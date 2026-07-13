"""Tests for collector/audit/audit_engine.py — SessionAuditEngine.

Covers the agent audit layer: the five-question report structure, claim
verification statuses, deterministic risk signals, failure localization
reuse, and the explainable trust score. Also exercises the
``GET /api/sessions/{id}/audit`` route end-to-end.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api.main import create_app
from collector.audit import SessionAuditEngine
from storage import TraceRepository

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "audit-session",
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    **data,
) -> TraceEvent:
    """Build a base TraceEvent carrying typed fields in its data dict.

    The audit engine reads fields via ``event_value`` (attr then data), so a
    base event with a data dict exercises the same code path as the typed
    subclasses reconstructed from storage.
    """
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    evidence_event_ids: list[str] | None = None,
    evidence: list[dict] | None = None,
    chosen_action: str = "act",
    reasoning: str = "",
    parent_id: str | None = None,
    alternatives: list | None = None,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        confidence=confidence,
        evidence_event_ids=evidence_event_ids or [],
        evidence=evidence or [],
        chosen_action=chosen_action,
        reasoning=reasoning,
        alternatives=alternatives or [],
    )


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------


def test_empty_session_returns_well_formed_report():
    engine = SessionAuditEngine()
    report = engine.audit([])

    assert report["session_id"] == ""
    assert report["claims"] == []
    assert report["failures"] == []
    assert set(report["questions"]) == {
        "what_happened",
        "why",
        "evidence",
        "outcome",
        "where_it_failed",
    }
    assert 0.0 <= report["trust"]["score"] <= 1.0
    assert report["trust"]["band"] in {"low", "medium", "high"}
    assert "explanation" in report["trust"]


def test_report_answers_all_five_questions():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 2})
    decision = _decision(
        "d1",
        confidence=0.9,
        evidence_event_ids=["t1"],
        chosen_action="answer",
        reasoning="grounded in search results",
    )
    report = SessionAuditEngine().audit([tool, decision])

    assert report["questions"]["what_happened"]["tool_calls"] == 0
    assert report["questions"]["what_happened"]["tool_results"] == 1
    assert report["questions"]["what_happened"]["decisions"] == 1
    assert report["questions"]["why"]["decisions_with_rationale"][0]["rationale"] == "grounded in search results"
    assert report["questions"]["evidence"]["tool_backed_facts"] == 1
    assert report["questions"]["outcome"]["success_count"] == 1
    assert report["questions"]["where_it_failed"]["first_failure"] is None


# ---------------------------------------------------------------------------
# Verification status
# ---------------------------------------------------------------------------


def test_decision_backed_by_successful_tool_result_is_verified():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 2})
    decision = _decision("d1", confidence=0.9, evidence_event_ids=["t1"])
    report = SessionAuditEngine().audit([tool, decision])

    claim = report["claims"][0]
    assert claim["verification_status"] == "verified"
    assert "tool result" in claim["verification_basis"]
    assert claim["contradicted"] is False


def test_decision_with_unresolvable_evidence_is_partially_verified():
    decision = _decision(
        "d1",
        confidence=0.8,
        evidence_event_ids=["does-not-exist"],
        evidence=[{"source": "model_memory", "content": "vague"}],
    )
    report = SessionAuditEngine().audit([decision])

    assert report["claims"][0]["verification_status"] == "partially_verified"


def test_confident_decision_without_evidence_is_unsupported():
    decision = _decision("d1", confidence=0.85)
    report = SessionAuditEngine().audit([decision])

    claim = report["claims"][0]
    assert claim["verification_status"] == "unsupported"
    signal_types = {signal["type"] for signal in report["signals"]}
    assert "unsupported_claim" in signal_types
    assert "confidence_evidence_mismatch" in signal_types


def test_low_confidence_decision_without_evidence_is_unverified():
    decision = _decision("d1", confidence=0.2)
    report = SessionAuditEngine().audit([decision])

    assert report["claims"][0]["verification_status"] == "unverified"


def test_confident_decision_whose_subtree_fails_is_contradicted():
    # Confident decision directly causes a failed tool result.
    decision = _decision("d1", confidence=0.9, chosen_action="delete_records")
    failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d1",
        tool_name="db",
        error="permission denied",
    )
    report = SessionAuditEngine().audit([decision, failure])

    statuses = {claim["event_id"]: claim["verification_status"] for claim in report["claims"]}
    assert statuses["d1"] == "contradicted"
    signal_types = {signal["type"] for signal in report["signals"]}
    assert "contradiction" in signal_types


# ---------------------------------------------------------------------------
# Risk signals
# ---------------------------------------------------------------------------


def test_repeated_failed_tool_strategy_is_flagged():
    events = [
        _event("f1", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"),
        _event("f2", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"),
        _event("f3", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"),
    ]
    report = SessionAuditEngine().audit(events)

    repeat_signals = [s for s in report["signals"] if s["type"] == "repeated_failed_strategy"]
    assert len(repeat_signals) == 1
    assert repeat_signals[0]["severity"] == "high"
    assert "uploader" in repeat_signals[0]["message"]


def test_drift_event_emits_plan_drift_signal():
    drift = _event("dr1", EventType.DRIFT, signal="agent abandoned the plan")
    report = SessionAuditEngine().audit([drift])
    assert any(s["type"] == "plan_drift" for s in report["signals"])


def test_policy_violation_emits_signal_and_lowers_compliance():
    decision = _decision("d1", confidence=0.9, evidence_event_ids=[])
    violation = _event("v1", EventType.POLICY_VIOLATION, violation_type="unsafe_action")
    report = SessionAuditEngine().audit([decision, violation])

    assert any(s["type"] == "policy_violation" for s in report["signals"])
    assert report["trust"]["components"]["policy_compliance"] < 1.0


# ---------------------------------------------------------------------------
# Trust score
# ---------------------------------------------------------------------------


def test_grounding_raises_trust_relative_to_unsupported():
    grounded = SessionAuditEngine().audit(
        [
            _event("t1", EventType.TOOL_RESULT, tool_name="s", result={}),
            _decision("d1", confidence=0.9, evidence_event_ids=["t1"]),
        ]
    )
    unsupported = SessionAuditEngine().audit([_decision("d1", confidence=0.9)])
    assert grounded["trust"]["score"] > unsupported["trust"]["score"]
    assert grounded["trust"]["band"] in {"medium", "high"}
    assert unsupported["trust"]["band"] == "low"


def test_trust_explanation_names_every_component():
    report = SessionAuditEngine().audit([_decision("d1", confidence=0.5)])
    explanation = report["trust"]["explanation"]
    for token in [
        "evidence_coverage",
        "verification_rate",
        "policy_compliance",
        "recovery_rate",
        "failure_severity",
        "contradictions",
    ]:
        assert token in explanation


def test_trust_score_is_bounded_and_explainable():
    report = SessionAuditEngine().audit([_decision("d1", confidence=0.95)])
    score = report["trust"]["score"]
    assert 0.0 <= score <= 1.0
    components = report["trust"]["components"]
    for key in (
        "evidence_coverage",
        "verification_rate",
        "contradiction_count",
        "failure_severity",
        "recovery_rate",
        "policy_compliance",
        "decision_count",
        "failure_count",
    ):
        assert key in components


# ---------------------------------------------------------------------------
# Failures + review points
# ---------------------------------------------------------------------------


def test_failures_localize_root_cause_from_diagnostics():
    decision = _decision("d1", confidence=0.9, chosen_action="call_api")
    failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d1",
        upstream_event_ids=["d1"],
        tool_name="api",
        error="500",
    )
    report = SessionAuditEngine().audit([decision, failure])

    assert len(report["failures"]) >= 1
    failure_entry = report["failures"][0]
    assert failure_entry["event_id"] == "f1"
    assert failure_entry["mode"]  # populated by FailureDiagnostics


def test_review_points_prioritize_unsupported_and_failed():
    decision = _decision("d1", confidence=0.9, chosen_action="guess")
    report = SessionAuditEngine().audit([decision])
    priorities = [point["priority"] for point in report["review_points"]]
    assert "high" in priorities


def test_critical_decisions_include_high_confidence_and_unsupported():
    events = [
        _decision("d1", confidence=0.95, evidence_event_ids=["t1"]),
        _event("t1", EventType.TOOL_RESULT, tool_name="s", result={}),
        _decision("d2", confidence=0.9),
    ]
    report = SessionAuditEngine().audit(events)
    critical_ids = {claim["event_id"] for claim in report["critical_decisions"]}
    assert critical_ids == {"d1", "d2"}


# ---------------------------------------------------------------------------
# Determinism + invariance
# ---------------------------------------------------------------------------


def test_audit_is_deterministic_for_identical_input():
    events = [
        _event("t1", EventType.TOOL_RESULT, tool_name="s", result={}),
        _decision("d1", confidence=0.9, evidence_event_ids=["t1"], reasoning="r"),
        _event("f1", EventType.TOOL_RESULT, tool_name="db", error="x"),
    ]
    engine = SessionAuditEngine()
    first = engine.audit(copy.deepcopy(events))
    second = engine.audit(copy.deepcopy(events))
    assert first == second


def test_objective_inferred_from_goal_then_content():
    goal_event = _event("a1", EventType.AGENT_START, goal="resolve customer ticket")
    report = SessionAuditEngine().audit([goal_event])
    assert report["objective"] == "resolve customer ticket"

    content_event = _event("a2", EventType.AGENT_TURN, content="What is my balance?")
    report2 = SessionAuditEngine().audit([content_event])
    assert report2["objective"] == "What is my balance?"


# ---------------------------------------------------------------------------
# HTTP route end-to-end
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "audit-route-session") -> Session:
    return Session(
        id=session_id,
        agent_name="audit_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_cost_usd=0.1,
        total_tokens=100,
        llm_calls=1,
        tool_calls=2,
        config={"mode": "test"},
        tags=["audit-route-test"],
    )


@pytest.mark.asyncio
async def test_audit_route_returns_report(shared_app):
    """GET /api/sessions/{id}/audit returns a full audit report over the wire."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session())
            tool = TraceEvent(
                id="rt-tool",
                session_id="audit-route-session",
                name="search",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
                data={"tool_name": "search", "result": {"hits": 1}},
            )
            decision = TraceEvent(
                id="rt-decision",
                session_id="audit-route-session",
                parent_id="rt-tool",
                name="decide",
                event_type=EventType.DECISION,
                timestamp=datetime(2026, 3, 26, 10, 6, tzinfo=timezone.utc),
                data={
                    "confidence": 0.9,
                    "evidence_event_ids": ["rt-tool"],
                    "chosen_action": "answer",
                    "reasoning": "grounded",
                },
            )
            await repo.add_event(tool)
            await repo.add_event(decision)
            await db_session.commit()

        resp = await client.get("/api/sessions/audit-route-session/audit")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "audit-route-session"
        audit = body["audit"]
        assert audit["trust"]["band"] in {"low", "medium", "high"}
        assert audit["claims"][0]["verification_status"] == "verified"
        assert set(audit["questions"]) == {
            "what_happened",
            "why",
            "evidence",
            "outcome",
            "where_it_failed",
        }


