"""Tests for cross-session failure clustering API routes.

Exercises the route handlers in ``api/cross_session_routes.py`` directly via
their endpoint functions (the ``api_repo_factory`` + ``_get_route_endpoint``
convention established in ``tests/test_api_contract.py``).

Note: ``tests/test_cross_session_clustering.py`` covers the
``CrossSessionClusterAnalyzer`` logic itself; these tests cover the HTTP route
handlers that wrap it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api import app_context
from api import services as api_services
from collector.buffer import get_event_buffer
from collector.server import configure_storage
from storage import Base, TraceRepository


def _get_route_endpoint(path: str, method: str):
    """Return the route endpoint function for a path/method pair."""
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def api_repo_factory(tmp_path, monkeypatch):
    """Build an isolated sqlite DB and wire app_context + collector storage to it."""
    db_path = tmp_path / "cross-session-routes.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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

    configure_storage(None)
    configure_event_pipeline(None)
    asyncio.run(engine.dispose())


def _make_session(
    session_id: str,
    *,
    agent_name: str = "test_agent",
    framework: str = "pytest",
    status: SessionStatus = SessionStatus.COMPLETED,
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc),
        status=status,
        total_cost_usd=0.25,
        total_tokens=500,
        llm_calls=2,
        tool_calls=4,
        errors=1,
        replay_value=0.6,
        config={"mode": "test"},
        tags=["cluster-test"],
    )


def _make_event(
    session_id: str,
    event_type: EventType,
    name: str = "test_event",
    *,
    importance: float = 0.5,
) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        parent_id=None,
        event_type=event_type,
        name=name,
        data={},
        metadata={},
        importance=importance,
        upstream_event_ids=[],
    )


def _fingerprint(event_type: EventType, name: str) -> str:
    """Mirror the route's fingerprint computation (TraceEvent has no fingerprint attr)."""
    return f"{event_type}:{name}"


# -----------------------------------------------------------------------------
# GET /api/clusters  ->  get_cross_session_clusters
# -----------------------------------------------------------------------------


def test_get_clusters_returns_recurring_failure_cluster(api_repo_factory):
    """Multiple sessions sharing the same failure fingerprint form one cluster."""
    fp = _fingerprint(EventType.ERROR, "timeout")

    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            for sid in ("cs-cluster-1", "cs-cluster-2", "cs-cluster-3"):
                await repo.create_session(_make_session(sid))
                await repo.add_event(_make_event(sid, EventType.ERROR, name="timeout"))
            await session.commit()

    asyncio.run(seed())

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await clusters_endpoint(limit=50, min_count=2, repo=repo)

    payload = asyncio.run(run())

    assert payload["min_count"] == 2
    assert payload["total"] == 1
    clusters = payload["clusters"]
    assert len(clusters) == 1
    assert clusters[0]["fingerprint"] == fp
    assert clusters[0]["count"] == 3


def test_get_clusters_empty_when_no_sessions(api_repo_factory):
    """No sessions at all -> empty clusters response."""

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await clusters_endpoint(limit=50, min_count=2, repo=repo)

    payload = asyncio.run(run())

    assert payload["clusters"] == []
    assert payload["total"] == 0
    assert payload["min_count"] == 2


def test_get_clusters_no_failures_when_only_tool_calls(api_repo_factory):
    """Non-failure events (severity <= 0.7) produce no failure fingerprints."""
    from collector.intelligence.compute import compute_event_ranking  # noqa: F401  # sanity import

    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            await repo.create_session(_make_session("cs-tools-1"))
            await repo.add_event(_make_event("cs-tools-1", EventType.TOOL_CALL, name="search"))
            await repo.create_session(_make_session("cs-tools-2"))
            await repo.add_event(_make_event("cs-tools-2", EventType.TOOL_CALL, name="search"))
            await session.commit()

    asyncio.run(seed())

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await clusters_endpoint(limit=50, min_count=1, repo=repo)

    payload = asyncio.run(run())

    assert payload["total"] == 0
    assert payload["clusters"] == []


def test_get_clusters_min_count_filters_below_threshold(api_repo_factory):
    """A cluster with count below min_count is filtered out."""
    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            # Two sessions share the failure -> cluster count would be 2.
            await repo.create_session(_make_session("cs-min-1"))
            await repo.add_event(_make_event("cs-min-1", EventType.ERROR, name="conn_reset"))
            await repo.create_session(_make_session("cs-min-2"))
            await repo.add_event(_make_event("cs-min-2", EventType.ERROR, name="conn_reset"))
            await session.commit()

    asyncio.run(seed())

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            # Demand at least 3 sessions; only 2 are present -> filtered out.
            return await clusters_endpoint(limit=50, min_count=3, repo=repo)

    payload = asyncio.run(run())

    assert payload["min_count"] == 3
    assert payload["total"] == 0
    assert payload["clusters"] == []


