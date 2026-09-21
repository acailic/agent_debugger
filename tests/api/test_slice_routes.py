"""Route-handler tests for the Weiser slice endpoints.

Exercises ``GET /api/sessions/{session_id}/slices`` and
``GET /api/sessions/{session_id}/damage-radius`` in
``api/audit_routes.py`` via their endpoint functions (the
``api_repo_factory`` + ``_get_route_endpoint`` convention established in
``tests/test_api_contract.py``). The slice-computation logic itself is
covered by ``tests/test_slices.py``; these tests cover the HTTP route
handlers that wrap it.

All fixture ids are prefixed ``slr-`` (unique across the suite — xdist
collision rule).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api import app_context
from api import services as api_services
from collector.buffer import get_event_buffer
from collector.server import configure_storage
from storage import Base, TraceRepository

# The seeded chain: a decision citing a failed tool result, a second
# decision depending on the first, then the failure it caused. The first
# bad decision is the ungrounded/contradicted early decision.
_SESSION = "slr-slice-1"
_AGENT_START = "slr-ev-start"
_TOOL_CALL = "slr-ev-toolcall"
_TOOL_RESULT = "slr-ev-toolresult"  # errored tool result (the fact)
_DECISION_BAD = "slr-ev-dec-bad"  # cites the errored result, claims success
_DECISION_NEXT = "slr-ev-dec-next"  # child of the bad decision
_ERROR = "slr-ev-error"


def _get_route_endpoint(path: str, method: str):
    """Return the route endpoint function for a path/method pair."""
    from conftest import iter_app_api_routes

    for route_path, methods, endpoint in iter_app_api_routes(api_main.app):
        if route_path == path and method.upper() in (methods or {}):
            return endpoint
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def api_repo_factory(tmp_path, monkeypatch):
    """Build an isolated sqlite DB and wire app_context + collector storage to it."""
    db_path = tmp_path / "slice-routes.db"
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


def _session() -> Session:
    return Session(
        id=_SESSION,
        agent_name="test_agent",
        framework="pytest",
        started_at=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        total_cost_usd=0.1,
        total_tokens=100,
        llm_calls=1,
        tool_calls=1,
        errors=1,
        replay_value=0.5,
        config={"mode": "test"},
        tags=["slice-routes"],
    )


def _event(
    event_id: str,
    event_type: EventType,
    *,
    parent_id: str | None = None,
    name: str = "ev",
    data: dict | None = None,
    evidence: list[str] | None = None,
    session_id: str = _SESSION,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        event_type=event_type,
        name=name,
        data=data or {},
        metadata={},
        importance=0.5,
        upstream_event_ids=evidence or [],
    )


def _seed_events() -> list[TraceEvent]:
    """A chain whose bad decision is the first bad decision, with damage below it."""
    return [
        _event(_AGENT_START, EventType.AGENT_START, name="start"),
        _event(_TOOL_CALL, EventType.TOOL_CALL, name="fetch", parent_id=_AGENT_START),
        _event(
            _TOOL_RESULT,
            EventType.TOOL_RESULT,
            name="fetch",
            parent_id=_TOOL_CALL,
            data={"error": "connection reset"},
        ),
        # The bad decision: cites the errored result but asserts success —
        # contradicted by the outcome, and early in the trace.
        _event(
            _DECISION_BAD,
            EventType.DECISION,
            name="proceed",
            parent_id=_AGENT_START,
            data={
                "summary": "Proceed on fetched data",
                "confidence": 0.9,
                "rationale": "Data looks fine",
            },
            evidence=[_TOOL_RESULT],
        ),
        _event(
            _DECISION_NEXT,
            EventType.DECISION,
            name="write-report",
            parent_id=_DECISION_BAD,
            data={"summary": "Write report", "confidence": 0.8},
        ),
        _event(_ERROR, EventType.ERROR, name="crash", parent_id=_DECISION_NEXT),
    ]


def _seed(factory) -> None:
    async def run() -> None:
        async with factory() as session:
            repo = TraceRepository(session)
            await repo.create_session(_session())
            for event in _seed_events():
                await repo.add_event(event)
            await session.commit()

    asyncio.run(run())


def _call(factory, endpoint, **kwargs):
    async def run():
        async with factory() as session:
            repo = TraceRepository(session)
            return await endpoint(repo=repo, **kwargs)

    return asyncio.run(run())


# -----------------------------------------------------------------------------
# GET /api/sessions/{session_id}/slices  ->  get_session_slice
# -----------------------------------------------------------------------------


def test_backward_slice_route_includes_cited_evidence(api_repo_factory):
    """Backward slice of the bad decision includes the fact it cited."""
    _seed(api_repo_factory)
    endpoint = _get_route_endpoint("/api/sessions/{session_id}/slices", "GET")

    payload = _call(
        api_repo_factory,
        endpoint,
        session_id=_SESSION,
        node_id=_DECISION_BAD,
        direction="backward",
    )

    assert payload.session_id == _SESSION
    slice_ids = {entry["event_id"] for entry in payload.slice["slice"]}
    assert _TOOL_RESULT in slice_ids  # the cited fact fed the claim
    assert _DECISION_BAD not in slice_ids  # the node itself is not in its slice


def test_forward_slice_route_returns_downstream(api_repo_factory):
    """Forward slice of the bad decision contains its downstream decisions.

    The slice runs over evidence-graph nodes — decisions and facts — so the
    raw ERROR event is not a slice entry; the damage it represents is
    carried by the contradicted downstream decision node.
    """
    _seed(api_repo_factory)
    endpoint = _get_route_endpoint("/api/sessions/{session_id}/slices", "GET")

    payload = _call(
        api_repo_factory,
        endpoint,
        session_id=_SESSION,
        node_id=_DECISION_BAD,
        direction="forward",
    )

    slice_ids = {entry["event_id"] for entry in payload.slice["slice"]}
    assert _DECISION_NEXT in slice_ids
    assert _TOOL_RESULT not in slice_ids  # upstream fact is not damage


def test_slice_route_missing_node_returns_empty(api_repo_factory):
    """An unknown node id yields an empty slice, not an error."""
    _seed(api_repo_factory)
    endpoint = _get_route_endpoint("/api/sessions/{session_id}/slices", "GET")

    payload = _call(
        api_repo_factory,
        endpoint,
        session_id=_SESSION,
        node_id="slr-ev-nope",
        direction="backward",
    )

    assert payload.slice["size"] == 0
    assert payload.slice["slice"] == []


# -----------------------------------------------------------------------------
# GET /api/sessions/{session_id}/damage-radius  ->  get_damage_radius
# -----------------------------------------------------------------------------


def test_damage_radius_route_anchored_at_first_bad_decision(api_repo_factory):
    """The radius is the forward slice from the localized first bad decision."""
    _seed(api_repo_factory)
    endpoint = _get_route_endpoint(
        "/api/sessions/{session_id}/damage-radius", "GET"
    )

    payload = _call(api_repo_factory, endpoint, session_id=_SESSION)

    assert payload.radius["available"] is True
    assert payload.radius["first_bad_decision"] == _DECISION_BAD
    radius_ids = {entry["event_id"] for entry in payload.radius["slice"]}
    assert _DECISION_NEXT in radius_ids
    assert _TOOL_RESULT not in radius_ids


def test_damage_radius_route_unavailable_without_bad_decision(api_repo_factory):
    """A clean session with no localized bad decision says so explicitly."""
    async def seed() -> None:
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            clean = Session(
                id="slr-clean-1",
                agent_name="test_agent",
                framework="pytest",
                started_at=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 9, 21, 10, 5, tzinfo=timezone.utc),
                status=SessionStatus.COMPLETED,
                config={"mode": "test"},
                tags=[],
            )
            await repo.create_session(clean)
            await repo.add_event(
                _event(
                    "slr-ev-clean-start",
                    EventType.AGENT_START,
                    name="start",
                    session_id="slr-clean-1",
                )
            )
            await session.commit()

    asyncio.run(seed())
    endpoint = _get_route_endpoint(
        "/api/sessions/{session_id}/damage-radius", "GET"
    )

    async def run():
        async with api_repo_factory() as session:
            repo = TraceRepository(session)
            return await endpoint(session_id="slr-clean-1", repo=repo)

    payload = asyncio.run(run())

    assert payload.radius["available"] is False
    assert payload.radius["first_bad_decision"] is None
    assert "no first bad decision" in payload.radius["reason"]
