"""Tests for collector/audit/failure_narrative.py — the XAI explanation bundle.

Covers the structured failure narrative (symptom / mechanism / evidence /
next inspection point) attached to every session audit report: bundle shape
for localized failures, honest weakness when no cause is localized, mode
normalization, contributing factors, determinism, and the HTTP route payload.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api.main import create_app
from collector.audit import SessionAuditEngine
from collector.audit.failure_narrative import (
    UNLOCALIZED_CONFIDENCE_CAP,
    build_failure_narrative,
)
from storage import TraceRepository

# ---------------------------------------------------------------------------
# Helpers (mirror test_audit_engine.py conventions)
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "narrative-session",
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp or datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    chosen_action: str = "act",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        timestamp=timestamp,
        confidence=confidence,
        chosen_action=chosen_action,
        **data,
    )


def _localized_failure_session() -> list[TraceEvent]:
    """A confident decision whose tool call fails — cause is localized to d1."""
    decision = _decision("d1", confidence=0.9, chosen_action="call_api")
    failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d1",
        upstream_event_ids=["d1"],
        tool_name="api",
        error="500",
    )
    return [decision, failure]


# ---------------------------------------------------------------------------
# Bundle presence + shape
# ---------------------------------------------------------------------------


def test_narrative_absent_for_clean_session():
    events = [
        _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 1}),
        _decision("d1", confidence=0.9, evidence_event_ids=["t1"]),
    ]
    narrative = SessionAuditEngine().audit(events)["failure_narrative"]

    assert narrative["available"] is False
    assert narrative["evidence"] == []
    assert narrative["narrative"] == ""
    assert narrative["confidence"] == 0.0


def test_narrative_bundle_structure_for_localized_failure():
    report = SessionAuditEngine().audit(_localized_failure_session())
    narrative = report["failure_narrative"]

    assert narrative["available"] is True
    assert narrative["symptom"]["failure_event_id"] == "f1"
    assert narrative["symptom"]["text"]
    assert narrative["symptom"]["mode"] in {"tool_execution_failure", "ungrounded_decision"}
    assert narrative["symptom"]["mechanism_category"] in {
        "tool_invocation_failed",
        "decision_without_evidence",
    }
    assert narrative["mechanism"]["localized"] is True
    assert narrative["mechanism"]["cause_event_id"]
    # Cause chain contains both the cause and the failure, each exactly once.
    chain_ids = [item["event_id"] for item in narrative["mechanism"]["cause_chain"]]
    assert set(chain_ids) >= {narrative["mechanism"]["cause_event_id"], "f1"}
    assert len(chain_ids) == len(set(chain_ids))
    # Evidence entries anchor back to trace events.
    assert narrative["evidence"]
    assert all(entry["event_id"] in {"d1", "f1"} for entry in narrative["evidence"])
    assert all(entry["why"] for entry in narrative["evidence"])
    # Next inspection points somewhere concrete with a suggested action.
    assert narrative["next_inspection"]["event_id"]
    assert narrative["next_inspection"]["why"]
    assert narrative["next_inspection"]["suggested_action"]
    assert narrative["confidence"] > UNLOCALIZED_CONFIDENCE_CAP
    assert narrative["weakness"] is None
    assert narrative["narrative"].startswith("Symptom:")


def test_narrative_next_inspection_prefers_localized_cause():
    report = SessionAuditEngine().audit(_localized_failure_session())
    narrative = report["failure_narrative"]

    assert narrative["mechanism"]["cause_event_id"] == "d1"
    assert narrative["next_inspection"]["event_id"] == "d1"
    assert "decision justification" in narrative["next_inspection"]["suggested_action"]


def test_narrative_included_in_report_and_matches_standalone_builder():
    events = _localized_failure_session()
    report = SessionAuditEngine().audit(events)

    assert report["failure_narrative"] == build_failure_narrative(events, report)


# ---------------------------------------------------------------------------
# Honest uncertainty when localization is weak
# ---------------------------------------------------------------------------


def test_narrative_caps_confidence_when_no_cause_localized():
    # An orphan failure with no upstream links — diagnostics finds no candidate.
    events = [_event("f1", EventType.TOOL_RESULT, tool_name="api", error="500")]
    narrative = SessionAuditEngine().audit(events)["failure_narrative"]

    assert narrative["available"] is True
    assert narrative["mechanism"]["localized"] is False
    assert narrative["mechanism"]["cause_event_id"] is None
    assert narrative["confidence"] <= UNLOCALIZED_CONFIDENCE_CAP
    assert narrative["weakness"] is not None
    assert "symptom-only" in narrative["weakness"]
    # Falls back to the failure event itself as the inspection point.
    assert narrative["next_inspection"]["event_id"] == "f1"
    assert "success-flow" in narrative["next_inspection"]["suggested_action"]


# ---------------------------------------------------------------------------
# Mode normalization + contributing factors
# ---------------------------------------------------------------------------


def test_narrative_normalizes_guardrail_mode_category():
    refusal = _event("r1", EventType.REFUSAL, reason="would exfiltrate secrets")
    narrative = SessionAuditEngine().audit([refusal])["failure_narrative"]

    assert narrative["symptom"]["mode"] == "guardrail_block"
    assert narrative["symptom"]["mechanism_category"] == "guardrail_or_policy_block"


def test_narrative_lists_contributing_factors_from_signals():
    # Same tool failing twice triggers the repeated_failed_strategy signal;
    # the confident decision before the failure is contradicted.
    decision = _decision("d1", confidence=0.9, chosen_action="call_api")
    first_failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d1",
        upstream_event_ids=["d1"],
        tool_name="deploy",
        error="timeout",
    )
    second_failure = _event(
        "f2",
        EventType.TOOL_RESULT,
        parent_id="d1",
        upstream_event_ids=["d1"],
        tool_name="deploy",
        error="timeout",
    )
    narrative = SessionAuditEngine().audit([decision, first_failure, second_failure])[
        "failure_narrative"
    ]

    factor_types = {factor["type"] for factor in narrative["mechanism"]["contributing_factors"]}
    assert "repeated_failed_strategy" in factor_types
    labels = {factor["label"] for factor in narrative["mechanism"]["contributing_factors"]}
    assert "repeated failed strategy" in labels
    # Every contributing factor points at a real event in the trace.
    for factor in narrative["mechanism"]["contributing_factors"]:
        assert factor["event_id"] in {"d1", "f1", "f2"}


def test_narrative_adds_goal_drift_factor_when_drifted():
    goal = _event("a1", EventType.AGENT_START, goal="migrate billing database")
    on_topic = _decision(
        "d1",
        confidence=0.6,
        chosen_action="inspect billing schema",
        reasoning="migrate billing database step",
    )
    off_topic_1 = _decision(
        "d2", confidence=0.6, chosen_action="read the news", reasoning="check headlines"
    )
    off_topic_2 = _decision(
        "d3", confidence=0.6, chosen_action="nap", reasoning="sleep a while"
    )
    failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d3",
        upstream_event_ids=["d3"],
        tool_name="deploy",
        error="boom",
    )
    narrative = SessionAuditEngine().audit([goal, on_topic, off_topic_1, off_topic_2, failure])[
        "failure_narrative"
    ]

    factor_types = {factor["type"] for factor in narrative["mechanism"]["contributing_factors"]}
    assert "goal_drift" in factor_types


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_narrative_is_deterministic():
    events = _localized_failure_session()
    engine = SessionAuditEngine()
    first = engine.audit(copy.deepcopy(events))["failure_narrative"]
    second = engine.audit(copy.deepcopy(events))["failure_narrative"]
    assert first == second


# ---------------------------------------------------------------------------
# HTTP route end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_route_includes_failure_narrative(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = "narrative-route-session"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(
                Session(
                    id=session_id,
                    agent_name="narrative_agent",
                    framework="pytest",
                    started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
                    status=SessionStatus.COMPLETED,
                    config={},
                    tags=["narrative-route-test"],
                )
            )
            decision = TraceEvent(
                id="nr-decision",
                session_id=session_id,
                name="decide",
                event_type=EventType.DECISION,
                timestamp=datetime(2026, 3, 26, 10, 6, tzinfo=timezone.utc),
                data={"confidence": 0.9, "chosen_action": "call_api"},
            )
            failure = TraceEvent(
                id="nr-failure",
                session_id=session_id,
                parent_id="nr-decision",
                name="api",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 7, tzinfo=timezone.utc),
                data={"tool_name": "api", "error": "500"},
            )
            await repo.add_event(decision)
            await repo.add_event(failure)
            await db_session.commit()

        resp = await client.get(f"/api/sessions/{session_id}/audit")
        assert resp.status_code == 200
        narrative = resp.json()["audit"]["failure_narrative"]
        assert narrative["available"] is True
        assert narrative["symptom"]["failure_event_id"] == "nr-failure"
        assert narrative["next_inspection"]["event_id"]
