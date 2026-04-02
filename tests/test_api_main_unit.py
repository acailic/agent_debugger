from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.events import Checkpoint, Session, ToolCallEvent
from api import app_context
from api import dependencies as api_dependencies
from api import services as api_services
from api.analytics_routes import RecordEventRequest
from api.middleware import LoggingMiddleware, RequestIDMiddleware
from api.schemas import CreateKeyRequest, SessionUpdateRequest
from storage import Base, TraceRepository


def _get_route_endpoint(path: str, method: str):
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def api_repo_factory(tmp_path, monkeypatch):
    from collector.intelligence.facade import TraceIntelligence
    from redaction.pipeline import RedactionPipeline

    db_path = tmp_path / "api-main-unit.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    trace_intelligence = TraceIntelligence()
    redaction_pipeline = RedactionPipeline.from_config()

    monkeypatch.setattr(app_context, "engine", engine)
    monkeypatch.setattr(app_context, "async_session_maker", session_maker)
    monkeypatch.setattr(app_context, "trace_intelligence", trace_intelligence)
    monkeypatch.setattr(app_context, "_redaction_pipeline", redaction_pipeline)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    yield session_maker

    asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_get_tenant_id_uses_local_mode_without_api_lookup():
    request = SimpleNamespace(headers={})
    db = MagicMock()

    with (
        patch("api.dependencies.get_config", return_value=SimpleNamespace(mode="local")),
        patch("api.dependencies.get_tenant_from_api_key", new=AsyncMock()) as get_tenant_from_api_key,
    ):
        tenant_id = await api_dependencies.get_tenant_id(request, db)

    assert tenant_id == "local"
    get_tenant_from_api_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_tenant_id_uses_api_key_lookup_in_cloud_mode():
    request = SimpleNamespace(headers={"authorization": "Bearer test"})
    db = MagicMock()

    with (
        patch("api.dependencies.get_config", return_value=SimpleNamespace(mode="cloud")),
        patch(
            "api.dependencies.get_tenant_from_api_key", new=AsyncMock(return_value="tenant-cloud")
        ) as get_tenant_from_api_key,
    ):
        tenant_id = await api_dependencies.get_tenant_id(request, db)

    assert tenant_id == "tenant-cloud"
    get_tenant_from_api_key.assert_awaited_once_with(request, db)


def test_get_repository_scopes_to_tenant():
    session = MagicMock()
    repo = api_dependencies.get_repository(session, "tenant-a")
    assert isinstance(repo, TraceRepository)
    assert repo.session is session
    assert repo.tenant_id == "tenant-a"


def test_create_app_orders_request_id_middleware_before_logging():
    app = api_main.create_app()
    middleware_classes = [middleware.cls for middleware in app.user_middleware]

    assert middleware_classes.index(RequestIDMiddleware) < middleware_classes.index(LoggingMiddleware)


@pytest.mark.asyncio
async def test_get_db_session_yields_session_from_factory(api_repo_factory):
    generator = api_dependencies.get_db_session()
    session = await anext(generator)
    assert isinstance(session, AsyncSession)
    await generator.aclose()


def test_normalizers_include_analysis_summary():
    session = Session(
        id="session-normalize",
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
    )
    event = ToolCallEvent(session_id=session.id, tool_name="search", arguments={"q": "Belgrade"})
    checkpoint = Checkpoint(session_id=session.id, event_id=event.id, sequence=1)

    normalized_session = api_services.normalize_session(session, {"replay_value": 0.9})

    assert normalized_session.id == "session-normalize"
    assert normalized_session.replay_value == 0.9


def test_request_models_strip_whitespace():
    create_key = CreateKeyRequest(name="  primary  ", environment="  live  ")
    session_update = SessionUpdateRequest(agent_name="  agent  ", framework="  pytest  ")
    analytics_event = RecordEventRequest(event_type="  why_button_clicked  ", agent_name="  agent  ")

    assert create_key.name == "primary"
    assert create_key.environment == "live"
    assert session_update.agent_name == "agent"
    assert session_update.framework == "pytest"
    assert analytics_event.event_type == "why_button_clicked"
    assert analytics_event.agent_name == "agent"