@pytest.mark.asyncio
async def test_audit_route_missing_session_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nope-not-real/audit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Per-decision justification
# ---------------------------------------------------------------------------


def test_justify_decision_returns_why_evidence_outcome():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 2})
    decision = _decision(
        "d1",
        confidence=0.9,
        evidence_event_ids=["t1"],
        chosen_action="answer",
        reasoning="grounded in search results",
    )
    justification = SessionAuditEngine().justify_decision([tool, decision], "d1")

    assert justification is not None
    assert justification["event_id"] == "d1"
    assert justification["what"]["action"] == "answer"
    assert justification["why"]["rationale"] == "grounded in search results"
    assert justification["evidence"]["verification_status"] == "verified"
    assert justification["evidence"]["resolved_refs"] == ["t1"]
    assert justification["outcome"]["downstream_event_count"] == 0
    assert justification["where_it_failed"]["contradicted"] is False
    assert justification["where_it_failed"]["path_to_first_failure"] == []
    assert justification["policy"]["compliant"] is True


def test_justify_decision_normalizes_alternatives():
    decision = _decision(
        "d1",
        confidence=0.8,
        alternatives=[
            {"action": "answer", "chosen": True},
            {"description": "ask clarifying question"},
            "retry",
        ],
    )
    justification = SessionAuditEngine().justify_decision([decision], "d1")

    assert justification is not None
    alternatives = justification["why"]["alternatives"]
    assert alternatives == [
        {"action": "answer", "chosen": True},
        {"action": "ask clarifying question", "chosen": False},
        {"action": "retry", "chosen": False},
    ]


