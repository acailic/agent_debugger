"""Tests for agent_debugger_sdk/core/success_flow.py.

The success-flow advisory localizes a failing run's first departure from
a successful reference run's step flow (OAT paper note: failure localized
by contrast with success, no failure labels needed). Advisory-only by
construction — it must never feed the deterministic trust score.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core import build_success_flow_advisory, step_signature
from agent_debugger_sdk.core.events import EventType, TraceEvent

BASE_TIME = datetime(2026, 4, 12, 7, 0, tzinfo=timezone.utc)


def _step(event_id: str, event_type: EventType, tool_name: str | None = None) -> TraceEvent:
    data = {"tool_name": tool_name} if tool_name else {}
    return TraceEvent(
        id=event_id,
        session_id="s",
        timestamp=BASE_TIME,
        event_type=event_type,
        name=event_id,
        data=data,
    )


def test_step_signature_includes_tool_name_for_tool_events():
    assert step_signature(_step("t1", EventType.TOOL_CALL, "search")) == "tool_call:search"
    assert step_signature(_step("t2", EventType.TOOL_RESULT)) == "tool_result"
    assert step_signature(_step("d1", EventType.DECISION)) == "decision"


def test_identical_flows_report_no_divergence():
    reference = [
        _step("r1", EventType.AGENT_START),
        _step("r2", EventType.TOOL_CALL, "search"),
        _step("r3", EventType.TOOL_RESULT),
        _step("r4", EventType.DECISION),
    ]
    target = [
        _step("t1", EventType.AGENT_START),
        _step("t2", EventType.TOOL_CALL, "search"),
        _step("t3", EventType.TOOL_RESULT),
        _step("t4", EventType.DECISION),
    ]

    advisory = build_success_flow_advisory(target, reference, reference_session_id="ref-1")

    assert advisory["advisory"] is True
    assert advisory["common_prefix_steps"] == 4
    assert advisory["reference_coverage"] == 1.0
    assert advisory["first_divergence"] is None
    assert advisory["candidate_first_bad_step"] is None
    assert advisory["reference_session_id"] == "ref-1"


def test_first_divergence_localizes_departure_from_success_flow():
    reference = [
        _step("r1", EventType.AGENT_START),
        _step("r2", EventType.TOOL_CALL, "search"),
        _step("r3", EventType.TOOL_RESULT),
        _step("r4", EventType.DECISION),
    ]
    target = [
        _step("t1", EventType.AGENT_START),
        _step("t2", EventType.TOOL_CALL, "search"),
        # The run departs here: writes instead of reading the result.
        _step("t3", EventType.TOOL_CALL, "save_file"),
        _step("t4", EventType.ERROR),
    ]

    advisory = build_success_flow_advisory(target, reference)

    assert advisory["common_prefix_steps"] == 2
    divergence = advisory["first_divergence"]
    assert divergence is not None
    assert divergence["event_id"] == "t3"
    assert divergence["step_index"] == 2
    assert divergence["target_signature"] == "tool_call:save_file"
    assert divergence["reference_signature"] == "tool_result"
    assert advisory["candidate_first_bad_step"] == "t3"
    assert advisory["reference_coverage"] == 0.5
    # Advisory framing must be explicit — this is not deterministic verification.
    assert advisory["advisory"] is True
    assert "never feeds the trust" in advisory["note"].lower()


def test_target_longer_than_reference_reports_missing_reference_step():
    reference = [_step("r1", EventType.AGENT_START)]
    target = [
        _step("t1", EventType.AGENT_START),
        _step("t2", EventType.TOOL_CALL, "search"),
    ]

    advisory = build_success_flow_advisory(target, reference)

    assert advisory["common_prefix_steps"] == 1
    divergence = advisory["first_divergence"]
    assert divergence is not None
    assert divergence["reference_signature"] is None


def test_empty_reference_yields_empty_advisory():
    target = [_step("t1", EventType.AGENT_START)]
    advisory = build_success_flow_advisory(target, [])

    assert advisory["reference_steps"] == 0
    assert advisory["common_prefix_steps"] == 0
    assert advisory["first_divergence"] is None