@pytest.mark.asyncio
async def test_lifespan_configures_pipeline_for_sqlite(monkeypatch):
    created_buffers: list[str] = []
    configure_storage = MagicMock()
    configure_event_pipeline = MagicMock()
    prepare_database = AsyncMock()

    def fake_create_buffer(*, backend: str):
        created_buffers.append(backend)
        return "buffer-instance"

    monkeypatch.setenv("REDIS_URL", "")

    with (
        patch("storage.engine.get_database_url", return_value="sqlite+aiosqlite:///tmp/test.db"),
        patch("collector.create_buffer", side_effect=fake_create_buffer),
        patch("api.main.configure_storage", configure_storage),
        patch("api.main.configure_event_pipeline", configure_event_pipeline),
        patch("api.main.prepare_database", prepare_database),
    ):
        async with api_main.lifespan(FastAPI()):
            pass

    assert created_buffers == ["memory"]
    prepare_database.assert_awaited_once_with(app_context.engine)
    configure_storage.assert_called_once_with(app_context.async_session_maker)
    configure_event_pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_redaction_pipeline_uses_runtime_config():
    from redaction.pipeline import RedactionPipeline

    with patch(
        "agent_debugger_sdk.config.get_config",
        return_value=SimpleNamespace(redact_prompts=True, max_payload_kb=32),
    ):
        pipeline = RedactionPipeline.from_config()

    assert pipeline.redact_prompts is True
    assert pipeline.redact_pii is False
    assert pipeline.max_payload_kb == 32


@pytest.mark.asyncio
async def test_persist_helpers_store_session_event_and_checkpoint(api_repo_factory):
    session = Session(id="persisted-session", agent_name="agent", framework="pytest")
    event = ToolCallEvent(session_id=session.id, tool_name="search", arguments={"q": "Belgrade"})
    checkpoint = Checkpoint(session_id=session.id, event_id=event.id, sequence=1)
    pipeline = SimpleNamespace(apply=MagicMock(side_effect=lambda value: value))

    with patch("api.app_context._get_redaction_pipeline", return_value=pipeline):
        await api_services.persist_session_start(session)
        await api_services.persist_session_start(session)

        session.status = "completed"
        session.ended_at = datetime(2026, 3, 23, 11, 0, tzinfo=timezone.utc)
        await api_services.persist_session_update(session)
        await api_services.persist_event(event)
        await api_services.persist_checkpoint(checkpoint)

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        stored_session = await repo.get_session(session.id)
        stored_events = await repo.list_events(session.id)
        stored_checkpoints = await repo.list_checkpoints(session.id)

    assert stored_session is not None
    assert stored_session.status == "completed"
    assert [stored_event.tool_name for stored_event in stored_events] == ["search"]
    assert [stored_checkpoint.sequence for stored_checkpoint in stored_checkpoints] == [1]
    pipeline.apply.assert_called_once()


@pytest.mark.asyncio
async def test_list_sessions_can_sort_by_replay_value(api_repo_factory):
    list_sessions = _get_route_endpoint("/api/sessions", "GET")

    session_low = Session(
        id="replay-low",
        agent_name="low",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc),
    )
    session_high = Session(
        id="replay-high",
        agent_name="high",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
    )
    analyses = {
        "replay-low": {
            "session_replay_value": 0.2,
            "retention_tier": "low",
            "session_summary": {"failure_count": 0, "behavior_alert_count": 0},
            "representative_failure_ids": [],
        },
        "replay-high": {
            "session_replay_value": 0.9,
            "retention_tier": "high",
            "session_summary": {"failure_count": 2, "behavior_alert_count": 1},
            "representative_failure_ids": ["event-1"],
        },
    }

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(session_low)
        await repo.create_session(session_high)

        with patch.object(
            app_context.trace_intelligence,
            "analyze_session",
            side_effect=lambda events, checkpoints, **kwargs: analyses[events[0].session_id]
            if events
            else analyses["replay-low"],
        ):
            event_high = ToolCallEvent(session_id="replay-high", tool_name="high", arguments={})
            event_low = ToolCallEvent(session_id="replay-low", tool_name="low", arguments={})
            with (
                patch.object(repo, "get_event_tree", side_effect=[[event_high], [event_low]]),
                patch.object(repo, "list_checkpoints", side_effect=[[], []]),
            ):
                response = await list_sessions(limit=10, offset=0, sort_by="replay_value", repo=repo)

    assert [session.id for session in response.sessions] == ["replay-high", "replay-low"]
    assert response.sessions[0].representative_event_id == "event-1"
    assert response.sessions[1].representative_event_id is None


