"""Tests for collector/audit/failure_narrative.py — the latent-conditions layer.

Covers the human-error (Reason) latent-failures note's active/latent split in
the failure narrative: the first bad decision stays the ACTIVE failure
(``mechanism["first_bad_decision"]`` is the bare event id, unchanged) while
the dormant upstream weaknesses that made it likely are reported as
``mechanism["latent_conditions"]`` — capture conditions from the session
completeness diagnostics (missing sequence numbers, orphaned parents,
truncation markers, non-monotonic timestamps) and evidence-system conditions
from the report's own signals (stale evidence, unsupported claims) plus goal
drift, always excluding the active failure itself. Capture conditions come
first; the list is capped at 4; the narrative text stays silent when the
list is empty ("none found", never "none existed").
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine
from collector.audit.failure_narrative import build_failure_narrative

BASE_TS = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers (mirror test_failure_narrative.py conventions). Every event id is
# prefixed "lcl-" and unique per test (xdist collision rule from project
# memory: ids must never repeat across seedings).
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    *,
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    timestamp: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    **data: Any,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id="latent-conditions-session",
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp if timestamp is not None else BASE_TS,
        data=data,
        metadata=metadata or {},
        upstream_event_ids=upstream_event_ids or [],
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    chosen_action: str = "act",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    **data: Any,
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


def _clean_session(prefix: str) -> list[TraceEvent]:
    """Decision + failed tool call whose capture is clean (no latent conditions)."""
    decision = _decision(
        f"{prefix}-d1",
        confidence=0.9,
        chosen_action="call_api",
        timestamp=BASE_TS,
    )
    failure = _event(
        f"{prefix}-f1",
        EventType.TOOL_RESULT,
        parent_id=f"{prefix}-d1",
        upstream_event_ids=[f"{prefix}-d1"],
        timestamp=BASE_TS + timedelta(seconds=1),
        tool_name="api",
        error="500",
    )
    return [decision, failure]


def _signal(
    event_id: str,
    signal_type: str,
    *,
    severity: str = "medium",
    message: str = "signal message",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": signal_type,
        "severity": severity,
        "message": message,
    }


def _report(
    *,
    failure_event_id: str,
    cause_event_id: str | None,
    signals: list[dict[str, Any]] | None = None,
    goal_drift: dict[str, Any] | None = None,
    where_it_failed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Minimal audit-report dict with exactly the fields the narrative reads."""
    return {
        "signals": signals or [],
        "goal_drift": goal_drift or {},
        "failures": [
            {
                "event_id": failure_event_id,
                "mode": "tool_execution_failure",
                "symptom": "Tool api failed with 500",
                "likely_cause_event_id": cause_event_id,
                "confidence": 0.8,
                "supporting_event_ids": [cause_event_id, failure_event_id],
            }
        ],
        "questions": {"where_it_failed": where_it_failed or {}},
    }


# ---------------------------------------------------------------------------
# Evidence-system conditions (report signals + goal drift)
# ---------------------------------------------------------------------------