def test_justify_decision_returns_none_for_non_decision_event():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={})
    # t1 exists but is not a decision claim.
    assert SessionAuditEngine().justify_decision([tool], "t1") is None
    # Unknown event id also resolves to None.
    assert SessionAuditEngine().justify_decision([tool], "missing") is None


def test_justify_decision_localizes_downstream_failure_path():
    decision = _decision(
        "d1", confidence=0.9, chosen_action="delete_records", reasoning="cleanup"
    )
    failure = _event(
        "f1",
        EventType.TOOL_RESULT,
        parent_id="d1",
        upstream_event_ids=["d1"],
        tool_name="db",
        error="permission denied",
    )
    justification = SessionAuditEngine().justify_decision(
        [decision, failure], "d1"
    )

    assert justification is not None
    assert justification["where_it_failed"]["contradicted"] is True
    assert justification["where_it_failed"]["path_to_first_failure"][-1] == "f1"
    assert justification["outcome"]["downstream_failures"] == 1
    assert justification["outcome"]["downstream_successes"] == 0
    assert justification["where_it_failed"]["subtree_failures"]


def test_justify_decision_reports_policy_violation_in_subtree():
    decision = _decision("d1", confidence=0.9, chosen_action="send_email")
    violation = _event(
        "v1",
        EventType.POLICY_VIOLATION,
        parent_id="d1",
        upstream_event_ids=["d1"],
        violation_type="unsafe_action",
    )
    justification = SessionAuditEngine().justify_decision(
        [decision, violation], "d1"
    )

    assert justification is not None
    assert justification["policy"]["compliant"] is False
    assert justification["policy"]["violations_in_subtree"][0]["event_id"] == "v1"


