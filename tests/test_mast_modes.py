"""Tests for the MAST failure-mode vocabulary in collector/audit/audit_engine.py.

Adopt's MAST's 14-mode / 3-category taxonomy (Cemri et al., arXiv:2503.13657)
for the audit narrative and first-bad-decision typing — see
docs/papers/why-do-multi-agent-llm-systems-fail-mast.md. The taxonomy ONLY:
every mode label must be derived from recorded trace facts, never from an
LLM judge, and evidence no mode honestly covers reads ``unmapped`` /
``None`` (the same discipline as ``undetermined``).

Covers, per slice spec:

* every :data:`MAST_MODE_MAP` row firing through ``audit()`` on a synthetic
  trace built to trigger its trace fact (or, where the engine can never
  anchor the fact on a decision, through ``_classify_first_bad_decision``
  fed with the report's own signals — mirroring the uca rule-3 pattern in
  tests/test_failure_typing.py);
* the unmapped rows staying unmapped;
* additive-key regressions: ``first_bad_decision_detail`` still carries
  uca_type / fault_side and the bare ``first_bad_decision`` stays a string;
* determinism;
* no mode label without its trace fact — in particular no inter-agent
  (C2) mode may ever fire on a single-agent trace.

Every event/session id in this module is prefixed ``mst-``: the suite runs
under xdist and duplicated ids across test modules have collided before
(hard rule from project memory).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine
from collector.audit.audit_engine import MAST_MODE_MAP, _classify_first_bad_decision

# ---------------------------------------------------------------------------
# Helpers (mirror test_failure_typing.py / test_audit_engine.py builders)
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "mast-modes-session",
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
    **data,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        timestamp=timestamp,
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


def _outcome_failures(events: list[TraceEvent]) -> list[dict]:
    """The failures list of the where_it_failed outcome block."""
    report = SessionAuditEngine().audit(events)
    return report["questions"]["outcome"]["failures"]


# The 14 MAST modes (arXiv:2503.13657 Appendix A), snake_case as emitted.
FULL_MAST_MODES = {
    # C1 system design issues
    "disobey_task_specification",
    "disobey_role_specification",
    "step_repetition",
    "loss_of_conversation_history",
    "unaware_of_termination_conditions",
    # C2 inter-agent misalignment
    "conversation_reset",
    "fail_to_ask_for_clarification",
    "task_derailment",
    "information_withholding",
    "ignored_other_agent_input",
    "reasoning_action_mismatch",
    # C3 task verification
    "premature_termination",
    "no_or_incomplete_verification",
    "incorrect_verification",
}

# The six C2 modes — they all require a second agent, so a single-agent
# trace must never emit one (the note's caution: the corpus is multi-agent;
# a mode that never fires here is a finding, not a bug).
C2_MODES = {
    "conversation_reset",
    "fail_to_ask_for_clarification",
    "task_derailment",
    "information_withholding",
    "ignored_other_agent_input",
    "reasoning_action_mismatch",
}


# ---------------------------------------------------------------------------
# MAST_MODE_MAP invariants
# ---------------------------------------------------------------------------


def test_mode_map_shape_and_vocabulary():
    # Every row is exactly {mast_mode, mast_category}; mapped modes are real
    # MAST names; no row maps to the inter-agent category C2.
    for key, entry in MAST_MODE_MAP.items():
        assert set(entry) == {"mast_mode", "mast_category"}, key
        if entry["mast_mode"] != "unmapped":
            assert entry["mast_mode"] in FULL_MAST_MODES, key
            assert entry["mast_category"] in {"C1", "C3"}, key
        else:
            assert entry["mast_category"] is None, key
    assert not any(entry["mast_category"] == "C2" for entry in MAST_MODE_MAP.values())
    # Verified claims are passes, not failure evidence — never mapped.
    assert "verified" not in MAST_MODE_MAP


def test_mode_map_covers_every_diagnostics_failure_mode():
    # The eight failure-mode strings FailureDiagnostics can emit (see
    # collector/failure_diagnostics.py failure_mode()) each have a row, so a
    # failure entry can never fall through to an undocumented default.
    diagnostics_modes = {
        "tool_execution_failure",
        "ungrounded_decision",
        "looping_behavior",
        "behavior_anomaly",
        "guardrail_block",
        "policy_mismatch",
        "upstream_runtime_error",
        "diagnostic_review",
    }
    assert diagnostics_modes <= set(MAST_MODE_MAP)
    # Plus the loop signal type and the failure-grade claim statuses.
    assert {"repeated_failed_strategy", "stale", "contradicted", "unsupported"} <= set(
        MAST_MODE_MAP
    )


# ---------------------------------------------------------------------------
# C1 rows: step repetition + disobey task specification, firing end-to-end
# ---------------------------------------------------------------------------


def test_looping_behavior_maps_to_step_repetition():
    # Trace fact: a BEHAVIOR_ALERT with alert_type "tool_loop" — repeated
    # tool invocations recorded -> MAST FM-1.3 step repetition (C1).
    alert = _event(
        "mst-loop-a1",
        EventType.BEHAVIOR_ALERT,
        alert_type="tool_loop",
        signal="uploader invoked 5 times",
    )
    entries = _outcome_failures([alert])

    assert len(entries) == 1
    assert entries[0]["mode"] == "looping_behavior"
    assert entries[0]["mast_mode"] == "step_repetition"
    assert entries[0]["mast_category"] == "C1"


def test_repeated_failed_strategy_signal_types_step_repetition():
    # Trace fact: the same tool_name carries >= 2 error results. Through
    # audit() the repeated_failed_strategy signal anchors on the first
    # failing TOOL_RESULT, which is never the first bad decision (always a
    # claim), so the map row is exercised by feeding the classifier the
    # report's own signals — the same pattern test_failure_typing.py uses
    # for uca rule 3.
    first = _event(
        "mst-rep-f1", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
    )
    second = _event(
        "mst-rep-f2", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
    )
    engine = SessionAuditEngine()
    report = engine.audit([first, second])

    signal = next(
        s for s in report["signals"] if s["type"] == "repeated_failed_strategy"
    )
    assert signal["event_id"] == "mst-rep-f1"

    detail = _classify_first_bad_decision(
        "mst-rep-f1",
        events=[first, second],
        claims=report["claims"],
        failures=report["failures"],
        signals=report["signals"],
    )
    assert detail["mast_mode"] == "step_repetition"
    assert detail["mast_category"] == "C1"
    assert "mast rule 3" in detail["derivation"]
    assert "FM-1.3" in detail["derivation"]


def test_guardrail_block_maps_to_disobey_task_specification():
    # Trace fact: a REFUSAL names a constraint the attempted action did not
    # adhere to -> MAST FM-1.1 disobey task specification (C1). Fires both
    # on the outcome failures entry and on the blamed first bad decision.
    tool = _event("mst-grd-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    decision = _decision(
        "mst-grd-d1",
        confidence=0.9,
        evidence_event_ids=["mst-grd-t1"],
        parent_id="mst-grd-t1",
    )
    refusal = _event("mst-grd-r1", EventType.REFUSAL, reason="would exfiltrate secrets")
    report = SessionAuditEngine().audit([tool, decision, refusal])

    entries = report["questions"]["outcome"]["failures"]
    assert len(entries) == 1
    assert entries[0]["mode"] == "guardrail_block"
    assert entries[0]["mast_mode"] == "disobey_task_specification"
    assert entries[0]["mast_category"] == "C1"

    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["event_id"] == "mst-grd-d1"
    assert detail["mast_mode"] == "disobey_task_specification"
    assert detail["mast_category"] == "C1"
    assert "mast rule 2" in detail["derivation"]
    assert "FM-1.1" in detail["derivation"]


def test_policy_mismatch_maps_to_disobey_task_specification():
    # Trace fact: a POLICY_VIOLATION event — its violation_type names the
    # constraint breached -> the same FM-1.1 mode (C1).
    violation = _event(
        "mst-pol-p1", EventType.POLICY_VIOLATION, violation_type="prod_write"
    )
    entries = _outcome_failures([violation])

    assert len(entries) == 1
    assert entries[0]["mode"] == "policy_mismatch"
    assert entries[0]["mast_mode"] == "disobey_task_specification"
    assert entries[0]["mast_category"] == "C1"


# ---------------------------------------------------------------------------
# C3 rows: verification modes on the first bad decision, firing end-to-end
# ---------------------------------------------------------------------------


def test_stale_claim_maps_to_incorrect_verification():
    # Trace fact: STALE — the decision cited an older fact while a strictly
    # newer uncited concrete fact existed at decision time; it was validated
    # against superseded state -> MAST FM-3.3 incorrect verification (C3).
    old_tool = _event(
        "mst-sta-t-old",
        EventType.TOOL_RESULT,
        tool_name="search",
        result={"hits": 1},
        timestamp=_ts(0),
    )
    fresh_tool = _event(
        "mst-sta-t-new",
        EventType.TOOL_RESULT,
        tool_name="search",
        result={"hits": 99},
        timestamp=_ts(5),
    )
    decision = _decision(
        "mst-sta-d1",
        confidence=0.8,
        evidence_event_ids=["mst-sta-t-old"],
        parent_id="mst-sta-t-old",
        timestamp=_ts(6),
    )
    failing_tool = _event(
        "mst-sta-f1", EventType.TOOL_RESULT, tool_name="api", error="500", timestamp=_ts(7)
    )
    report = SessionAuditEngine().audit([old_tool, fresh_tool, decision, failing_tool])

    assert report["claims"][0]["verification_status"] == "stale"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["mast_mode"] == "incorrect_verification"
    assert detail["mast_category"] == "C3"
    assert "mast rule 1" in detail["derivation"]
    assert "FM-3.3" in detail["derivation"]


def test_contradicted_claim_maps_to_no_or_incomplete_verification():
    # Trace fact: CONTRADICTED — the decision's causal subtree contains a
    # failure event; the outcome disagreed and no recorded check caught it
    # -> MAST FM-3.2 no or incomplete verification (C3).
    decision = _decision("mst-con-d1", confidence=0.9, chosen_action="delete")
    failure = _event(
        "mst-con-f1",
        EventType.TOOL_RESULT,
        parent_id="mst-con-d1",
        tool_name="db",
        error="permission denied",
    )
    report = SessionAuditEngine().audit([decision, failure])

    assert report["claims"][0]["verification_status"] == "contradicted"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["mast_mode"] == "no_or_incomplete_verification"
    assert detail["mast_category"] == "C3"
    assert "mast rule 4" in detail["derivation"]
    assert "FM-3.2" in detail["derivation"]


def test_unsupported_claim_maps_to_no_or_incomplete_verification():
    # Trace fact: UNSUPPORTED — asserted at confidence >= 0.5 with no
    # evidence recorded at all -> the same FM-3.2 verification-absent mode.
    detail = _detail([_decision("mst-uns-d1", confidence=0.9)])

    assert detail["mast_mode"] == "no_or_incomplete_verification"
    assert detail["mast_category"] == "C3"
    assert "mast rule 5" in detail["derivation"]
    assert "FM-3.2" in detail["derivation"]


def test_mast_rule_ordering_stale_beats_guardrail():
    # Mast rule 1 wins over rule 2: a stale decision that a refusal also
    # blames types as incorrect verification, not disobey task spec.
    old_tool = _event(
        "mst-mo-t-old", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(0)
    )
    fresh_tool = _event(
        "mst-mo-t-new", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(5)
    )
    decision = _decision(
        "mst-mo-d1",
        confidence=0.8,
        evidence_event_ids=["mst-mo-t-old"],
        timestamp=_ts(6),
    )
    refusal = _event("mst-mo-r1", EventType.REFUSAL, reason="blocked")
    report = SessionAuditEngine().audit([old_tool, fresh_tool, decision, refusal])

    assert report["claims"][0]["verification_status"] == "stale"
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["mast_mode"] == "incorrect_verification"
    assert detail["mast_category"] == "C3"


# ---------------------------------------------------------------------------
# Unmapped rows: no honest MAST mode — never a forced guess
# ---------------------------------------------------------------------------


def test_tool_execution_failure_is_unmapped():
    # Trace fact: a failed TOOL_RESULT with no agent-mishandling candidate —
    # a tool-side error. MAST names no tool-error mode, so the entry reads
    # unmapped / None rather than a forced label.
    failing_tool = _event(
        "mst-tox-f1", EventType.TOOL_RESULT, tool_name="api", error="500"
    )
    entries = _outcome_failures([failing_tool])

    assert len(entries) == 1
    assert entries[0]["mode"] == "tool_execution_failure"
    assert entries[0]["mast_mode"] == "unmapped"
    assert entries[0]["mast_category"] is None


def test_ungrounded_decision_is_unmapped_and_detail_rule6():
    # Trace fact: the failed action was blamed on a decision with confidence
    # < 0.4 and no evidence — deciding without the needed information. The
    # conceptual neighbor FM-2.2 is inter-agent (C2), so the failure entry
    # stays unmapped and the blamed decision (claim status unverified)
    # falls through to mast rule 6.
    decision = _decision("mst-ugd-d1", confidence=0.3)
    failing_tool = _event(
        "mst-ugd-f1", EventType.TOOL_RESULT, tool_name="api", error="500"
    )
    report = SessionAuditEngine().audit([decision, failing_tool])

    entries = report["questions"]["outcome"]["failures"]
    assert entries[0]["mode"] == "ungrounded_decision"
    assert entries[0]["mast_mode"] == "unmapped"
    assert entries[0]["mast_category"] is None

    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["event_id"] == "mst-ugd-d1"
    assert detail["mast_mode"] == "unmapped"
    assert detail["mast_category"] is None
    assert "mast rule 6" in detail["derivation"]
    # Unchanged first-bad-decision typing from the previous slice.
    assert detail["uca_type"] == "undetermined"


def test_upstream_runtime_error_is_unmapped():
    # Trace fact: an ERROR event — a harness/runtime exception, outside
    # MAST's agent-behavior vocabulary.
    error = _event(
        "mst-err-e1", EventType.ERROR, error_type="RuntimeError", error_message="boom"
    )
    entries = _outcome_failures([error])

    assert entries[0]["mode"] == "upstream_runtime_error"
    assert entries[0]["mast_mode"] == "unmapped"
    assert entries[0]["mast_category"] is None


def test_behavior_anomaly_is_unmapped():
    # Trace fact: a BEHAVIOR_ALERT that is not a tool loop — no specific
    # behavior a MAST mode names is recorded.
    alert = _event(
        "mst-anom-a1", EventType.BEHAVIOR_ALERT, alert_type="hallucination_spree"
    )
    entries = _outcome_failures([alert])

    assert entries[0]["mode"] == "behavior_anomaly"
    assert entries[0]["mast_mode"] == "unmapped"
    assert entries[0]["mast_category"] is None


# ---------------------------------------------------------------------------
# No mode label without its trace fact (single-agent discipline)
# ---------------------------------------------------------------------------


def _single_agent_traces() -> list[list[TraceEvent]]:
    """Battery of single-agent traces exercising every firing surface."""
    return [
        # tool loop (looping_behavior + tool-loop plan_drift signal)
        [
            _event(
                "mst-bat-a1",
                EventType.BEHAVIOR_ALERT,
                alert_type="tool_loop",
                signal="repeated invocations",
            )
        ],
        # repeated failed strategy + guardrail + policy in one run
        [
            _event(
                "mst-bat-f1", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
            ),
            _event(
                "mst-bat-f2", EventType.TOOL_RESULT, tool_name="uploader", error="timeout"
            ),
            _event("mst-bat-r1", EventType.REFUSAL, reason="blocked"),
            _event("mst-bat-p1", EventType.POLICY_VIOLATION, violation_type="prod_write"),
        ],
        # stale decision blamed by a downstream failure
        [
            _event(
                "mst-bat-t-old", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(0)
            ),
            _event(
                "mst-bat-t-new", EventType.TOOL_RESULT, tool_name="search", result={}, timestamp=_ts(5)
            ),
            _decision(
                "mst-bat-d1",
                confidence=0.8,
                evidence_event_ids=["mst-bat-t-old"],
                timestamp=_ts(6),
            ),
            _event(
                "mst-bat-f3", EventType.TOOL_RESULT, tool_name="api", error="500", timestamp=_ts(7)
            ),
        ],
        # unsupported + ungrounded decisions
        [_decision("mst-bat-d2", confidence=0.9)],
        [
            _decision("mst-bat-d3", confidence=0.3),
            _event("mst-bat-f4", EventType.TOOL_RESULT, tool_name="api", error="500"),
        ],
        # contradicted decision
        [
            _decision("mst-bat-d4", confidence=0.9),
            _event(
                "mst-bat-f5",
                EventType.TOOL_RESULT,
                parent_id="mst-bat-d4",
                tool_name="db",
                error="denied",
            ),
        ],
    ]


def test_no_inter_agent_mode_fires_on_single_agent_traces():
    # The six C2 modes all require a second agent; no trace fact in a
    # single-agent session can honestly fire one, so no MAST label emitted
    # anywhere in the report may be a C2 mode.
    engine = SessionAuditEngine()
    for events in _single_agent_traces():
        report = engine.audit(events)
        detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
        if detail is not None:
            assert detail["mast_mode"] not in C2_MODES
            assert detail["mast_category"] != "C2"
        for entry in report["questions"]["outcome"]["failures"]:
            assert entry["mast_mode"] not in C2_MODES
            assert entry["mast_category"] != "C2"


def test_goal_drift_stays_out_of_inter_agent_task_derailment():
    # A drifting single-agent run (objective established, then trailing
    # decisions stop referencing it) has a recorded drift fact — but MAST's
    # FM-2.3 task derailment is inter-agent (C2), so the drift may not buy
    # an inter-agent label: the first bad decision keeps its verification
    # mode from claim facts alone.
    start = _event(
        "mst-drift-s1", EventType.AGENT_START, goal="migrate the database schema"
    )
    tool = _event("mst-drift-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    grounded = _decision(
        "mst-drift-d1",
        confidence=0.9,
        evidence_event_ids=["mst-drift-t1"],
        reasoning="plan to migrate the database schema tonight",
        timestamp=_ts(2),
    )
    adrift1 = _decision(
        "mst-drift-d2", confidence=0.9, reasoning="check the weather forecast", timestamp=_ts(3)
    )
    adrift2 = _decision(
        "mst-drift-d3", confidence=0.9, reasoning="read sports headlines", timestamp=_ts(4)
    )
    report = SessionAuditEngine().audit([start, tool, grounded, adrift1, adrift2])

    assert report["goal_drift"]["drifted"] is True
    detail = report["questions"]["where_it_failed"]["first_bad_decision_detail"]
    assert detail["event_id"] == "mst-drift-d2"
    assert detail["mast_mode"] == "no_or_incomplete_verification"  # unsupported claim
    assert detail["mast_category"] == "C3"
    assert detail["mast_mode"] not in C2_MODES


def test_clean_run_emits_no_mast_labels():
    # The strongest no-fact-no-label case: a grounded, failure-free run
    # emits no failure entries and no first bad decision at all.
    tool = _event("mst-clean-t1", EventType.TOOL_RESULT, tool_name="search", result={})
    decision = _decision(
        "mst-clean-d1", confidence=0.9, evidence_event_ids=["mst-clean-t1"]
    )
    report = SessionAuditEngine().audit([tool, decision])

    assert report["questions"]["outcome"]["failures"] == []
    where = report["questions"]["where_it_failed"]
    assert where["first_bad_decision"] is None
    assert where["first_bad_decision_detail"] is None


# ---------------------------------------------------------------------------
# Additive-key regressions (previous slice's fields unchanged)
# ---------------------------------------------------------------------------


def test_detail_additive_keys_regression():
    # The five pre-existing typing fields keep their behavior; the MAST keys
    # are additive on top (uca/fault values pinned by test_failure_typing).
    report = SessionAuditEngine().audit([_decision("mst-add-d1", confidence=0.9)])

    where = report["questions"]["where_it_failed"]
    assert where["first_bad_decision"] == "mst-add-d1"
    assert isinstance(where["first_bad_decision"], str)
    detail = where["first_bad_decision_detail"]
    assert set(detail) >= {
        "event_id",
        "uca_type",
        "fault_side",
        "interaction_edge",
        "derivation",
        "mast_mode",
        "mast_category",
    }
    assert detail["uca_type"] == "wrong"
    assert detail["fault_side"] == "model_produced"
    assert detail["mast_mode"] == "no_or_incomplete_verification"
    # The derivation still names the uca rule first, the mast rule second.
    assert "rule 4" in detail["derivation"]
    assert "mast rule 5" in detail["derivation"]


def test_outcome_failure_entries_keys_are_additive():
    # Every outcome-block failure entry keeps its four original keys and
    # gains exactly the two MAST keys.
    events = [
        _event("mst-keys-f1", EventType.TOOL_RESULT, tool_name="api", error="500"),
        _event("mst-keys-r1", EventType.REFUSAL, reason="blocked"),
        _event("mst-keys-p1", EventType.POLICY_VIOLATION, violation_type="prod_write"),
    ]
    entries = _outcome_failures(events)

    assert len(entries) == 3
    for entry in entries:
        assert set(entry) >= {
            "event_id",
            "mode",
            "symptom",
            "likely_cause_event_id",
            "mast_mode",
            "mast_category",
        }
        assert entry["mast_mode"] in FULL_MAST_MODES | {"unmapped"}
        assert entry["mast_category"] in {"C1", "C3", None}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_mast_fields_are_deterministic():
    events = _single_agent_traces()[1] + [
        _event("mst-det-e1", EventType.ERROR, error_type="RuntimeError", error_message="x")
    ]
    engine = SessionAuditEngine()
    first = engine.audit(copy.deepcopy(events))
    second = engine.audit(copy.deepcopy(events))

    assert first["questions"]["where_it_failed"] == second["questions"]["where_it_failed"]
    assert first["questions"]["outcome"]["failures"] == second["questions"]["outcome"]["failures"]
    assert first["signals"] == second["signals"]