def test_stale_evidence_off_the_first_bad_decision_is_a_latent_condition():
    # d1 cites the older fact while a newer one existed at decision time ->
    # stale_evidence signal on d1; d2 is the earliest bad decision (its
    # subtree failed), so d2 is the ACTIVE failure and the stale signal on
    # d1 survives as a latent condition behind it.
    old_tool = _event(
        "lcl-ev-t-old",
        EventType.TOOL_RESULT,
        timestamp=BASE_TS,
        tool_name="search",
        result={"hits": 1},
    )
    fresh_tool = _event(
        "lcl-ev-t-fresh",
        EventType.TOOL_RESULT,
        timestamp=BASE_TS + timedelta(minutes=5),
        tool_name="search",
        result={"hits": 99},
    )
    stale_decision = _decision(
        "lcl-ev-d1",
        confidence=0.8,
        chosen_action="call_api",
        timestamp=BASE_TS + timedelta(minutes=6),
        evidence_event_ids=["lcl-ev-t-old"],
    )
    bad_decision = _decision(
        "lcl-ev-d2",
        confidence=0.85,
        chosen_action="deploy",
        timestamp=BASE_TS + timedelta(minutes=7),
    )
    failure = _event(
        "lcl-ev-f1",
        EventType.TOOL_RESULT,
        parent_id="lcl-ev-d2",
        upstream_event_ids=["lcl-ev-d2"],
        timestamp=BASE_TS + timedelta(minutes=8),
        tool_name="deploy",
        error="boom",
    )

    report = SessionAuditEngine().audit(
        [old_tool, fresh_tool, stale_decision, bad_decision, failure]
    )
    assert report["questions"]["where_it_failed"]["first_bad_decision"] == "lcl-ev-d2"
    stale_messages = [
        signal["message"]
        for signal in report["signals"]
        if signal["type"] == "stale_evidence"
    ]
    assert stale_messages, "scenario must actually produce a stale-evidence signal"

    mechanism = report["failure_narrative"]["mechanism"]
    assert mechanism["first_bad_decision"] == "lcl-ev-d2"
    assert mechanism["latent_conditions"] == [
        {
            "type": "stale_evidence",
            "label": "acted on superseded evidence",
            "text": stale_messages[0],
            "event_id": "lcl-ev-d1",
        }
    ]


def test_stale_evidence_on_the_first_bad_decision_is_excluded():
    # A signal anchored on the first bad decision IS the active failure,
    # never a latent condition of itself; the off-decision signal survives.
    events = _clean_session("lcl-on")
    report = _report(
        failure_event_id="lcl-on-f1",
        cause_event_id="lcl-on-d1",
        signals=[
            _signal("lcl-on-d1", "stale_evidence"),
            _signal("lcl-on-f1", "unsupported_claim", severity="high"),
        ],
        where_it_failed={"first_bad_decision": "lcl-on-d1"},
    )

    mechanism = build_failure_narrative(events, report)["mechanism"]
    assert mechanism["latent_conditions"] == [
        {
            "type": "unsupported_claim",
            "label": "assertion without evidence",
            "text": "signal message",
            "event_id": "lcl-on-f1",
        }
    ]


def test_goal_drift_is_a_latent_condition():
    # The objective is established by d1 then abandoned: goal_drift.drifted
    # flips true and the narrative names the enabling condition.
    goal = _event("lcl-gd-a1", EventType.AGENT_START, goal="migrate billing database")
    on_topic = _decision(
        "lcl-gd-d1",
        confidence=0.6,
        chosen_action="inspect billing schema",
        reasoning="migrate billing database step",
    )
    off_topic_1 = _decision(
        "lcl-gd-d2", confidence=0.6, chosen_action="read the news", reasoning="check headlines"
    )
    off_topic_2 = _decision(
        "lcl-gd-d3", confidence=0.6, chosen_action="nap", reasoning="sleep a while"
    )
    failure = _event(
        "lcl-gd-f1",
        EventType.TOOL_RESULT,
        parent_id="lcl-gd-d3",
        upstream_event_ids=["lcl-gd-d3"],
        tool_name="deploy",
        error="boom",
    )

    report = SessionAuditEngine().audit([goal, on_topic, off_topic_1, off_topic_2, failure])
    assert report["goal_drift"]["drifted"] is True

    latent = report["failure_narrative"]["mechanism"]["latent_conditions"]
    drift_entries = [item for item in latent if item["type"] == "goal_drift"]
    assert len(drift_entries) == 1
    assert drift_entries[0]["label"] == "objective no longer referenced"
    assert drift_entries[0]["event_id"] == report["goal_drift"]["first_drift_event_id"]
    # The text names the count of decisions taken after the last reference.
    assert str(report["goal_drift"]["decisions_after_last_reference"]) in drift_entries[0]["text"]