def test_get_clusters_limit_caps_results(api_repo_factory):
    """limit slices the resulting cluster list after min_count filtering."""
    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            # Each session carries two distinct failure fingerprints shared across
            # both sessions -> two clusters, each with count 2.
            for sid in ("cs-limit-1", "cs-limit-2"):
                await repo.create_session(_make_session(sid))
                await repo.add_event(_make_event(sid, EventType.ERROR, name="timeout"))
                await repo.add_event(_make_event(sid, EventType.ERROR, name="conn_reset"))
            await session.commit()

    asyncio.run(seed())

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await clusters_endpoint(limit=1, min_count=2, repo=repo)

    payload = asyncio.run(run())

    assert payload["total"] == 1
    assert len(payload["clusters"]) == 1


def test_get_clusters_skips_sessions_without_events(api_repo_factory):
    """A session with no events is skipped; remaining failure still clusters."""
    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            await repo.create_session(_make_session("cs-with-events"))
            await repo.add_event(_make_event("cs-with-events", EventType.ERROR, name="timeout"))
            # Empty session -> skipped inside the handler.
            await repo.create_session(_make_session("cs-empty"))
            await session.commit()

    asyncio.run(seed())

    clusters_endpoint = _get_route_endpoint("/api/clusters", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await clusters_endpoint(limit=50, min_count=1, repo=repo)

    payload = asyncio.run(run())

    assert payload["total"] == 1
    assert payload["clusters"][0]["count"] == 1
    assert payload["clusters"][0]["sessions"] == ["cs-with-events"]


# -----------------------------------------------------------------------------
# GET /api/clusters/{fingerprint}/sessions  ->  get_cluster_sessions
# -----------------------------------------------------------------------------


def test_get_cluster_sessions_returns_matching_sessions(api_repo_factory):
    """Sessions containing the queried fingerprint are returned."""
    fp = _fingerprint(EventType.ERROR, "timeout")

    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            await repo.create_session(_make_session("cs-sess-1"))
            await repo.add_event(_make_event("cs-sess-1", EventType.ERROR, name="timeout"))
            await repo.create_session(_make_session("cs-sess-2"))
            await repo.add_event(_make_event("cs-sess-2", EventType.ERROR, name="timeout"))
            # Unrelated session that should not appear.
            await repo.create_session(_make_session("cs-sess-other"))
            await repo.add_event(_make_event("cs-sess-other", EventType.TOOL_CALL, name="search"))
            await session.commit()

    asyncio.run(seed())

    sessions_endpoint = _get_route_endpoint("/api/clusters/{fingerprint}/sessions", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sessions_endpoint(fingerprint=fp, repo=repo)

    payload = asyncio.run(run())

    assert payload["fingerprint"] == fp
    assert payload["total"] == 2
    returned_ids = {s.id for s in payload["sessions"]}
    assert returned_ids == {"cs-sess-1", "cs-sess-2"}
    # SessionSchema shape sanity check.
    first = payload["sessions"][0]
    assert first.agent_name == "test_agent"
    assert first.framework == "pytest"
    assert first.errors == 1


def test_get_cluster_sessions_404_when_no_match(api_repo_factory):
    """An absent fingerprint raises HTTPException 404."""
    from fastapi import HTTPException

    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            await repo.create_session(_make_session("cs-unrelated"))
            await repo.add_event(_make_event("cs-unrelated", EventType.TOOL_CALL, name="search"))
            await session.commit()

    asyncio.run(seed())

    sessions_endpoint = _get_route_endpoint("/api/clusters/{fingerprint}/sessions", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sessions_endpoint(fingerprint="error:nonexistent", repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())

    assert exc_info.value.status_code == 404
    assert "error:nonexistent" in exc_info.value.detail


def test_get_cluster_sessions_404_on_empty_db(api_repo_factory):
    """No sessions at all -> HTTPException 404."""
    from fastapi import HTTPException

    sessions_endpoint = _get_route_endpoint("/api/clusters/{fingerprint}/sessions", "GET")

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await sessions_endpoint(fingerprint="error:timeout", repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())

    assert exc_info.value.status_code == 404