@pytest.mark.asyncio
async def test_auth_routes_create_list_and_revoke_keys(api_repo_factory):
    create_key = _get_route_endpoint("/api/auth/keys", "POST")
    list_keys = _get_route_endpoint("/api/auth/keys", "GET")
    revoke_key = _get_route_endpoint("/api/auth/keys/{key_id}", "DELETE")

    async with api_repo_factory() as db_session:
        with (
            patch("auth.service.generate_api_key", return_value="ad_live_example_secret"),
            patch("auth.service.hash_key", return_value="hashed-secret"),
        ):
            created = await create_key(
                CreateKeyRequest(name="primary", environment="live"),
                tenant_id="tenant-a",
                db=db_session,
            )

        listed = await list_keys(tenant_id="tenant-a", db=db_session)
        await revoke_key(created.id, tenant_id="tenant-a", db=db_session)
        listed_after_revoke = await list_keys(tenant_id="tenant-a", db=db_session)

    assert created.key == "ad_live_example_secret"
    assert listed[0].id == created.id
    assert listed[0].environment == "live"
    assert listed_after_revoke == []


@pytest.mark.asyncio
async def test_auth_revoke_route_raises_not_found_for_missing_key(api_repo_factory):
    revoke_key = _get_route_endpoint("/api/auth/keys/{key_id}", "DELETE")

    async with api_repo_factory() as db_session:
        with pytest.raises(HTTPException) as exc:
            await revoke_key("missing", tenant_id="tenant-a", db=db_session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Key not found"


@pytest.mark.asyncio
async def test_session_routes_return_persisted_data(api_repo_factory):
    list_sessions = _get_route_endpoint("/api/sessions", "GET")
    get_session = _get_route_endpoint("/api/sessions/{session_id}", "GET")
    update_session = _get_route_endpoint("/api/sessions/{session_id}", "PUT")
    get_traces = _get_route_endpoint("/api/sessions/{session_id}/traces", "GET")
    get_trace_bundle = _get_route_endpoint("/api/sessions/{session_id}/trace", "GET")
    get_tree = _get_route_endpoint("/api/sessions/{session_id}/tree", "GET")
    get_checkpoints = _get_route_endpoint("/api/sessions/{session_id}/checkpoints", "GET")
    get_analysis = _get_route_endpoint("/api/sessions/{session_id}/analysis", "GET")
    get_live = _get_route_endpoint("/api/sessions/{session_id}/live", "GET")
    search_traces = _get_route_endpoint("/api/traces/search", "GET")
    delete_session = _get_route_endpoint("/api/sessions/{session_id}", "DELETE")

    session = Session(id="session-success", agent_name="agent", framework="pytest")
    event = ToolCallEvent(session_id=session.id, tool_name="search", arguments={"q": "Belgrade"})
    checkpoint = Checkpoint(session_id=session.id, event_id=event.id, sequence=1)
    analysis_payload = {"session_replay_value": 0.4, "session_summary": {"failure_count": 0, "behavior_alert_count": 0}}
    live_payload = {"active": True, "tool_calls": 1}

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(session)
        await repo.add_event(event)
        await repo.create_checkpoint(checkpoint)

        with (
            patch.object(app_context.trace_intelligence, "analyze_session", return_value=analysis_payload),
            patch.object(app_context.trace_intelligence, "build_live_summary", return_value=live_payload),
        ):
            sessions_response = await list_sessions(limit=10, offset=0, sort_by="started_at", repo=repo)
            updated_response = await update_session(
                session_id=session.id,
                update=SessionUpdateRequest(status="completed", tags=["updated"]),
                repo=repo,
            )
            session_response = await get_session(session_id=session.id, repo=repo)
            traces_response = await get_traces(session_id=session.id, limit=10, offset=0, repo=repo)
            bundle_response = await get_trace_bundle(session_id=session.id, repo=repo)
            tree_response = await get_tree(session_id=session.id, repo=repo)
            checkpoints_response = await get_checkpoints(session_id=session.id, repo=repo)
            analysis_response = await get_analysis(session_id=session.id, repo=repo)
            live_response = await get_live(session_id=session.id, repo=repo)
            search_response = await search_traces(
                query="Belgrade",
                session_id=session.id,
                event_type="tool_call",
                limit=10,
                repo=repo,
            )
            delete_response = await delete_session(session_id=session.id, repo=repo)

    assert sessions_response.sessions[0].id == session.id
    assert updated_response.session.status == "completed"
    assert updated_response.session.tags == ["updated"]
    assert session_response.session.id == session.id
    assert session_response.session.status == "completed"
    assert traces_response.traces[0].tool_name == "search"
    assert bundle_response.session.id == session.id
    assert bundle_response.events[0].tool_name == "search"
    assert bundle_response.checkpoints[0].sequence == 1
    assert bundle_response.analysis == analysis_payload
    assert tree_response.events[0].tool_name == "search"
    assert checkpoints_response.checkpoints[0].sequence == 1
    assert analysis_response.analysis == analysis_payload
    assert live_response.live_summary == live_payload
    assert search_response.total == 1
    assert delete_response.deleted is True


@pytest.mark.asyncio
async def test_replay_route_passes_split_breakpoints_to_builder(api_repo_factory):
    replay_session = _get_route_endpoint("/api/sessions/{session_id}/replay", "GET")
    session = Session(id="replay-builder", agent_name="agent", framework="pytest")
    event = ToolCallEvent(session_id=session.id, tool_name="search", arguments={"q": "Belgrade"})
    checkpoint = Checkpoint(session_id=session.id, event_id=event.id, sequence=1)
    replay_payload = {
        "mode": "failure",
        "focus_event_id": "focus-1",
        "start_index": 2,
        "events": [event.to_dict()],
        "checkpoints": [checkpoint.to_dict()],
        "nearest_checkpoint": checkpoint.to_dict(),
        "breakpoints": [event.to_dict()],
        "failure_event_ids": ["focus-1"],
    }

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(session)
        await repo.add_event(event)
        await repo.create_checkpoint(checkpoint)

        with patch("api.replay_routes.build_replay", return_value=replay_payload) as build_replay:
            response = await replay_session(
                session_id=session.id,
                mode="failure",
                focus_event_id="focus-1",
                breakpoint_event_types="tool_call,decision",
                breakpoint_tool_names="search,lookup",
                breakpoint_confidence_below=0.4,
                breakpoint_safety_outcomes="warn,block",
                repo=repo,
            )

    assert response.failure_event_ids == ["focus-1"]
    assert response.breakpoints[0].tool_name == "search"
    build_replay.assert_called_once()
    replay_args, replay_kwargs = build_replay.call_args
    assert [replay_event.session_id for replay_event in replay_args[0]] == [session.id]
    assert [replay_checkpoint.session_id for replay_checkpoint in replay_args[1]] == [session.id]
    assert replay_kwargs == {
        "mode": "failure",
        "focus_event_id": "focus-1",
        "breakpoint_event_types": {"tool_call", "decision"},
        "breakpoint_tool_names": {"search", "lookup"},
        "breakpoint_confidence_below": 0.4,
        "breakpoint_safety_outcomes": {"warn", "block"},
    }


@pytest.mark.asyncio
async def test_session_routes_raise_not_found(api_repo_factory):
    get_session = _get_route_endpoint("/api/sessions/{session_id}", "GET")
    update_session = _get_route_endpoint("/api/sessions/{session_id}", "PUT")
    delete_session = _get_route_endpoint("/api/sessions/{session_id}", "DELETE")
    get_traces = _get_route_endpoint("/api/sessions/{session_id}/traces", "GET")
    get_trace_bundle = _get_route_endpoint("/api/sessions/{session_id}/trace", "GET")
    get_tree = _get_route_endpoint("/api/sessions/{session_id}/tree", "GET")
    get_checkpoints = _get_route_endpoint("/api/sessions/{session_id}/checkpoints", "GET")
    get_stream = _get_route_endpoint("/api/sessions/{session_id}/stream", "GET")
    get_analysis = _get_route_endpoint("/api/sessions/{session_id}/analysis", "GET")
    get_live = _get_route_endpoint("/api/sessions/{session_id}/live", "GET")
    get_replay = _get_route_endpoint("/api/sessions/{session_id}/replay", "GET")

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)

        for call in (
            lambda: get_session(session_id="missing", repo=repo),
            lambda: update_session(
                session_id="missing",
                update=SessionUpdateRequest(status="completed"),
                repo=repo,
            ),
            lambda: delete_session(session_id="missing", repo=repo),
            lambda: get_traces(session_id="missing", limit=10, offset=0, repo=repo),
            lambda: get_trace_bundle(session_id="missing", repo=repo),
            lambda: get_tree(session_id="missing", repo=repo),
            lambda: get_checkpoints(session_id="missing", repo=repo),
            lambda: get_stream(session_id="missing", repo=repo),
            lambda: get_analysis(session_id="missing", repo=repo),
            lambda: get_live(session_id="missing", repo=repo),
            lambda: get_replay(
                session_id="missing",
                mode="full",
                focus_event_id=None,
                breakpoint_event_types=None,
                breakpoint_tool_names=None,
                breakpoint_confidence_below=None,
                breakpoint_safety_outcomes=None,
                repo=repo,
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_route_returns_sse_response_for_existing_session(api_repo_factory):
    stream_session_events = _get_route_endpoint("/api/sessions/{session_id}/stream", "GET")
    session = Session(id="stream-session", agent_name="streamer", framework="pytest")

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(session)
        response = await stream_session_events(session_id=session.id, repo=repo)

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"


@pytest.mark.asyncio
async def test_replay_returns_empty_payload_for_session_without_events(api_repo_factory):
    replay_session = _get_route_endpoint("/api/sessions/{session_id}/replay", "GET")
    session = Session(id="empty-replay", agent_name="idle", framework="pytest")

    async with api_repo_factory() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(session)
        response = await replay_session(
            session_id=session.id,
            mode="focus",
            focus_event_id="event-1",
            breakpoint_event_types=None,
            breakpoint_tool_names=None,
            breakpoint_confidence_below=None,
            breakpoint_safety_outcomes=None,
            repo=repo,
        )

    assert response.events == []
    assert response.checkpoints == []
    assert response.nearest_checkpoint is None
    assert response.focus_event_id == "event-1"


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_and_redis_status(monkeypatch):
    health = _get_route_endpoint("/health", "GET")

    class GoodSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return SimpleNamespace(execute=AsyncMock())

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeRedis:
        @classmethod
        def from_url(cls, url: str):
            return cls()

        async def ping(self):
            return True

        async def aclose(self):
            return None

    fake_asyncio_module = types.SimpleNamespace(Redis=FakeRedis)
    fake_redis_module = types.SimpleNamespace(asyncio=fake_asyncio_module)

    monkeypatch.setattr(app_context, "async_session_maker", GoodSessionMaker())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with (
        patch("api.system_routes.get_config", return_value=SimpleNamespace(mode="cloud")),
        patch.dict(
            sys.modules,
            {"redis": fake_redis_module, "redis.asyncio": fake_asyncio_module},
        ),
    ):
        payload = await health()

    assert payload["status"] == "ok"
    assert payload["database"] == "connected"
    assert payload["redis"] == "connected"


@pytest.mark.asyncio
async def test_health_endpoint_degrades_on_database_and_redis_errors(monkeypatch):
    health = _get_route_endpoint("/health", "GET")

    class BrokenSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class BrokenRedis:
        @classmethod
        def from_url(cls, url: str):
            return cls()

        async def ping(self):
            raise RuntimeError("redis down")

        async def aclose(self):
            return None

    fake_asyncio_module = types.SimpleNamespace(Redis=BrokenRedis)
    fake_redis_module = types.SimpleNamespace(asyncio=fake_asyncio_module)

    monkeypatch.setattr(app_context, "async_session_maker", BrokenSessionMaker())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with (
        patch("api.system_routes.get_config", return_value=SimpleNamespace(mode="cloud")),
        patch.dict(
            sys.modules,
            {"redis": fake_redis_module, "redis.asyncio": fake_asyncio_module},
        ),
    ):
        payload = await health()

    assert payload["status"] == "degraded"
    assert payload["database"].startswith("error:")
    assert payload["redis"].startswith("error:")


@pytest.mark.asyncio
async def test_event_generator_emits_event_and_keepalive_and_unsubscribes():
    queue = asyncio.Queue()
    unsubscribe = AsyncMock()
    fake_buffer = SimpleNamespace(subscribe=AsyncMock(return_value=queue), unsubscribe=unsubscribe)
    event = ToolCallEvent(session_id="stream-test", tool_name="search", arguments={"q": "Belgrade"})

    outcomes = iter([event, TimeoutError()])

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        outcome = next(outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    with (
        patch("api.services.get_event_buffer", return_value=fake_buffer),
        patch("api.services.asyncio.wait_for", side_effect=fake_wait_for),
    ):
        generator = api_services.event_generator("stream-test")
        first = await anext(generator)
        second = await anext(generator)
        await generator.aclose()

    assert first.startswith("data: ")
    assert '"tool_name": "search"' in first
    assert second == ": keepalive\n\n"
    unsubscribe.assert_awaited_once()