def test_evidence_conditions_ordered_by_severity_then_first_appearance():
    # High severity beats medium regardless of list order; a repeated signal
    # type collapses to its first surviving occurrence.
    events = _clean_session("lcl-sev")
    report = _report(
        failure_event_id="lcl-sev-f1",
        cause_event_id="lcl-sev-d1",
        signals=[
            _signal("lcl-sev-d2", "stale_evidence"),
            _signal("lcl-sev-d3", "stale_evidence"),
            _signal("lcl-sev-f1", "unsupported_claim", severity="high"),
        ],
        where_it_failed={"first_bad_decision": "lcl-sev-d1"},
    )

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert [item["type"] for item in latent] == ["unsupported_claim", "stale_evidence"]
    stale_entries = [item for item in latent if item["type"] == "stale_evidence"]
    assert [item["event_id"] for item in stale_entries] == ["lcl-sev-d2"]


# ---------------------------------------------------------------------------
# Capture conditions (session completeness diagnostics)
# ---------------------------------------------------------------------------


def test_missing_sequence_numbers_fire_missing_events_condition():
    # Sequences 1 and 3 persisted: emission position 2 was lost in delivery.
    events = [
        _decision(
            "lcl-seq-d1",
            confidence=0.9,
            chosen_action="call_api",
            timestamp=BASE_TS,
            metadata={"sequence": 1},
        ),
        _event(
            "lcl-seq-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-seq-d1",
            upstream_event_ids=["lcl-seq-d1"],
            timestamp=BASE_TS + timedelta(seconds=1),
            metadata={"sequence": 3},
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(failure_event_id="lcl-seq-f1", cause_event_id="lcl-seq-d1")

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert len(latent) == 1
    assert latent[0]["type"] == "missing_events"
    assert latent[0]["label"] == "silent recorder gap — sequence numbers missing"
    assert latent[0]["event_id"] is None
    assert "1" in latent[0]["text"]  # names the count


def test_orphaned_parent_fires_capture_hole_condition():
    events = [
        _decision(
            "lcl-orph-d1",
            confidence=0.9,
            chosen_action="call_api",
            parent_id="lcl-orph-ghost",
            timestamp=BASE_TS,
        ),
        _event(
            "lcl-orph-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-orph-d1",
            upstream_event_ids=["lcl-orph-d1"],
            timestamp=BASE_TS + timedelta(seconds=1),
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(failure_event_id="lcl-orph-f1", cause_event_id="lcl-orph-d1")

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert len(latent) == 1
    assert latent[0]["type"] == "orphaned_events"
    assert latent[0]["label"] == "orphaned events — capture holes"
    assert latent[0]["event_id"] is None
    assert "1" in latent[0]["text"]


def test_truncation_marker_fires_truncated_condition():
    # The ingestion pipeline's metadata flag for oversized payloads.
    events = [
        _decision(
            "lcl-trun-d1",
            confidence=0.9,
            chosen_action="call_api",
            timestamp=BASE_TS,
            metadata={"_truncated": True},
        ),
        _event(
            "lcl-trun-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-trun-d1",
            upstream_event_ids=["lcl-trun-d1"],
            timestamp=BASE_TS + timedelta(seconds=1),
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(failure_event_id="lcl-trun-f1", cause_event_id="lcl-trun-d1")

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert len(latent) == 1
    assert latent[0]["type"] == "truncated_events"
    assert latent[0]["label"] == "truncated events — detail lost at capture"
    assert latent[0]["event_id"] is None
    assert "1" in latent[0]["text"]


def test_non_monotonic_timestamps_fire_ordering_condition():
    # No sequence markers: emission order is the given order, whose second
    # timestamp regresses — one regression.
    events = [
        _decision(
            "lcl-nm-d1",
            confidence=0.9,
            chosen_action="call_api",
            timestamp=BASE_TS + timedelta(seconds=10),
        ),
        _event(
            "lcl-nm-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-nm-d1",
            upstream_event_ids=["lcl-nm-d1"],
            timestamp=BASE_TS,
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(failure_event_id="lcl-nm-f1", cause_event_id="lcl-nm-d1")

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert len(latent) == 1
    assert latent[0]["type"] == "non_monotonic_timestamps"
    assert latent[0]["label"] == "non-monotonic timestamps — ordering untrustworthy"
    assert latent[0]["event_id"] is None
    assert "1" in latent[0]["text"]


# ---------------------------------------------------------------------------
# Cap + ordering across the two groups
# ---------------------------------------------------------------------------


def _four_capture_condition_events() -> list[TraceEvent]:
    """One event list firing all four capture conditions, each with count 1.

    Sequence markers 1/3/4 (position 2 lost), e2's parent is a ghost id, e3
    carries the truncation flag, and e3's timestamp regresses against
    emission order (1 -> 3 -> 4 with timestamps T, T+10s, T+5s).
    """
    return [
        _event(
            "lcl-cap-e1",
            EventType.TOOL_CALL,
            timestamp=BASE_TS,
            metadata={"sequence": 1},
        ),
        _event(
            "lcl-cap-e2",
            EventType.DECISION,
            parent_id="lcl-cap-ghost",
            timestamp=BASE_TS + timedelta(seconds=10),
            metadata={"sequence": 3},
            confidence=0.5,
        ),
        _event(
            "lcl-cap-e3",
            EventType.TOOL_RESULT,
            timestamp=BASE_TS + timedelta(seconds=5),
            metadata={"sequence": 4, "_truncated": True},
            tool_name="api",
            error="500",
        ),
    ]


def test_latent_conditions_capped_at_four_capture_first():
    # All four capture conditions fire; the stale-evidence signal would be a
    # fifth entry and is the one the cap drops.
    events = _four_capture_condition_events()
    report = _report(
        failure_event_id="lcl-cap-e3",
        cause_event_id="lcl-cap-e1",
        signals=[_signal("lcl-cap-e1", "stale_evidence")],
    )

    latent = build_failure_narrative(events, report)["mechanism"]["latent_conditions"]
    assert [item["type"] for item in latent] == [
        "missing_events",
        "orphaned_events",
        "truncated_events",
        "non_monotonic_timestamps",
    ]
    assert all("1" in item["text"] for item in latent)


def test_capture_conditions_precede_evidence_conditions():
    # The orphan (capture) is listed before the stale-evidence signal
    # (evidence-system), and both labels reach the narrative sentence.
    events = [
        _decision(
            "lcl-ord-d1",
            confidence=0.9,
            chosen_action="call_api",
            parent_id="lcl-ord-ghost",
            timestamp=BASE_TS,
        ),
        _event(
            "lcl-ord-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-ord-d1",
            upstream_event_ids=["lcl-ord-d1"],
            timestamp=BASE_TS + timedelta(seconds=1),
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(
        failure_event_id="lcl-ord-f1",
        cause_event_id="lcl-ord-d1",
        signals=[_signal("lcl-ord-f1", "stale_evidence")],
        where_it_failed={"first_bad_decision": "lcl-ord-d1"},
    )

    narrative = build_failure_narrative(events, report)
    latent = narrative["mechanism"]["latent_conditions"]
    assert [item["type"] for item in latent] == ["orphaned_events", "stale_evidence"]
    assert (
        "Latent conditions: orphaned events — capture holes, acted on superseded evidence."
        in narrative["narrative"]
    )


# ---------------------------------------------------------------------------
# Narrative text + first-bad-decision display
# ---------------------------------------------------------------------------


def test_narrative_text_lists_latent_conditions_iff_non_empty():
    # Non-empty: the sentence lands right after the contributing-factors one.
    events = [
        _decision(
            "lcl-txt-d1",
            confidence=0.9,
            chosen_action="call_api",
            parent_id="lcl-txt-ghost",
            timestamp=BASE_TS,
        ),
        _event(
            "lcl-txt-f1",
            EventType.TOOL_RESULT,
            parent_id="lcl-txt-d1",
            upstream_event_ids=["lcl-txt-d1"],
            timestamp=BASE_TS + timedelta(seconds=1),
            tool_name="api",
            error="500",
        ),
    ]
    report = _report(
        failure_event_id="lcl-txt-f1",
        cause_event_id="lcl-txt-d1",
        signals=[_signal("lcl-txt-f1", "stale_evidence")],
        where_it_failed={"first_bad_decision": "lcl-txt-d1"},
    )
    narrative_text = build_failure_narrative(events, report)["narrative"]
    assert "Latent conditions:" in narrative_text
    assert narrative_text.index("Contributing factors:") < narrative_text.index("Latent conditions:")

    # Empty: nothing is claimed — "none found" is silence, never a sentence
    # asserting absence.
    clean = SessionAuditEngine().audit(_clean_session("lcl-txt-clean"))
    mechanism = clean["failure_narrative"]["mechanism"]
    assert mechanism["latent_conditions"] == []
    assert "Latent conditions" not in clean["failure_narrative"]["narrative"]


def test_first_bad_decision_detail_passes_through_untouched():
    detail = {
        "event_id": "lcl-det-d1",
        "reason": "unsupported",
        "candidates": [
            {"event_id": "lcl-det-d1", "why": "no evidence"},
            {"event_id": "lcl-det-f1", "why": "observed failure"},
        ],
        "note": "arbitrary internal shape must pass through unchanged",
    }
    events = _clean_session("lcl-det")
    report = _report(
        failure_event_id="lcl-det-f1",
        cause_event_id="lcl-det-d1",
        where_it_failed={
            "first_bad_decision": "lcl-det-d1",
            "first_bad_decision_detail": detail,
        },
    )

    mechanism = build_failure_narrative(events, report)["mechanism"]
    # The bare event id stays exactly as-is (backward compatibility)...
    assert mechanism["first_bad_decision"] == "lcl-det-d1"
    # ...with the detail dict as an untouched sibling.
    assert mechanism["first_bad_decision_detail"] == detail
    assert report["questions"]["where_it_failed"]["first_bad_decision_detail"] == detail


def test_first_bad_decision_detail_omitted_when_absent():
    # Old reports (the parallel field does not exist yet) serialize with the
    # key entirely absent, not null.
    events = _clean_session("lcl-abs")
    report = _report(
        failure_event_id="lcl-abs-f1",
        cause_event_id="lcl-abs-d1",
        where_it_failed={"first_bad_decision": "lcl-abs-d1"},
    )

    mechanism = build_failure_narrative(events, report)["mechanism"]
    assert mechanism["first_bad_decision"] == "lcl-abs-d1"
    assert "first_bad_decision_detail" not in mechanism


# ---------------------------------------------------------------------------
# Determinism + purity
# ---------------------------------------------------------------------------


def test_latent_conditions_deterministic_and_report_untouched():
    events = _four_capture_condition_events()
    report = _report(
        failure_event_id="lcl-cap-e3",
        cause_event_id="lcl-cap-e1",
        signals=[_signal("lcl-cap-e2", "unsupported_claim", severity="high")],
        goal_drift={
            "drifted": True,
            "first_drift_event_id": "lcl-cap-e2",
            "decisions_after_last_reference": 2,
        },
        where_it_failed={"first_bad_decision": "lcl-cap-e1"},
    )
    snapshot = copy.deepcopy(report)

    first = build_failure_narrative(copy.deepcopy(events), report)
    second = build_failure_narrative(copy.deepcopy(events), report)

    assert first == second
    assert report == snapshot  # the narrative never mutates its inputs