@pytest.mark.asyncio
async def test_justification_route_returns_report(shared_app):
    """GET /api/sessions/{id}/decisions/{event_id}/justification over the wire."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("audit-justification-session"))
            tool = TraceEvent(
                id="j-tool",
                session_id="audit-justification-session",
                name="search",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
                data={"tool_name": "search", "result": {"hits": 1}},
            )
            decision = TraceEvent(
                id="j-decision",
                session_id="audit-justification-session",
                parent_id="j-tool",
                name="decide",
                event_type=EventType.DECISION,
                timestamp=datetime(2026, 3, 26, 10, 6, tzinfo=timezone.utc),
                data={
                    "confidence": 0.9,
                    "evidence_event_ids": ["j-tool"],
                    "chosen_action": "answer",
                    "reasoning": "grounded",
                    "alternatives": [{"action": "answer", "chosen": True}],
                },
            )
            await repo.add_event(tool)
            await repo.add_event(decision)
            await db_session.commit()

        resp = await client.get(
            "/api/sessions/audit-justification-session/decisions/j-decision/justification"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "audit-justification-session"
        assert body["event_id"] == "j-decision"
        justification = body["justification"]
        assert justification["evidence"]["verification_status"] == "verified"
        assert set(justification) == {
            "event_id",
            "headline",
            "what",
            "why",
            "evidence",
            "outcome",
            "where_it_failed",
            "policy",
        }


@pytest.mark.asyncio
async def test_justification_route_unknown_event_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("audit-justification-404-session"))
            await db_session.commit()

        resp = await client.get(
            "/api/sessions/audit-justification-404-session/decisions/nope/justification"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Evidence-provenance graph
# ---------------------------------------------------------------------------


def test_evidence_graph_links_claim_to_tool_fact_via_evidence_edge():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 2})
    decision = _decision(
        "d1", confidence=0.9, evidence_event_ids=["t1"], chosen_action="answer"
    )
    graph = SessionAuditEngine().build_evidence_graph([tool, decision])

    roles = {node["event_id"]: node["role"] for node in graph["nodes"]}
    assert roles == {"d1": "claim", "t1": "tool_fact"}

    d1 = next(n for n in graph["nodes"] if n["event_id"] == "d1")
    assert d1["verification_status"] == "verified"

    evidence_edges = [e for e in graph["edges"] if e["edge_type"] == "evidence"]
    assert len(evidence_edges) == 1
    edge = evidence_edges[0]
    assert edge["source_id"] == "d1"
    assert edge["target_id"] == "t1"
    assert edge["source_class"] == "tool_backed"

    assert graph["stats"]["claim_count"] == 1
    assert graph["stats"]["fact_count"] == 1
    assert graph["stats"]["verification_counts"] == {"verified": 1}


def test_evidence_graph_includes_causal_edges_from_parent_ids():
    user_input = _event("u1", EventType.AGENT_START, goal="resolve ticket")
    decision = _decision(
        "d1",
        confidence=0.9,
        evidence_event_ids=["u1"],
        chosen_action="triage",
        parent_id="u1",
    )
    graph = SessionAuditEngine().build_evidence_graph([user_input, decision])

    causal_edges = [e for e in graph["edges"] if e["edge_type"] == "causal"]
    assert causal_edges
    assert {
        "source_id": "u1",
        "target_id": "d1",
        "edge_type": "causal",
    }.items() <= causal_edges[0].items()
    # The cited user input is also an evidence edge with the user_provided class.
    evidence_edges = [e for e in graph["edges"] if e["edge_type"] == "evidence"]
    assert any(
        e["source_id"] == "d1" and e["target_id"] == "u1" and e["source_class"] == "user_provided"
        for e in evidence_edges
    )


def test_evidence_graph_counts_mixed_verification_statuses():
    tool = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={})
    verified = _decision("d1", confidence=0.9, evidence_event_ids=["t1"])
    unsupported = _decision("d2", confidence=0.9)
    graph = SessionAuditEngine().build_evidence_graph([tool, verified, unsupported])

    assert graph["stats"]["verification_counts"] == {"verified": 1, "unsupported": 1}
    assert graph["stats"]["claim_count"] == 2


def test_evidence_graph_counts_unresolved_evidence_refs():
    decision = _decision(
        "d1",
        confidence=0.8,
        evidence_event_ids=["ghost"],
        evidence=[{"source": "model_memory", "content": "vague"}],
    )
    graph = SessionAuditEngine().build_evidence_graph([decision])

    assert graph["stats"]["unresolved_evidence_refs"] == 1
    assert not any(e["edge_type"] == "evidence" for e in graph["edges"])


def test_evidence_graph_includes_uncited_facts_as_available_evidence():
    cited = _event("t1", EventType.TOOL_RESULT, tool_name="search", result={})
    uncited = _event("t2", EventType.TOOL_RESULT, tool_name="lookup", result={})
    decision = _decision("d1", confidence=0.9, evidence_event_ids=["t1"])
    graph = SessionAuditEngine().build_evidence_graph([cited, uncited, decision])

    node_ids = {node["event_id"] for node in graph["nodes"]}
    assert node_ids == {"d1", "t1", "t2"}  # t2 available but never cited
    assert graph["stats"]["fact_count"] == 2
    assert graph["stats"]["evidence_edges"] == 1


@pytest.mark.asyncio
async def test_evidence_graph_route_returns_graph(shared_app):
    """GET /api/sessions/{id}/evidence-graph over the wire."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("audit-evidence-graph-session"))
            tool = TraceEvent(
                id="eg-tool",
                session_id="audit-evidence-graph-session",
                name="search",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
                data={"tool_name": "search", "result": {"hits": 1}},
            )
            decision = TraceEvent(
                id="eg-decision",
                session_id="audit-evidence-graph-session",
                parent_id="eg-tool",
                name="decide",
                event_type=EventType.DECISION,
                timestamp=datetime(2026, 3, 26, 10, 6, tzinfo=timezone.utc),
                data={
                    "confidence": 0.9,
                    "evidence_event_ids": ["eg-tool"],
                    "chosen_action": "answer",
                    "reasoning": "grounded",
                },
            )
            await repo.add_event(tool)
            await repo.add_event(decision)
            await db_session.commit()

        resp = await client.get(
            "/api/sessions/audit-evidence-graph-session/evidence-graph"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "audit-evidence-graph-session"
        graph = body["graph"]
        assert set(graph) == {"session_id", "nodes", "edges", "stats"}
        roles = {node["role"] for node in graph["nodes"]}
        assert "claim" in roles
        assert graph["stats"]["evidence_edges"] >= 1
        assert graph["stats"]["verification_counts"] == {"verified": 1}


@pytest.mark.asyncio
async def test_evidence_graph_route_missing_session_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nope-not-real/evidence-graph")
        assert resp.status_code == 404

