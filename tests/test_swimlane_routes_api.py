"""Tests for multi-agent swimlane API routes (api/swimlane_routes.py).

The SDK swimlane analyzers are covered by tests/test_swimlane.py; these tests
cover the HTTP layer: swimlane visualization, inter-agent message flows,
coordination analysis, emergent behavior detection, and the combined
multi-agent analysis endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import (
    DecisionEvent,
    Session,
    SessionStatus,
    ToolCallEvent,
    ToolResultEvent,
)
from agent_debugger_sdk.core.swimlane import (
    CoordinationIssue,
    CoordinationSeverity,
    EmergentBehavior,
    EmergentBehaviorType,
    IssueReport,
    MessageFlow,
    MessageFlowType,
)
from api.main import create_app
from storage import TraceRepository
from tests.conftest import unique_id

BASE_TIME = datetime(2026, 4, 11, 8, 0, tzinfo=timezone.utc)


def _make_session(session_id: str) -> Session:
    return Session(
        id=session_id,
        agent_name="orchestrator",
        framework="pytest",
        started_at=BASE_TIME,
        ended_at=BASE_TIME.replace(minute=10),
        status=SessionStatus.COMPLETED,
        total_cost_usd=0.20,
        total_tokens=200,
        llm_calls=3,
        tool_calls=2,
        config={"mode": "test"},
        tags=["swimlane-api-test"],
    )


def _eid(session_id: str, name: str) -> str:
    """Event ids are derived from the unique session id to avoid collisions
    in the shared persistent test database."""
    return f"{session_id}-{name}"


def _multi_agent_events(session_id: str) -> list:
    """Two-agent interaction: agent_1 delegates, agent_2 responds."""
    return [
        ToolCallEvent(
            id=_eid(session_id, "tool1"),
            session_id=session_id,
            timestamp=BASE_TIME,
            name="Agent 1 delegates to Agent 2",
            data={"agent_id": "agent_1"},
            tool_name="delegate_to_agent_2",
            arguments={"task": "analyze"},
        ),
        ToolResultEvent(
            id=_eid(session_id, "result1"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(second=5),
            parent_id=_eid(session_id, "tool1"),
            name="Agent 2 responds",
            data={"agent_id": "agent_2"},
            upstream_event_ids=[_eid(session_id, "tool1")],
            tool_name="delegate_to_agent_2",
            result={"status": "completed"},
        ),
        DecisionEvent(
            id=_eid(session_id, "decision1"),
            session_id=session_id,
            timestamp=BASE_TIME.replace(second=10),
            name="Agent 1 decision",
            data={"agent_id": "agent_1"},
            reasoning="Delegating the analysis task",
            confidence=0.8,
        ),
    ]


@pytest.fixture
async def session_id() -> str:
    from api import app_context

    session_id = unique_id("swimapi")
    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session(session_id))
        for event in _multi_agent_events(session_id):
            await repo.add_event(event)
        await db_session.commit()
    return session_id


@pytest.mark.asyncio
async def test_swimlane_visualization_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/swimlane")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id

    swimlane = data["swimlane_data"]
    assert swimlane["session_id"] == session_id
    assert isinstance(swimlane["lanes"], dict)
    assert "agent_1" in swimlane["lanes"]
    assert "agent_2" in swimlane["lanes"]
    assert swimlane["lanes"]["agent_1"]["event_count"] == 2
    assert swimlane["lanes"]["agent_2"]["event_count"] == 1
    assert isinstance(swimlane["message_flows"], list)


@pytest.mark.asyncio
async def test_swimlane_visualization_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/swimapi-missing/swimlane")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inter_agent_messages_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id

    flows = data["message_flows"]
    assert len(flows) >= 1
    flow_ids = {f["from_agent_id"] for f in flows}
    assert "agent_1" in flow_ids

    summary = data["flow_summary"]
    assert summary["total_flows"] == len(flows)
    assert isinstance(summary["flow_types"], dict)
    assert summary["most_active_pair"] is not None
    pair = summary["most_active_pair"]["pair"]
    assert pair.startswith("agent_1->") or "->agent_1" in pair


@pytest.mark.asyncio
async def test_inter_agent_messages_no_flows(shared_app):
    import uuid

    from api import app_context

    session_id = f"swimapi-single-{uuid.uuid4().hex[:8]}"
    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session(session_id))
        await repo.add_event(
            DecisionEvent(
                session_id=session_id,
                timestamp=BASE_TIME,
                name="solo decision",
                data={"agent_id": "solo_agent"},
                reasoning="Working alone",
                confidence=0.9,
            )
        )
        await db_session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert data["message_flows"] == []
    summary = data["flow_summary"]
    assert summary == {
        "total_flows": 0,
        "flow_types": {},
        "agent_pairs": {},
        "most_active_pair": None,
    }


@pytest.mark.asyncio
async def test_coordination_analysis_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/sessions/{session_id}/coordination-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert isinstance(data["coordination_issues"], list)

    summary = data["summary"]
    assert summary["total_issues"] == len(data["coordination_issues"])
    assert isinstance(summary["by_severity"], dict)
    assert isinstance(summary["by_type"], dict)
    assert isinstance(summary["critical_issues"], list)


@pytest.mark.asyncio
async def test_coordination_analysis_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/sessions/swimapi-missing/coordination-analysis")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_emergent_behaviors_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/sessions/{session_id}/emergent-behaviors")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert isinstance(data["emergent_behaviors"], list)

    summary = data["summary"]
    assert summary["total_behaviors"] == len(data["emergent_behaviors"])
    assert isinstance(summary["by_type"], dict)
    assert 0.0 <= summary["avg_confidence"] <= 1.0
    # Only behaviors with confidence >= 0.7 are highlighted
    for behavior in summary["high_confidence_behaviors"]:
        assert behavior["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_emergent_behaviors_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/sessions/swimapi-missing/emergent-behaviors")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multi_agent_analysis_success(shared_app, session_id):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{session_id}/multi-agent-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id

    info = data["session_info"]
    assert info["agent_name"] == "orchestrator"
    assert info["framework"] == "pytest"

    swimlane = data["swimlane_data"]
    assert swimlane["agent_count"] == 2

    assert "issues" in data["coordination_analysis"]
    assert "summary" in data["coordination_analysis"]
    assert "behaviors" in data["emergent_behavior_analysis"]
    assert "summary" in data["emergent_behavior_analysis"]


@pytest.mark.asyncio
async def test_multi_agent_analysis_missing_session(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/swimapi-missing/multi-agent-analysis")

    assert resp.status_code == 404


# =============================================================================
# Helper unit tests (no database)
# =============================================================================


def _make_flow(from_agent: str, to_agent: str, flow_type=MessageFlowType.DELEGATION):
    return MessageFlow(
        from_agent_id=from_agent,
        to_agent_id=to_agent,
        flow_type=flow_type,
        event_id="evt",
        description="test flow",
    )


def test_analyze_message_flows_empty():
    from api.swimlane_routes import _analyze_message_flows

    assert _analyze_message_flows([]) == {
        "total_flows": 0,
        "flow_types": {},
        "agent_pairs": {},
        "most_active_pair": None,
    }


def test_analyze_message_flows_counts_and_most_active_pair():
    from api.swimlane_routes import _analyze_message_flows

    flows = [
        _make_flow("a", "b"),
        _make_flow("a", "b"),
        _make_flow("b", "a", MessageFlowType.RESPONSE),
    ]
    result = _analyze_message_flows([f.to_dict() for f in flows])

    assert result["total_flows"] == 3
    assert result["flow_types"]["delegation"] == 2
    assert result["flow_types"]["response"] == 1
    assert result["agent_pairs"]["a->b"] == 2
    assert result["most_active_pair"] == {"pair": "a->b", "count": 2}


def test_analyze_message_flows_ignores_incomplete_pairs():
    from api.swimlane_routes import _analyze_message_flows

    flows = [_make_flow("a", "")]  # no destination agent
    result = _analyze_message_flows([f.to_dict() for f in flows])
    assert result["total_flows"] == 1
    assert result["agent_pairs"] == {}
    assert result["most_active_pair"] is None


def test_generate_coordination_summary_empty():
    from api.swimlane_routes import _generate_coordination_summary

    assert _generate_coordination_summary([]) == {
        "total_issues": 0,
        "by_severity": {},
        "by_type": {},
        "critical_issues": [],
    }


def test_generate_coordination_summary_with_critical_issue():
    from api.swimlane_routes import _generate_coordination_summary

    issues = [
        IssueReport(
            issue_type=CoordinationIssue.DEADLOCK,
            severity=CoordinationSeverity.CRITICAL,
            involved_agents=["a", "b"],
            description="mutual wait",
        ),
        IssueReport(
            issue_type=CoordinationIssue.COMMUNICATION_GAP,
            severity=CoordinationSeverity.MEDIUM,
            involved_agents=["b"],
            description="missing ack",
        ),
    ]
    summary = _generate_coordination_summary(issues)

    assert summary["total_issues"] == 2
    assert summary["by_severity"] == {"critical": 1, "medium": 1}
    assert summary["by_type"] == {"deadlock": 1, "communication_gap": 1}
    assert len(summary["critical_issues"]) == 1
    assert summary["critical_issues"][0]["description"] == "mutual wait"


def test_generate_emergent_behavior_summary_empty():
    from api.swimlane_routes import _generate_emergent_behavior_summary

    assert _generate_emergent_behavior_summary([]) == {
        "total_behaviors": 0,
        "by_type": {},
        "high_confidence_behaviors": [],
        "avg_confidence": 0.0,
    }


def test_generate_emergent_behavior_summary_mixed_confidence():
    from api.swimlane_routes import _generate_emergent_behavior_summary

    behaviors = [
        EmergentBehavior(
            behavior_type=EmergentBehaviorType.COLLABORATIVE_PROBLEM_SOLVING,
            confidence=0.9,
            involved_agents=["a", "b"],
        ),
        EmergentBehavior(
            behavior_type=EmergentBehaviorType.EMERGENT_HIERARCHY,
            confidence=0.4,
            involved_agents=["a"],
        ),
    ]
    summary = _generate_emergent_behavior_summary(behaviors)

    assert summary["total_behaviors"] == 2
    assert summary["by_type"]["collaborative_problem_solving"] == 1
    assert summary["avg_confidence"] == pytest.approx(0.65)
    # Only the 0.9-confidence behavior passes the 0.7 threshold
    assert len(summary["high_confidence_behaviors"]) == 1
    assert (
        summary["high_confidence_behaviors"][0]["behavior_type"]
        == "collaborative_problem_solving"
    )
