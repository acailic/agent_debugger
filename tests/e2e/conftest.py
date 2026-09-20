"""End-to-end scenario fixtures: a REAL server, a REAL SDK, a REAL database.

Unlike the route tests (in-process ASGI client), the e2e suite runs the full
product loop the way a user does:

    SDK in-process
      -> HttpTransport (real TCP, real Authorization header)
      -> uvicorn subprocess (real server lifespan, buffers, pipelines)
      -> file-backed SQLite (real persistence)
      -> operator queries over HTTP (audit, replay, portfolio, ...)

The server runs as a subprocess on an ephemeral port with its own temporary
database, so the suite is hermetic: no shared state with the unit-test
in-process app context, and xdist workers each get their own server.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]

# Registered in pyproject.toml alongside `integration`.
pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class E2EServer:
    base_url: str
    db_url: str
    api_key: str
    tenant_id: str
    process: subprocess.Popen


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> E2EServer:
    """Start a real uvicorn server on an ephemeral port and register an API key."""
    tmp = tmp_path_factory.mktemp("e2e-server")
    db_url = f"sqlite+aiosqlite:///{tmp}/e2e.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = {
        **os.environ,
        "AGENT_DEBUGGER_DB_URL": db_url,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(tmp),  # keep any relative-path side effects (analytics db) inside tmp
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for the server to come up (tables are created in its lifespan).
    deadline = time.monotonic() + 60
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode(errors="replace") if process.stdout else ""
            raise RuntimeError(f"e2e server died during startup:\n{output[-4000:]}")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if response.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001 - retry until deadline
            last_error = exc
        time.sleep(0.3)
    else:
        process.terminate()
        raise RuntimeError(f"e2e server never became healthy: {last_error}")

    # Register an API key directly in the server's database (tenant-aware E2E).
    from auth.api_keys import generate_api_key, hash_key
    from auth.models import APIKeyModel
    from storage.engine import create_db_engine

    raw_key = generate_api_key(environment="test")
    tenant_id = f"e2e-tenant-{uuid.uuid4().hex[:8]}"

    async def _insert_key() -> None:
        engine = create_db_engine(db_url)
        try:
            from storage import Base

            async with engine.begin() as conn:
                # Tables were created by the server lifespan; this covers the
                # race where the health endpoint beat schema creation.
                await conn.run_sync(
                    Base.metadata.create_all, tables=[APIKeyModel.__table__]
                )
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine) as session:
                session.add(
                    APIKeyModel(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        key_hash=hash_key(raw_key),
                        key_prefix=raw_key[:12],
                        environment="test",
                        name="e2e-suite",
                        is_active=True,
                    )
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_insert_key())

    yield E2EServer(
        base_url=base_url,
        db_url=db_url,
        api_key=raw_key,
        tenant_id=tenant_id,
        process=process,
    )

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@pytest.fixture
def e2e_sdk(e2e_server: E2EServer):
    """Point the in-process SDK at the e2e server with a real API key.

    Function-scoped on purpose: the shared unit-test conftest resets the SDK
    global config before every test, so this re-initializes it each time.
    """
    from agent_debugger_sdk import config as cfg_mod
    from agent_debugger_sdk import simple as simple_mod

    cfg_mod.init(
        endpoint=e2e_server.base_url,
        api_key=e2e_server.api_key,
        enabled=True,
    )
    # trace_session's first-use init() is a no-op when config exists, but make
    # the intent explicit so future changes to init() cannot silently reroute.
    simple_mod._initialized = True
    yield
    cfg_mod._global_config = None
    simple_mod._initialized = False


_SDK_PIPELINE_VARS = (
    "_default_event_buffer",
    "_default_event_persister",
    "_default_checkpoint_persister",
    "_default_session_start_hook",
    "_default_session_update_hook",
)


async def run_scenario(coro):
    """Await a scenario coroutine with the SDK pipeline ContextVars cleared.

    Unit tests that ran earlier in this process may have configured the
    in-process event pipeline globally; a leaked persister hook would stop
    TraceContext from wiring the HTTP transport. The vars are cleared for
    the scenario's dynamic scope and restored afterwards, so the SDK always
    takes the real network path without leaking into other tests.
    """
    from agent_debugger_sdk.core.context import vars as sdk_vars

    variables = [getattr(sdk_vars, name) for name in _SDK_PIPELINE_VARS]
    tokens = [var.set(None) for var in variables]
    try:
        return await coro
    finally:
        for var, token in zip(variables, tokens):
            var.reset(token)


@pytest_asyncio.fixture
async def api(e2e_server: E2EServer) -> httpx.AsyncClient:
    """Authenticated operator HTTP client for query/analysis endpoints."""
    async with httpx.AsyncClient(
        base_url=e2e_server.base_url,
        headers={"Authorization": f"Bearer {e2e_server.api_key}"},
        timeout=30.0,
    ) as client:
        yield client
