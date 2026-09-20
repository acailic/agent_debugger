"""Tests for research feature API routes (api/research_routes.py).

Covers the three research-inspired feature groups end-to-end over a seeded
database session:

1. Frame Lifetime Trace — /frames and /frames/tree
2. Backward Failure Attribution — /failures/causes and /failures/similar
3. Conformal Prediction Scoring — /uncertainty, /prediction-intervals, /risk-assessment
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import (
    DecisionEvent,
    EventType,
    Session,
    SessionStatus,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from api.main import create_app
from storage import TraceRepository
from tests.conftest import unique_id

BASE_TIME = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)


def _make_session(session_id: str) -> Session:
    return Session(
        id=session_id,
        agent_name="research_agent",
        framework="pytest",
        started_at=BASE_TIME,
        ended_at=BASE_TIME.replace(hour=10),
        status=SessionStatus.COMPLETED,
        total_cost_usd=0.10,
        total_tokens=100,
        llm_calls=2,
        tool_calls=2,
        config={"mode": "test"},
        tags=["research-api-test"],
    )


def _eid(session_id: str, name: str) -> str:
    """Event ids are derived from the unique session id to avoid collisions
    in the shared persistent test database."""
    return f"{session_id}-{name}"


def _research_events(session_id: str) -> list[TraceEvent]:
    """Events forming a 3-level frame hierarchy plus decisions and an error.

    Frame chain: evt_root -> evt_child -> evt_grandchild.
    evt_decision_low (confidence 0.2) and evt_decision_hi (confidence 0.95)
    feed the uncertainty/conformal endpoints.
    """
    return [
        ToolCallEvent(
            id=_eid(session_id, "root"),
            session_id=session_id,
            timestamp=BASE_TIME,
            name="outer_tool",
            data={},
            tool_name="search",
            arguments={"q": "root"},
        ),
        ToolResultEvent(
            id=_eid(session_id, "child"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(minute=1),
            parent_id=_eid(session_id, "root"),
            name="outer_tool_result",
            data={},
            upstream_event_ids=[_eid(session_id, "root")],
            tool_name="search",
            result={"hits": 1},
        ),
        DecisionEvent(
            id=_eid(session_id, "grandchild"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(minute=2),
            parent_id=_eid(session_id, "child"),
            name="act_on_result",
            data={},
            reasoning="Result looked relevant",
            confidence=0.2,
        ),
        DecisionEvent(
            id=_eid(session_id, "decision_hi"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(minute=3),
            name="final_decision",
            data={},
            reasoning="Clear evidence",
            confidence=0.95,
        ),
        TraceEvent(
            id=_eid(session_id, "error"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(minute=4),
            event_type=EventType.ERROR,
            name="tool_failed",
            data={"error": "connection refused"},
        ),
    ]


async def _seed_research_session() -> str:
    """Seed a fresh session with a unique id and return it."""
    from api import app_context

    session_id = unique_id("researchapi")
    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session(session_id))
        for event in _research_events(session_id):
            await repo.add_event(event)
        await db_session.commit()
    return session_id


@pytest.fixture
async def session_id() -> str:
    return await _seed_research_session()


# =============================================================================
# Feature 1: Frame Lifetime Trace
# =============================================================================


@pytest.mark.asyncio
async def test_get_session_frames_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/frames")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id

    frames = data["frames"]
    assert len(frames) == 5
    by_id = {f["event_id"]: f for f in frames}
    assert by_id[_eid(session_id, "root")]["depth"] == 0
    assert by_id[_eid(session_id, "child")]["depth"] == 1
    assert by_id[_eid(session_id, "grandchild")]["depth"] == 2
    assert by_id[_eid(session_id, "root")]["function_name"] == "outer_tool"
    assert by_id[_eid(session_id, "error")]["event_type"] == "error"

    summary = data["summary"]
    assert summary["total_frames"] == 5
    assert summary["max_depth"] == 2
    assert summary["total_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_get_session_frames_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/researchapi-missing/frames")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_frame_tree_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/frames/tree")

    assert resp.status_code == 200
    tree = resp.json()["tree"]
    # Roots are ordered by timestamp; the root tool call is the first parentless event.
    assert tree["event_id"] == _eid(session_id, "root")
    child = tree["children"][0]
    assert child["event_id"] == _eid(session_id, "child")
    assert child["children"][0]["event_id"] == _eid(session_id, "grandchild")


@pytest.mark.asyncio
async def test_get_frame_tree_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/researchapi-missing/frames/tree")

    assert resp.status_code == 404


# =============================================================================
# Feature 2: Backward Failure Attribution
# =============================================================================


@pytest.mark.asyncio
async def test_get_failure_causes_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/failures/causes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["failure_event_id"] is None
    assert isinstance(data["causal_graph"], dict)
    assert isinstance(data["critical_paths"], dict)
    assert isinstance(data["root_causes"], list)


@pytest.mark.asyncio
async def test_get_failure_causes_with_explicit_event(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}/failures/causes",
            params={"failure_event_id": _eid(session_id, "error")},
        )

    assert resp.status_code == 200
    assert resp.json()["failure_event_id"] == _eid(session_id, "error")


@pytest.mark.asyncio
async def test_get_failure_causes_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/researchapi-missing/failures/causes")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_similar_failures_contract(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}/failures/similar",
            params={"failure_event_id": _eid(session_id, "error"), "limit": 3},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["failure_event_id"] == _eid(session_id, "error")
    assert isinstance(data["similar_failures"], list)
    assert data["total"] == len(data["similar_failures"])
    assert data["total"] <= 3


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_limit", [0, 11])
async def test_get_similar_failures_limit_validation(shared_app, bad_limit):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions/researchapi-validation/failures/similar",
            params={"failure_event_id": "evt_error", "limit": bad_limit},
        )

    assert resp.status_code == 422


# =============================================================================
# Feature 3: Conformal Prediction Scoring
# =============================================================================


@pytest.mark.asyncio
async def test_get_uncertainty_analysis(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/uncertainty")

    assert resp.status_code == 200
    data = resp.json()

    scores = {s["event_id"]: s for s in data["uncertainty_scores"]}
    # Only events carrying a confidence attribute contribute.
    assert set(scores) == {_eid(session_id, "grandchild"), _eid(session_id, "decision_hi")}
    assert scores[_eid(session_id, "grandchild")]["confidence"] == pytest.approx(0.2)
    assert scores[_eid(session_id, "grandchild")]["uncertainty"] == pytest.approx(0.8)
    assert scores[_eid(session_id, "decision_hi")]["uncertainty"] == pytest.approx(0.05)

    summary = data["summary"]
    assert summary["total_decisions"] == 2
    assert summary["high_uncertainty_count"] == 1
    assert summary["average_uncertainty"] == pytest.approx(0.425)
    # 0.3 < average 0.425 <= 0.5 -> medium
    assert summary["risk_level"] == "medium"


@pytest.mark.asyncio
async def test_get_uncertainty_analysis_without_confidence(shared_app):
    import uuid

    from api import app_context

    session_id = f"researchapi-noconf-{uuid.uuid4().hex[:8]}"
    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session(session_id))
        await repo.add_event(
            TraceEvent(
                session_id=session_id,
                timestamp=BASE_TIME,
                event_type=EventType.TOOL_CALL,
                name="plain_call",
            )
        )
        await db_session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/uncertainty")

    assert resp.status_code == 200
    data = resp.json()
    assert data["uncertainty_scores"] == []
    assert data["summary"]["total_decisions"] == 0
    assert data["summary"]["average_uncertainty"] == 0.0
    assert data["summary"]["risk_level"] == "low"


@pytest.mark.asyncio
async def test_get_prediction_intervals(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}/prediction-intervals",
            params={"confidence_level": 0.9},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence_level"] == pytest.approx(0.9)

    intervals = {p["event_id"]: p for p in data["prediction_intervals"]}
    assert set(intervals) == {_eid(session_id, "grandchild"), _eid(session_id, "decision_hi")}

    # margin = (1 - confidence) * confidence_level, clamped to [0, 1]
    low = intervals[_eid(session_id, "grandchild")]
    assert low["lower_bound"] == pytest.approx(0.0)  # clamped: 0.2 - 0.72 < 0
    assert low["upper_bound"] == pytest.approx(0.92)

    high = intervals[_eid(session_id, "decision_hi")]
    assert high["lower_bound"] == pytest.approx(0.905)
    assert high["upper_bound"] == pytest.approx(0.995)

    stats = data["coverage_statistics"]
    assert stats["total_intervals"] == 2
    assert stats["average_width"] == pytest.approx((0.92 + 0.09) / 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_level", [0.4, 1.0])
async def test_get_prediction_intervals_validation(shared_app, bad_level):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions/researchapi-validation/prediction-intervals",
            params={"confidence_level": bad_level},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_risk_assessment_high_risk(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/risk-assessment")

    assert resp.status_code == 200
    data = resp.json()

    # High-risk: evt_grandchild (uncertainty 0.8) and evt_error (error type).
    # Low-risk: evt_root, evt_child (no confidence -> 1.0), evt_decision_hi (0.05).
    dist = data["risk_distribution"]
    assert dist["high"] == 2
    assert dist["medium"] == 0
    assert dist["low"] == 3

    high_ids = {e["event_id"] for e in data["high_risk_events"]}
    assert high_ids == {_eid(session_id, "grandchild"), _eid(session_id, "error")}

    # 2/5 = 0.4 high-risk ratio -> overall high
    assert data["overall_risk"] == "high"

    recommendations = data["recommendations"]
    assert "Review high-uncertainty decisions before deployment" in recommendations
    # high_risk_ratio 0.4 > 0.15 adds the retraining recommendation
    assert any("risky events" in r for r in recommendations)


@pytest.mark.asyncio
async def test_get_risk_assessment_low_risk(shared_app):
    import uuid

    from api import app_context

    session_id = f"researchapi-lowrisk-{uuid.uuid4().hex[:8]}"
    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session(session_id))
        await repo.add_event(
            DecisionEvent(
                session_id=session_id,
                timestamp=BASE_TIME,
                name="confident_decision",
                reasoning="certain",
                confidence=0.99,
            )
        )
        await db_session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/risk-assessment")

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_risk"] == "low"
    assert data["risk_distribution"]["low"] == 1
    assert any("low-risk" in r for r in data["recommendations"])


@pytest.mark.asyncio
async def test_get_risk_assessment_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/researchapi-missing/risk-assessment")

    assert resp.status_code == 404


# =============================================================================
# Helper unit tests (no database)
# =============================================================================


def test_calculate_frame_depth_orphan_parent():
    from api.services.research import calculate_frame_depth

    event = TraceEvent(
        id="orphan",
        session_id="s",
        timestamp=BASE_TIME,
        event_type=EventType.TOOL_CALL,
        parent_id="ghost",
        name="orphan",
    )
    # Parent not in event list -> depth stops at 0
    assert calculate_frame_depth(event, [event]) == 0


def test_build_frame_tree_empty_events():
    from api.services.research import build_frame_tree

    assert build_frame_tree([]) == {}


def test_generate_risk_recommendations_levels():
    from api.services.research import generate_risk_recommendations

    high = generate_risk_recommendations("high", 0.05)
    assert len(high) == 3

    medium = generate_risk_recommendations("medium", 0.05)
    assert len(medium) == 2

    low = generate_risk_recommendations("low", 0.05)
    assert len(low) == 2

    # Ratio above 0.15 appends one extra recommendation
    escalated = generate_risk_recommendations("low", 0.2)
    assert len(escalated) == 3
