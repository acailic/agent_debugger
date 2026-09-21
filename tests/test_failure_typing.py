"""Tests for the failure-typing additions to collector/audit/audit_engine.py.

Covers the two additive audit capabilities derived from the paper notes:

* STAMP unsafe-control-action typing (``uca_type``) plus Model-or-Harness
  fault attribution (``fault_side`` + ``interaction_edge``) on the first bad
  decision — docs/papers/engineering-a-safer-world-stamp.md and
  docs/papers/model-or-harness-fault-side-taxonomy.md.
* Claim-status fractions (``claim_status_fractions`` + the summary's claim
  verification line) — docs/papers/verifiability-generative-search-engines.md.

Every event/session id in this module is prefixed ``ftyp-``: the suite runs
under xdist and duplicated ids across test modules have collided before
(hard rule from project memory).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine
from collector.audit.audit_engine import (
    CLAIM_STATUS_ORDER,
    _classify_first_bad_decision,
)

# ---------------------------------------------------------------------------
# Helpers (mirror test_audit_engine.py / test_failure_narrative.py builders)
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "failure-typing-session",
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    timestamp: datetime | None = None,
    metadata: dict | None = None,
    **data,
) -> TraceEvent:
    """Build a base TraceEvent carrying typed fields in its data dict."""
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp or datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=upstream_event_ids or [],
        metadata=metadata or {},
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    evidence_event_ids: list[str] | None = None,
    chosen_action: str = "act",
    reasoning: str = "",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    metadata: dict | None = None,
    **data,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        timestamp=timestamp,
        metadata=metadata,
        confidence=confidence,
        evidence_event_ids=evidence_event_ids or [],
        chosen_action=chosen_action,
        reasoning=reasoning,
        **data,
    )


def _ts(minute: int) -> datetime:
    return datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)


def _detail(events: list[TraceEvent]) -> dict | None:
    """First-bad-decision detail from a full engine audit of *events*."""
    report = SessionAuditEngine().audit(events)
    return report["questions"]["where_it_failed"]["first_bad_decision_detail"]


# ---------------------------------------------------------------------------
# first_bad_decision_detail: shape + backward compatibility
# ---------------------------------------------------------------------------


def test_detail_shape_on_unsupported_decision():
    # A confident evidence-free decision is unsupported -> the first bad
    # decision; the detail record carries the five typing fields (superset:
    # the MAST slice adds mast_mode/mast_category additively).
    report = SessionAuditEngine().audit([_decision("ftyp-shape-d1", confidence=0.9)])

    where = report["questions"]["where_it_failed"]
    assert where["first_bad_decision"] == "ftyp-shape-d1"
    detail = where["first_bad_decision_detail"]
    assert set(detail) >= {
        "event_id",
        "uca_type",
        "fault_side",
        "interaction_edge",
        "derivation",
    }
    assert detail["event_id"] == "ftyp-shape-d1"
    assert detail["uca_type"] == "wrong"  # rule 4: unsupported claim
    assert detail["fault_side"] == "model_produced"  # fault rule 3: DECISION
    assert detail["interaction_edge"] is None  # no parent -> no edge
    assert "rule 4" in detail["derivation"]
    assert "unsupported" in detail["derivation"]


def test_first_bad_decision_bare_string_is_unchanged_regression():
    # The pre-existing bare event-id string must keep its exact shape/value.
    report = SessionAuditEngine().audit([_decision("ftyp-regress-d1", confidence=0.9)])

    where = report["questions"]["where_it_failed"]
    first_bad = where["first_bad_decision"]
    assert isinstance(first_bad, str)
    assert first_bad == "ftyp-regress-d1"
    assert where["first_bad_decision_detail"]["event_id"] == first_bad


def test_detail_is_none_when_no_bad_decision():
    # A clean grounded run has no first bad decision: both fields are None.
    tool = _event("ftyp-clean-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    decision = _decision(
        "ftyp-clean-d1", confidence=0.9, evidence_event_ids=["ftyp-clean-t1"]
    )
    report = SessionAuditEngine().audit([tool, decision])

    where = report["questions"]["where_it_failed"]
    assert where["first_bad_decision"] is None
    assert where["first_bad_decision_detail"] is None


# ---------------------------------------------------------------------------
# uca_type rules 1-5, each firing in isolation
# ---------------------------------------------------------------------------


def test_uca_rule1_stale_claim_is_mistimed():
    # Rule 1: the decision cites an older fact while a newer uncited fact
    # existed (stale) and a downstream failing tool blames it as the cause,
    # making it the first bad decision. STAMP: acting on superseded evidence
    # is an action at the wrong time.
    old_tool = _event(
        "ftyp-mis-t-old",
        EventType.TOOL_RESULT,
        tool_name="search",
        result={"hits": 1},
        timestamp=_ts(0),
    )
    fresh_tool = _event(
        "ftyp-mis-t-new",
        EventType.TOOL_RESULT,
        tool_name="search",
        result={"hits": 99},
        timestamp=_ts(5),
    )
    decision = _decision(
        "ftyp-mis-d1",
        confidence=0.8,
        evidence_event_ids=["ftyp-mis-t-old"],
        parent_id="ftyp-mis-t-old",
        timestamp=_ts(6),
    )
    # Unlinked failing tool: the causal analyzer still blames the nearest
    # preceding decision, but the decision's subtree stays failure-free so
    # the claim stays stale (not contradicted).
    failing_tool = _event(
        "ftyp-mis-f1",
        EventType.TOOL_RESULT,
        tool_name="api",
        error="500",
        timestamp=_ts(7),
    )
    report = SessionAuditEngine().audit([old_tool, fresh_tool, decision, failing_tool])

    assert report["claims"][0]["verification_status"] == "stale"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "mistimed"
    assert "rule 1" in detail["derivation"]
    assert detail["fault_side"] == "model_produced"
    assert detail["interaction_edge"] == "tool_result->decision"


def test_uca_rule2_guardrail_blame_is_omitted():
    # Rule 2: a grounded (verified) decision that a REFUSAL failure blames as
    # its cause — the refusal blocked the required action, so the required
    # action was not taken (omitted), not a wrong or stale action.
    tool = _event("ftyp-omit-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    decision = _decision(
        "ftyp-omit-d1",
        confidence=0.9,
        evidence_event_ids=["ftyp-omit-t1"],
        parent_id="ftyp-omit-t1",
    )
    refusal = _event("ftyp-omit-r1", EventType.REFUSAL, reason="would exfiltrate secrets")
    report = SessionAuditEngine().audit([tool, decision, refusal])

    assert report["claims"][0]["verification_status"] == "verified"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "omitted"
    assert "rule 2" in detail["derivation"]
    assert "guardrail" in detail["derivation"]
    assert detail["fault_side"] == "model_produced"
    assert detail["interaction_edge"] == "tool_result->decision"


def test_uca_rule2_policy_violation_event_is_omitted_direct():
    # Rule 2 (bad-event clause): the blamed event itself is a policy
    # violation. Exercised at the helper level — through audit() the first
    # bad decision is always a DECISION claim.
    violation = _event(
        "ftyp-pv-p1", EventType.POLICY_VIOLATION, violation_type="unsafe_action"
    )
    detail = _classify_first_bad_decision(
        "ftyp-pv-p1", events=[violation], claims=[], failures=[], signals=[]
    )
    assert detail["uca_type"] == "omitted"
    assert "policy_violation" in detail["derivation"]


def test_uca_rule3_loop_signal_is_overlong_direct():
    # Rule 3: a repeated_failed_strategy signal references the event — the
    # strategy was applied too long. Exercised at the helper level: through
    # audit() the looping signal anchors on the first failing TOOL_RESULT,
    # which is never the first bad decision (always a claim).
    first_failure = _event(
        "ftyp-loop-f1", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
    )
    second_failure = _event(
        "ftyp-loop-f2", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
    )
    repeat_signal = {
        "event_id": "ftyp-loop-f1",
        "type": "repeated_failed_strategy",
        "severity": "high",
        "message": 'Tool "uploader" failed 2 times — repeated failed strategy.',
    }
    detail = _classify_first_bad_decision(
        "ftyp-loop-f1",
        events=[first_failure, second_failure],
        claims=[],
        failures=[],
        signals=[repeat_signal],
    )
    assert detail["uca_type"] == "overlong"
    assert "rule 3" in detail["derivation"]

    # The tool-loop flavor of the looping signal (BEHAVIOR_ALERT alert_type
    # "tool_loop" -> a plan_drift signal) types the same way.
    tool_loop_signal = {
        "event_id": "ftyp-loop-f1",
        "type": "plan_drift",
        "severity": "high",
        "message": "Tool-loop behavior: repeated tool invocations",
    }
    detail_loop = _classify_first_bad_decision(
        "ftyp-loop-f1",
        events=[first_failure, second_failure],
        claims=[],
        failures=[],
        signals=[tool_loop_signal],
    )
    assert detail_loop["uca_type"] == "overlong"


def test_uca_rule4_unsupported_claim_is_wrong():
    # Rule 4: an unsupported claim with no guardrail/loop involvement is a
    # wrong action taken (the simplest wrong-decision fixture).
    report = SessionAuditEngine().audit([_decision("ftyp-wrong-d1", confidence=0.9)])

    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "wrong"
    assert "rule 4" in detail["derivation"]


def test_uca_rule4_contradicted_claim_is_wrong():
    # Rule 4 via the contradicted half: a confident decision whose subtree
    # fails.
    decision = _decision("ftyp-wrong-d2", confidence=0.9, chosen_action="delete")
    failure = _event(
        "ftyp-wrong-f2",
        EventType.TOOL_RESULT,
        parent_id="ftyp-wrong-d2",
        tool_name="db",
        error="permission denied",
    )
    report = SessionAuditEngine().audit([decision, failure])

    assert report["claims"][0]["verification_status"] == "contradicted"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "wrong"
    assert "contradicted" in detail["derivation"]


def test_uca_rule5_undetermined_when_no_earlier_rule_matches():
    # Rule 5: the decision is blamed as a cause but its claim status
    # (unverified) matches no earlier rule -> honest undetermined.
    decision = _decision("ftyp-undet-d1", confidence=0.2)
    failing_tool = _event(
        "ftyp-undet-f1", EventType.TOOL_RESULT, tool_name="api", error="500"
    )
    report = SessionAuditEngine().audit([decision, failing_tool])

    assert report["claims"][0]["verification_status"] == "unverified"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "undetermined"
    assert "rule 5" in detail["derivation"]


def test_uca_rule_ordering_mistimed_beats_omitted():
    # Rule 1 wins over rule 2: a stale decision that a refusal also blames
    # types as mistimed (acted on superseded evidence), not omitted.
    old_tool = _event(
        "ftyp-mo-t-old", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(0)
    )
    fresh_tool = _event(
        "ftyp-mo-t-new", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(5)
    )
    decision = _decision(
        "ftyp-mo-d1",
        confidence=0.8,
        evidence_event_ids=["ftyp-mo-t-old"],
        timestamp=_ts(6),
    )
    refusal = _event("ftyp-mo-r1", EventType.REFUSAL, reason="blocked")
    report = SessionAuditEngine().audit([old_tool, fresh_tool, decision, refusal])

    assert report["claims"][0]["verification_status"] == "stale"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "mistimed"


def test_uca_rule_ordering_omitted_beats_wrong():
    # Rule 2 wins over rule 4: an unsupported decision blamed by a refusal is
    # typed omitted (the guardrail blocked the required action), not wrong.
    decision = _decision("ftyp-ow-d1", confidence=0.9)
    refusal = _event("ftyp-ow-r1", EventType.REFUSAL, reason="blocked")
    report = SessionAuditEngine().audit([decision, refusal])

    assert report["claims"][0]["verification_status"] == "unsupported"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["uca_type"] == "omitted"


# ---------------------------------------------------------------------------
# fault_side rules 1-4
# ---------------------------------------------------------------------------


def test_fault_side_tool_returned_direct():
    # Fault rule 1: the bad/blamed event is a failed TOOL_RESULT. Exercised
    # at the helper level — through audit() the first bad decision is always
    # a DECISION claim, so the tool_returned branch needs a blamed tool id.
    failing_tool = _event(
        "ftyp-tool-f1", EventType.TOOL_RESULT, tool_name="api", error="500"
    )
    detail = _classify_first_bad_decision(
        "ftyp-tool-f1", events=[failing_tool], claims=[], failures=[], signals=[]
    )
    assert detail["fault_side"] == "tool_returned"


def test_fault_side_harness_recorded_when_truncated():
    # Fault rule 2: the decision carries the ingestion pipeline's truncation
    # marker (completeness module's _event_is_truncated check).
    decision = _decision(
        "ftyp-trunc-d1", confidence=0.9, metadata={"_truncated": True}
    )
    detail = _detail([decision])
    assert detail["fault_side"] == "harness_recorded"


def test_fault_side_harness_recorded_when_parent_missing_from_trace():
    # Fault rule 2 (dangling parent): parent_id set but absent from the
    # trace. The interaction edge stays None (unresolvable parent).
    decision = _decision("ftyp-ghost-d1", confidence=0.9, parent_id="ftyp-ghost-parent")
    detail = _detail([decision])
    assert detail["fault_side"] == "harness_recorded"
    assert detail["interaction_edge"] is None


def test_fault_side_model_produced_for_llm_response_direct():
    # Fault rule 3 (LLM_RESPONSE half): a claim/verification failure produced
    # by the model, sitting on the decision->llm_response interaction edge.
    decision = _decision("ftyp-llm-d1", confidence=0.8)
    response = _event(
        "ftyp-llm-r1", EventType.LLM_RESPONSE, parent_id="ftyp-llm-d1", content="text"
    )
    detail = _classify_first_bad_decision(
        "ftyp-llm-r1", events=[decision, response], claims=[], failures=[], signals=[]
    )
    assert detail["fault_side"] == "model_produced"
    assert detail["interaction_edge"] == "decision->llm_response"


def test_fault_side_undetermined_direct():
    # Fault rule 4: an event type the rules cannot attribute (neither a
    # failed tool result, nor harness-marked, nor decision/llm_response).
    turn = _event("ftyp-turn-a1", EventType.AGENT_TURN, content="hello")
    detail = _classify_first_bad_decision(
        "ftyp-turn-a1", events=[turn], claims=[], failures=[], signals=[]
    )
    assert detail["fault_side"] == "undetermined"


# ---------------------------------------------------------------------------
# interaction_edge
# ---------------------------------------------------------------------------


def test_interaction_edge_with_and_without_parent():
    # With parent: the grounded decision's edge reads parent->child
    # ("tool_result->decision" — pinned end-to-end in the mistimed/omitted
    # tests above). Without parent: no resolvable parent -> None.
    tool = _event("ftyp-edge-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    with_parent = _decision(
        "ftyp-edge-d1",
        confidence=0.9,
        evidence_event_ids=["ftyp-edge-t1"],
        parent_id="ftyp-edge-t1",
    )
    unsupported_with_parent = _decision(
        "ftyp-edge-d2",
        confidence=0.9,
        parent_id="ftyp-edge-t1",
    )
    detail = _detail([tool, with_parent, unsupported_with_parent])
    assert detail["event_id"] == "ftyp-edge-d2"
    assert detail["interaction_edge"] == "tool_result->decision"

    no_parent = _decision("ftyp-edge-d3", confidence=0.9)
    detail_none = _detail([no_parent])
    assert detail_none["interaction_edge"] is None


# ---------------------------------------------------------------------------
# claim_status_fractions + summary line (Liu et al. verifiability note)
# ---------------------------------------------------------------------------


def _mixed_status_events() -> list[TraceEvent]:
    """One run hitting five of the six statuses: 3 verified, 1 partially
    verified, 1 contradicted, 1 unsupported, 1 unverified."""
    tool = _event("ftyp-frac-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    verified = [
        _decision(
            f"ftyp-frac-dv{idx}",
            confidence=0.9,
            evidence_event_ids=["ftyp-frac-t1"],
        )
        for idx in range(1, 4)
    ]
    partially = _decision(
        "ftyp-frac-dp1",
        confidence=0.8,
        evidence_event_ids=["ftyp-frac-ghost"],
        # evidence that does not resolve to a concrete fact
        evidence=[{"source": "model_memory", "content": "vague"}],
    )
    unsupported = _decision("ftyp-frac-du1", confidence=0.9)
    unverified = _decision("ftyp-frac-dun1", confidence=0.2)
    contradicted = _decision("ftyp-frac-dc1", confidence=0.9)
    contradicted_failure = _event(
        "ftyp-frac-fc1",
        EventType.TOOL_RESULT,
        parent_id="ftyp-frac-dc1",
        tool_name="db",
        error="disk full",
    )
    return [tool, *verified, partially, unverified, unsupported, contradicted, contradicted_failure]


def test_claim_status_fractions_math_on_mixed_statuses():
    report = SessionAuditEngine().audit(_mixed_status_events())

    statuses = {c["event_id"]: c["verification_status"] for c in report["claims"]}
    assert statuses == {
        "ftyp-frac-dv1": "verified",
        "ftyp-frac-dv2": "verified",
        "ftyp-frac-dv3": "verified",
        "ftyp-frac-dp1": "partially_verified",
        "ftyp-frac-dun1": "unverified",
        "ftyp-frac-du1": "unsupported",
        "ftyp-frac-dc1": "contradicted",
    }

    fractions = report["claim_status_fractions"]
    assert list(fractions) == [*CLAIM_STATUS_ORDER, "total_claims"]
    assert fractions == {
        "verified": {"count": 3, "fraction": round(3 / 7, 4)},
        "partially_verified": {"count": 1, "fraction": round(1 / 7, 4)},
        "contradicted": {"count": 1, "fraction": round(1 / 7, 4)},
        "unsupported": {"count": 1, "fraction": round(1 / 7, 4)},
        "unverified": {"count": 1, "fraction": round(1 / 7, 4)},
        "stale": {"count": 0, "fraction": 0.0},
        "total_claims": 7,
    }


def test_claim_status_fractions_zeroed_for_empty_session():
    report = SessionAuditEngine().audit([])

    assert report["claim_status_fractions"] == {
        "verified": {"count": 0, "fraction": 0.0},
        "partially_verified": {"count": 0, "fraction": 0.0},
        "contradicted": {"count": 0, "fraction": 0.0},
        "unsupported": {"count": 0, "fraction": 0.0},
        "unverified": {"count": 0, "fraction": 0.0},
        "stale": {"count": 0, "fraction": 0.0},
        "total_claims": 0,
    }


def test_summary_markdown_claim_verification_line_mixed():
    report = SessionAuditEngine().audit(_mixed_status_events())

    line = next(
        ln
        for ln in report["summary"]["markdown"].splitlines()
        if ln.startswith("Claim verification:")
    )
    assert line == (
        "Claim verification: 3 verified, 1 partially, 1 contradicted, "
        "1 unsupported, 1 unverified (7 claims total)"
    )


def test_summary_claim_verification_line_skips_zero_statuses():
    # A fully verified run shows only the verified count + the total; an
    # empty run still names 0 verified so the row never disappears.
    tool = _event("ftyp-line-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    decision = _decision(
        "ftyp-line-d1", confidence=0.9, evidence_event_ids=["ftyp-line-t1"]
    )
    clean = SessionAuditEngine().audit([tool, decision])["summary"]["markdown"]
    assert "Claim verification: 1 verified (1 claim total)" in clean

    empty = SessionAuditEngine().audit([])["summary"]["markdown"]
    assert "Claim verification: 0 verified (0 claims total)" in empty


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_failure_typing_is_deterministic():
    events = _mixed_status_events() + [
        _event("ftyp-det-r1", EventType.REFUSAL, reason="blocked"),
    ]
    engine = SessionAuditEngine()
    first = engine.audit(copy.deepcopy(events))
    second = engine.audit(copy.deepcopy(events))
    assert first["questions"]["where_it_failed"] == second["questions"]["where_it_failed"]
    assert first["claim_status_fractions"] == second["claim_status_fractions"]
    assert first["summary"] == second["summary"]
