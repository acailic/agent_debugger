from __future__ import annotations

import asyncio

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from api import app_context
from api import services as api_services
from benchmarks import run_evidence_grounding_session, run_failure_cluster_session, run_safety_escalation_session
from collector.buffer import get_event_buffer
from collector.server import SessionCreate, TraceEventIngest, configure_storage, create_session, ingest_trace
from storage import Base, TraceRepository


def _get_route_endpoint(path: str, method: str):
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


def _create_mock_request():
    """Create a mock Request object for testing."""
    # Create a minimal mock request
    class MockRequest:
        def __init__(self):
            self.headers = {}
            self.method = "POST"
            self.url = "http://test"
            self.query_params = {}
            self.path_params = {}
            self.body = b""

        async def body(self):
            return b""

    return MockRequest()


@pytest.fixture
def api_repo_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "api-contract.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(api_main, "engine", engine)
    monkeypatch.setattr(api_main, "async_session_maker", session_maker)
    monkeypatch.setattr(app_context, "engine", engine)
    monkeypatch.setattr(app_context, "async_session_maker", session_maker)

    buffer = get_event_buffer()
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    configure_storage(session_maker)
    configure_event_pipeline(
        buffer,
        persist_event=api_services.persist_event,
        persist_checkpoint=api_services.persist_checkpoint,
        persist_session_start=api_services.persist_session_start,
        persist_session_update=api_services.persist_session_update,
    )

    yield session_maker

    configure_event_pipeline(None)
    asyncio.run(engine.dispose())


def test_trace_bundle_returns_normalized_research_events(api_repo_factory):
    session_id = "api-evidence-grounding"
    asyncio.run(run_evidence_grounding_session(session_id))
    trace_endpoint = _get_route_endpoint("/api/sessions/{session_id}/trace", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await trace_endpoint(session_id=session_id, repo=repo)

    payload = asyncio.run(run())
    assert payload.session.id == session_id
    assert payload.tree is not None
    assert payload.analysis["event_rankings"]

    decision = next(event for event in payload.events if event.event_type == "decision")
    assert decision.evidence_event_ids
    assert decision.upstream_event_ids


def test_analysis_endpoint_surfaces_failure_clusters(api_repo_factory):
    session_id = "api-failure-cluster"
    asyncio.run(run_failure_cluster_session(session_id))
    analysis_endpoint = _get_route_endpoint("/api/sessions/{session_id}/analysis", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await analysis_endpoint(session_id=session_id, repo=repo)

    analysis = asyncio.run(run()).analysis
    assert analysis["failure_clusters"]
    assert analysis["representative_failure_ids"]
    assert analysis["failure_clusters"][0]["count"] >= 2
    assert analysis["failure_explanations"]
    assert analysis["failure_explanations"][0]["candidates"]


def test_replay_endpoint_keeps_checkpoint_and_safety_breakpoints(api_repo_factory):
    session_id = "api-safety-escalation"
    asyncio.run(run_safety_escalation_session(session_id))
    replay_endpoint = _get_route_endpoint("/api/sessions/{session_id}/replay", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await replay_endpoint(
                session_id=session_id,
                mode="failure",
                focus_event_id=None,
                breakpoint_event_types=None,
                breakpoint_tool_names=None,
                breakpoint_confidence_below=None,
                breakpoint_safety_outcomes="warn,block",
                stop_at_breakpoint=False,
                collapse_threshold=0.35,
                repo=repo,
            )

    replay = asyncio.run(run())
    assert replay.nearest_checkpoint is not None
    assert replay.failure_event_ids
    assert any(event.event_type == "safety_check" for event in replay.breakpoints)


def test_ingest_trace_preserves_upstream_event_ids(api_repo_factory):
    async def run():
        mock_request = _create_mock_request()
        session = await create_session(
            SessionCreate(agent_name="collector_test", framework="pytest", tags=["api"]),
            mock_request,
        )
        response = await ingest_trace(
            TraceEventIngest(
                session_id=session.id,
                event_type="decision",
                name="api_decision",
                upstream_event_ids=["tool-1", "llm-2"],
                data={
                    "reasoning": "Prefer grounded tool output",
                    "confidence": 0.42,
                    "evidence": [{"source": "tool", "content": "verified"}],
                    "evidence_event_ids": ["tool-1"],
                    "alternatives": [],
                    "chosen_action": "answer",
                },
            ),
            mock_request,
        )
        assert response.status == "queued"

        trace_endpoint = _get_route_endpoint("/api/sessions/{session_id}/trace", "GET")
        async with api_repo_factory() as db_session:
            repo = TraceRepository(db_session)
            return await trace_endpoint(session_id=session.id, repo=repo)

    payload = asyncio.run(run())
    decision = next(event for event in payload.events if event.name == "api_decision")
    assert decision.upstream_event_ids == ["tool-1", "llm-2"]
    assert decision.evidence_event_ids == ["tool-1"]


def test_search_endpoint_finds_events_by_payload_and_filter(api_repo_factory):
    session_id = "api-search-evidence"
    asyncio.run(run_evidence_grounding_session(session_id))
    search_endpoint = _get_route_endpoint("/api/traces/search", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await search_endpoint(
                query="Belgrade",
                session_id=session_id,
                event_type="decision",
                limit=20,
                repo=repo,
            )

    payload = asyncio.run(run())
    assert payload.query == "Belgrade"
    assert payload.session_id == session_id
    assert payload.event_type == "decision"
    assert payload.total >= 1
    assert all(event.event_type == "decision" for event in payload.results)
    assert any("Belgrade" in str(event) for event in payload.results)
