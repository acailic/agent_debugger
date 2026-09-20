"""No-key local delivery: endpoint configured, API key unset.

Covers the W02 quickstart path. Destination selection is independent of
authentication: ``init(endpoint=...)`` without an API key must install the
HTTP transport and deliver unauthenticated to a local collector, while
disabled or endpoint-less configs stay fully inert (no transport, no
network). One test runs a REAL in-process collector (uvicorn thread serving
the collector's own routes over TCP) to prove events are persisted.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from agent_debugger_sdk import config as cfg_mod
from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.context import vars as sdk_vars
from agent_debugger_sdk.transport import HttpTransport, TransientError
from collector.server import configure_storage
from collector.server import router as collector_router
from storage import Base, TraceRepository


def _unique_session_id() -> str:
    return f"no-key-{uuid.uuid4().hex[:10]}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# Pipeline ContextVars that earlier tests in this process may have configured;
# a leaked hook would suppress the HTTP transport exactly like the old bug.
_PIPELINE_VARS = (
    "_default_event_buffer",
    "_default_event_persister",
    "_default_checkpoint_persister",
    "_default_session_start_hook",
    "_default_session_update_hook",
)


async def _with_clean_pipeline(coro):
    """Await a scenario coroutine with the SDK pipeline ContextVars cleared."""
    variables = [getattr(sdk_vars, name) for name in _PIPELINE_VARS]
    tokens = [var.set(None) for var in variables]
    try:
        return await coro
    finally:
        for var, token in zip(variables, tokens):
            var.reset(token)


@pytest.fixture(scope="module")
def collector_server():
    """Real in-process collector: uvicorn thread serving collector routes over TCP."""
    captured_requests: list[dict[str, str | None]] = []

    app = FastAPI()
    app.include_router(collector_router)

    @app.middleware("http")
    async def _capture_requests(request, call_next):
        captured_requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "authorization": request.headers.get("authorization"),
            }
        )
        return await call_next(request)

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "in-process collector never started"

    yield SimpleNamespace(base_url=f"http://127.0.0.1:{port}", captured=captured_requests)

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
async def collector_storage(tmp_path):
    """Temp SQLite storage wired into the collector's ingestion routes.

    NullPool on purpose: the uvicorn thread serves requests on its own event
    loop, so pooled connections must never cross loops.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path}/collector.db"
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_storage(async_sessionmaker(engine, expire_on_commit=False))
    yield db_url
    configure_storage(None)
    await engine.dispose()


async def test_endpoint_without_api_key_installs_and_uses_http_transport(
    collector_server, collector_storage
):
    """Local no-key mode: endpoint set, api_key unset -> HttpTransport, no auth header."""
    cfg_mod.init(endpoint=collector_server.base_url)  # no api_key

    session_id = _unique_session_id()
    captured_before = len(collector_server.captured)

    async def scenario():
        async with TraceContext(session_id=session_id, agent_name="no_key_agent") as ctx:
            assert isinstance(ctx._transport, HttpTransport)
            assert "Authorization" not in ctx._transport._headers
            await ctx.record_tool_call("search", {"query": "no-key"})

    await _with_clean_pipeline(scenario())

    delivered = collector_server.captured[captured_before:]
    delivered_paths = {r["path"] for r in delivered}
    assert "/api/sessions" in delivered_paths
    assert "/api/traces" in delivered_paths
    # Local mode sends without an Authorization header — the collector's
    # loopback tenant resolution is the only gate.
    assert delivered and all(r["authorization"] is None for r in delivered)


async def test_disabled_config_is_inert(monkeypatch):
    """enabled=False with an endpoint configured must not construct a transport."""
    constructed: list[tuple] = []

    class _ForbidTransport:
        def __init__(self, *args, **kwargs):
            constructed.append((args, kwargs))

    monkeypatch.setattr("agent_debugger_sdk.transport.HttpTransport", _ForbidTransport)
    # Port 9 has nothing listening: any request would fail loudly.
    cfg_mod.init(endpoint="http://127.0.0.1:9", enabled=False)

    async def scenario():
        async with TraceContext(session_id=_unique_session_id()) as ctx:
            assert ctx._transport is None
            await ctx.record_tool_call("search", {"query": "disabled"})
            events = await ctx.get_events()
        return ctx, events

    ctx, events = await _with_clean_pipeline(scenario())

    assert constructed == []
    # Fully inert: tracing disabled means nothing is even recorded locally.
    assert events == []


async def test_no_endpoint_is_inert(monkeypatch):
    """init() without endpoint or key: no transport, no network, local recording only."""
    constructed: list[tuple] = []

    class _ForbidTransport:
        def __init__(self, *args, **kwargs):
            constructed.append((args, kwargs))

    monkeypatch.setattr("agent_debugger_sdk.transport.HttpTransport", _ForbidTransport)
    cfg_mod.init()  # bare init: no endpoint, no api_key

    async def scenario():
        async with TraceContext(session_id=_unique_session_id()) as ctx:
            assert ctx._transport is None
            await ctx.record_tool_call("search", {"query": "offline"})
            events = await ctx.get_events()
        return events

    events = await _with_clean_pipeline(scenario())

    assert constructed == []
    # Old inert behavior: events recorded in memory, never delivered.
    assert any(event.name == "search_call" for event in events)

    # Same for get_config() when init() was never called at all.
    cfg_mod._global_config = None
    ctx = TraceContext(session_id=_unique_session_id())
    async with ctx:
        assert ctx._transport is None
    assert constructed == []


async def test_unreachable_collector_exits_cleanly_and_reports_failure():
    """Endpoint at a closed port: session must not raise, failures must be observed."""
    cfg_mod.init(endpoint=f"http://127.0.0.1:{_free_port()}")  # nothing listens

    session_id = _unique_session_id()
    failures: list = []

    async def scenario():
        # Skip real backoff sleeps so retry exhaustion stays fast.
        with patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock):
            async with TraceContext(session_id=session_id) as ctx:
                assert isinstance(ctx._transport, HttpTransport)
                # Observe the transport's failure-callback contract from the
                # wired delivery path (events must not vanish silently).
                ctx._transport._on_delivery_failure = failures.append
                await ctx.record_tool_call("search", {"query": "offline"})
            # Context exited cleanly despite every delivery failing.
        assert failures, "delivery failures must surface through on_delivery_failure"
        assert all(isinstance(error, TransientError) for error in failures)

    await _with_clean_pipeline(scenario())


async def test_no_key_delivery_persists_on_real_collector(collector_server, collector_storage):
    """End-to-end: no-key traced function -> events queryable in the collector's DB."""
    cfg_mod.init(endpoint=collector_server.base_url)  # no api_key

    session_id = _unique_session_id()
    tool_event_id: list[str] = []

    async def scenario():
        async with TraceContext(session_id=session_id, agent_name="no_key_agent") as ctx:
            tool_event_id.append(await ctx.record_tool_call("search", {"query": "persisted"}))

    await _with_clean_pipeline(scenario())

    engine = create_async_engine(collector_storage, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as db:
            repo = TraceRepository(db, tenant_id="local")
            session = await repo.get_session(session_id)
            assert session is not None
            assert session.agent_name == "no_key_agent"

            events = await repo.list_events(session_id)
            event_ids = {event.id for event in events}
            event_names = {event.name for event in events}
            assert tool_event_id[0] in event_ids
            assert "session_start" in event_names
            assert "session_end" in event_names
    finally:
        await engine.dispose()
