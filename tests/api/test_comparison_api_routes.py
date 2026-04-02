"""Tests for comparison API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from api.main import create_app
from storage import TraceRepository


def _make_session(
    session_id: str,
    framework: str = "pytest",
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.COMPLETED,
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=status,
        total_cost_usd=0.50,
        total_tokens=1000,
        llm_calls=5,
        tool_calls=10,
        config={"mode": "test"},
        tags=["comparison-test"],
    )


def _make_event(
    session_id: str,
    event_type: EventType,
    name: str = "test_event",
    **kwargs,
) -> TraceEvent:
    """Factory for creating test events.

    For AGENT_TURN events, pass speaker via data dict: data={"speaker": "agent_name"}
    """
    data = kwargs.pop("data", {})
    metadata = kwargs.pop("metadata", {})
    return TraceEvent(
        session_id=session_id,
        parent_id=kwargs.pop("parent_id", None),
        event_type=event_type,
        name=name,
        data=data,
        metadata=metadata,
        importance=kwargs.pop("importance", 0.5),
        upstream_event_ids=kwargs.pop("upstream_event_ids", []),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_compare_sessions_success():
    """Test successful comparison of two sessions."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Create two sessions with events
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)

            # Primary session
            await repo.create_session(_make_session("compare-primary"))
            await repo.add_event(
                _make_event("compare-primary", EventType.AGENT_TURN, name="turn_1", data={"speaker": "agent_1"})
            )
            await repo.add_event(
                _make_event("compare-primary", EventType.DECISION, name="decision_1", data={"reasoning": "test"})
            )

            # Secondary session
            await repo.create_session(_make_session("compare-secondary"))
            await repo.add_event(
                _make_event("compare-secondary", EventType.AGENT_TURN, name="turn_1", data={"speaker": "agent_2"})
            )
            await repo.add_event(
                _make_event("compare-secondary", EventType.DECISION, name="decision_1", data={"reasoning": "test"})
            )

            await db_session.commit()

        resp = await client.get("/api/compare/compare-primary/compare-secondary")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "primary" in data
        assert "secondary" in data
        assert "comparison_deltas" in data

        # Verify primary session data
        assert "session" in data["primary"]
        assert "policy_analysis" in data["primary"]
        assert "escalation_analysis" in data["primary"]
        assert data["primary"]["session"]["id"] == "compare-primary"

        # Verify secondary session data
        assert "session" in data["secondary"]
        assert "policy_analysis" in data["secondary"]
        assert "escalation_analysis" in data["secondary"]
        assert data["secondary"]["session"]["id"] == "compare-secondary"

        # Verify comparison deltas
        deltas = data["comparison_deltas"]
        assert "turn_count" in deltas
        assert "policy_count" in deltas
        assert "speaker_count" in deltas
        assert "escalation_score" in deltas
        assert "grounding_rate" in deltas


@pytest.mark.asyncio
async def test_compare_sessions_primary_not_found():
    """Test comparison when primary session doesn't exist."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Create only secondary session
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("compare-secondary-only"))
            await db_session.commit()

        resp = await client.get("/api/compare/nonexistent-primary/compare-secondary-only")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_compare_sessions_secondary_not_found():
    """Test comparison when secondary session doesn't exist."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Create only primary session
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("compare-primary-only"))
            await db_session.commit()

        resp = await client.get("/api/compare/compare-primary-only/nonexistent-secondary")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_compare_sessions_both_not_found():
    """Test comparison when neither session exists."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/compare/nonexistent-1/nonexistent-2")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_compare_sessions_with_policy_shifts():
    """Test comparison with policy shift analysis."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)

            # Create sessions with policy events
            await repo.create_session(_make_session("policy-primary"))
            await repo.add_event(_make_event("policy-primary", EventType.PROMPT_POLICY, name="policy_1"))

            await repo.create_session(_make_session("policy-secondary"))
            await repo.add_event(_make_event("policy-secondary", EventType.PROMPT_POLICY, name="policy_2"))

            await db_session.commit()

        resp = await client.get("/api/compare/policy-primary/policy-secondary")
        assert resp.status_code == 200
        data = resp.json()

        # Verify policy analysis structure
        assert "shift_count" in data["primary"]["policy_analysis"]
        assert "avg_shift_magnitude" in data["primary"]["policy_analysis"]
        assert isinstance(data["primary"]["policy_analysis"]["shift_count"], int)


@pytest.mark.asyncio
async def test_compare_sessions_with_escalation_signals():
    """Test comparison with escalation signal analysis."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)

            # Create sessions with escalation-related events
            await repo.create_session(_make_session("escalation-primary"))
            await repo.add_event(_make_event("escalation-primary", EventType.SAFETY_CHECK, name="safety_1"))

            await repo.create_session(_make_session("escalation-secondary"))
            await repo.add_event(_make_event("escalation-secondary", EventType.TOOL_CALL, name="tool_1"))

            await db_session.commit()

        resp = await client.get("/api/compare/escalation-primary/escalation-secondary")
        assert resp.status_code == 200
        data = resp.json()

        # Verify escalation analysis structure
        assert "score" in data["primary"]["escalation_analysis"]
        assert "signal_count" in data["primary"]["escalation_analysis"]
        assert isinstance(data["primary"]["escalation_analysis"]["score"], (int, float))


@pytest.mark.asyncio
async def test_compare_sessions_response_schema():
    """Test comparison response conforms to expected schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-primary"))
            await repo.create_session(_make_session("schema-secondary"))
            await db_session.commit()

        resp = await client.get("/api/compare/schema-primary/schema-secondary")
        assert resp.status_code == 200
        data = resp.json()

        # Verify top-level structure
        assert set(data.keys()) == {"primary", "secondary", "comparison_deltas"}

        # Verify session structure in both primary and secondary
        for key in ["primary", "secondary"]:
            assert set(data[key].keys()) == {"session", "policy_analysis", "escalation_analysis"}
            # Verify session has required fields
            session = data[key]["session"]
            required_fields = ["id", "agent_name", "framework", "status", "started_at"]
            for field in required_fields:
                assert field in session

        # Verify deltas structure
        deltas = data["comparison_deltas"]
        expected_delta_keys = {
            "turn_count",
            "policy_count",
            "speaker_count",
            "stance_shift_count",
            "escalation_count",
            "escalation_score",
            "grounded_decision_count",
            "grounding_rate",
            "avg_shift_magnitude",
        }
        assert set(deltas.keys()) == expected_delta_keys

        # Verify each delta has primary, secondary, and delta
        for delta_key in expected_delta_keys:
            delta_value = deltas[delta_key]
            assert isinstance(delta_value, dict)
            assert set(delta_value.keys()) == {"primary", "secondary", "delta"}
