"""Tests for bugs, edge cases, and testability in collector/baseline.py.

RED phase: these tests are written FIRST to prove bugs exist and define
the desired API for testability improvements. Every test here should
FAIL against the current code.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    TraceEvent,
)
from collector.baseline import (
    AgentBaseline,
    _build_multi_agent_metrics,
    _collect_session_event_metrics,
    _get_policy_template,
    _get_session_scalars,
    _get_speaker,
    _process_decision,
    _process_tool_result,
    _safe_div,
    _track_policy_shift,
    compute_baseline_from_sessions,
    detect_drift,
)

# =============================================================================
# CRITICAL BUG: confidence=0 recorded as 0.5 (falsy `or` fallback)
# baseline.py:128 — `data.get("confidence") or getattr(..., 0.5)`
# =============================================================================


class TestConfidenceZeroBug:
    """confidence=0 should be preserved, not defaulted to 0.5."""

    def test_process_decision_preserves_confidence_zero(self):
        """_process_decision should return confidence=0 when data has confidence=0."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="decision",
            data={"confidence": 0},
        )
        confidence, low_flag, grounded_flag = _process_decision(event, event.data)
        # BUG: currently returns 0.5 because `0 or 0.5` = 0.5
        assert confidence == 0.0, "confidence=0 must be preserved, not defaulted to 0.5"

    def test_process_decision_treats_zero_as_low_confidence(self):
        """confidence=0 should be flagged as low confidence (< 0.5)."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="decision",
            data={"confidence": 0},
        )
        _, low_flag, _ = _process_decision(event, event.data)
        assert low_flag == 1, "confidence=0 is below 0.5 threshold, should be flagged"

    def test_baseline_with_zero_confidence_decisions(self):
        """Baseline should correctly average zero-confidence decisions."""
        session = Session(
            id="s1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id=f"ev{i}",
                session_id="s1",
                event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc),
                name="decision",
                data={"confidence": 0},
            )
            for i in range(3)
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"s1": events},
        )
        # BUG: currently returns 0.5 (default) instead of 0.0
        assert baseline.avg_decision_confidence == 0.0

    def test_baseline_low_confidence_rate_with_zero(self):
        """All zero-confidence decisions should produce 100% low_confidence_rate."""
        session = Session(
            id="s1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id="ev1",
                session_id="s1",
                event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc),
                name="decision",
                data={"confidence": 0},
            ),
            TraceEvent(
                id="ev2",
                session_id="s1",
                event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc),
                name="decision",
                data={"confidence": 0.3},
            ),
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"s1": events},
        )
        # BUG: confidence=0 gets recorded as 0.5 (not low), so rate is 50% not 100%
        assert baseline.low_confidence_rate == 1.0  # both 0 and 0.3 are < 0.5


# =============================================================================
# CRITICAL BUG: duration_ms=0 falsy fallback (same pattern)
# baseline.py:135 — `data.get("duration_ms") or getattr(...) or 0`
# =============================================================================


class TestDurationZeroBug:
    """duration_ms=0 should be preserved when it comes from data."""

    def test_process_tool_result_preserves_zero_duration(self):
        """_process_tool_result should return duration=0 when data has duration_ms=0."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="tool",
            data={"duration_ms": 0, "error": None},
        )
        duration, error_flag = _process_tool_result(event, event.data)
        # This currently returns 0 (correct by accident) but via wrong code path
        assert duration == 0.0
        assert error_flag == 0

    def test_process_tool_result_no_fallback_to_event_attribute(self):
        """If data explicitly has duration_ms=0, it should NOT fall through to event attr."""
        # Create a mock event with a different duration_ms attribute
        class MockEvent:
            duration_ms = 999

        event = MockEvent()
        data = {"duration_ms": 0, "error": None}
        duration, _ = _process_tool_result(event, data)
        # BUG: `0 or 999 or 0` = 999, should be 0
        assert duration == 0.0, "data value should take precedence, not fall through to event attr"


# =============================================================================
# CRITICAL BUG: raw division instead of _safe_div (inconsistency)
# baseline.py:346-350 — five `/` instead of `_safe_div`
# =============================================================================


class TestDivisionConsistency:
    """All divisions in compute_baseline_from_sessions should use _safe_div."""

    def test_session_with_no_decisions_safe_cost(self):
        """Session with no decisions should have cost/session computed safely."""
        session = Session(
            id="s1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
            total_cost_usd=0.05,
            total_tokens=0,
            replay_value=0.0,
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"s1": []},  # no events at all
        )
        # cost_per_session should be 0.05 (total_cost / 1 session)
        assert baseline.avg_cost_per_session == 0.05
        # These should use _safe_div pattern (return 0.0 for zero denominator)
        assert baseline.avg_decision_confidence == 0.0
        assert baseline.error_rate == 0.0

    def test_session_with_no_decisions_zero_tokens(self):
        """Session with zero total_tokens should compute tokens_per_session as 0."""
        session = Session(
            id="s1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
            total_tokens=0,
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"s1": []},
        )
        assert baseline.avg_tokens_per_session == 0


# =============================================================================
# HIGH BUG: negative values not handled in drift detection
# baseline.py:374-387
# =============================================================================


class TestNegativeValuesInDrift:
    """Negative metric values should be handled gracefully."""

    def test_negative_baseline_returns_no_alert(self):
        """Negative baseline value should not produce a misleading alert."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=-0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.5,
        )
        alerts = detect_drift(baseline, current)
        # Should not produce alerts from negative baselines
        assert len(alerts) == 0

    def test_negative_current_returns_no_alert(self):
        """Negative current value should not produce misleading alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=-0.05,
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 0

    def test_both_zero_returns_no_alert(self):
        """Both baseline and current at zero should not produce an alert."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.0,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.0,
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 0


# =============================================================================
# PRIVATE HELPER UNIT TESTS
# =============================================================================


class TestSafeDiv:
    """Direct tests for _safe_div utility."""

    def test_normal_division(self):
        assert _safe_div(10.0, 5) == 2.0

    def test_zero_denominator_returns_default(self):
        assert _safe_div(10.0, 0) == 0.0

    def test_custom_default(self):
        assert _safe_div(10.0, 0, default=-1.0) == -1.0

    def test_zero_numerator(self):
        assert _safe_div(0.0, 5) == 0.0

    def test_both_zero(self):
        assert _safe_div(0.0, 0) == 0.0

    def test_float_denominator(self):
        assert _safe_div(3.0, 2) == 1.5


class TestProcessDecision:
    """Direct tests for _process_decision."""

    def test_confidence_from_data(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d", data={"confidence": 0.8},
        )
        conf, _, _ = _process_decision(event, event.data)
        assert conf == 0.8

    def test_confidence_from_event_attribute(self):
        class MockEvent:
            confidence = 0.7
        event = MockEvent()
        conf, _, _ = _process_decision(event, {})
        assert conf == 0.7

    def test_confidence_default_when_missing(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d", data={},
        )
        conf, _, _ = _process_decision(event, event.data)
        assert conf == 0.5  # default

    def test_low_confidence_flag_true(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d", data={"confidence": 0.3},
        )
        _, low_flag, _ = _process_decision(event, event.data)
        assert low_flag == 1

    def test_low_confidence_flag_false(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d", data={"confidence": 0.8},
        )
        _, low_flag, _ = _process_decision(event, event.data)
        assert low_flag == 0

    def test_grounded_flag_with_evidence(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d",
            data={"confidence": 0.8, "evidence_event_ids": ["ev1"]},
        )
        _, _, grounded = _process_decision(event, event.data)
        assert grounded == 1

    def test_grounded_flag_without_evidence(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d",
            data={"confidence": 0.8},
        )
        _, _, grounded = _process_decision(event, event.data)
        assert grounded == 0

    def test_grounded_flag_with_empty_list(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d",
            data={"confidence": 0.8, "evidence_event_ids": []},
        )
        _, _, grounded = _process_decision(event, event.data)
        # Empty list is falsy — should be 0
        assert grounded == 0


class TestProcessToolResult:
    """Direct tests for _process_tool_result."""

    def test_duration_from_data(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc), name="t",
            data={"duration_ms": 250},
        )
        duration, _ = _process_tool_result(event, event.data)
        assert duration == 250.0

    def test_error_flag_true(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc), name="t",
            data={"duration_ms": 100, "error": "timeout"},
        )
        _, error = _process_tool_result(event, event.data)
        assert error == 1

    def test_error_flag_false(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc), name="t",
            data={"duration_ms": 100, "error": None},
        )
        _, error = _process_tool_result(event, event.data)
        assert error == 0

    def test_error_flag_false_when_missing(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc), name="t",
            data={"duration_ms": 100},
        )
        _, error = _process_tool_result(event, event.data)
        assert error == 0

    def test_error_flag_with_empty_string(self):
        """Empty string error should be falsy (no error)."""
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc), name="t",
            data={"duration_ms": 100, "error": ""},
        )
        _, error = _process_tool_result(event, event.data)
        assert error == 0


class TestCollectSessionEventMetrics:
    """Direct tests for _collect_session_event_metrics."""

    def test_empty_events(self):
        result = _collect_session_event_metrics([])
        assert result["decision_count"] == 0
        assert result["tool_result_count"] == 0
        assert result["has_tool_loop"] is False
        assert result["has_refusal"] is False
        assert result["has_escalation"] is False
        assert result["speakers"] == set()
        assert result["policy_shift_count"] == 0
        assert result["turn_count"] == 0
        assert result["grounded_decisions"] == 0

    def test_refusal_event(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.REFUSAL,
            timestamp=datetime.now(timezone.utc), name="refusal", data={},
        )
        result = _collect_session_event_metrics([event])
        assert result["has_refusal"] is True

    def test_policy_violation_triggers_refusal_and_escalation(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.POLICY_VIOLATION,
            timestamp=datetime.now(timezone.utc), name="violation", data={},
        )
        result = _collect_session_event_metrics([event])
        assert result["has_refusal"] is True
        assert result["has_escalation"] is True

    def test_safety_check_triggers_escalation(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.SAFETY_CHECK,
            timestamp=datetime.now(timezone.utc), name="safety", data={},
        )
        result = _collect_session_event_metrics([event])
        assert result["has_escalation"] is True

    def test_tool_loop_behavior_alert(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime.now(timezone.utc), name="alert",
            data={"alert_type": "tool_loop"},
        )
        result = _collect_session_event_metrics([event])
        assert result["has_tool_loop"] is True

    def test_non_tool_loop_alert_ignored(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime.now(timezone.utc), name="alert",
            data={"alert_type": "something_else"},
        )
        result = _collect_session_event_metrics([event])
        assert result["has_tool_loop"] is False

    def test_agent_turn_tracks_speakers(self):
        events = [
            TraceEvent(
                id="ev1", session_id="s1", event_type=EventType.AGENT_TURN,
                timestamp=datetime.now(timezone.utc), name="turn",
                data={"speaker": "agent-a"},
            ),
            TraceEvent(
                id="ev2", session_id="s1", event_type=EventType.AGENT_TURN,
                timestamp=datetime.now(timezone.utc), name="turn",
                data={"speaker": "agent-b"},
            ),
        ]
        result = _collect_session_event_metrics(events)
        assert result["turn_count"] == 2
        assert result["speakers"] == {"agent-a", "agent-b"}

    def test_agent_turn_with_agent_id_fallback(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.AGENT_TURN,
            timestamp=datetime.now(timezone.utc), name="turn",
            data={"agent_id": "agent-x"},
        )
        result = _collect_session_event_metrics([event])
        assert result["speakers"] == {"agent-x"}

    def test_none_speaker_excluded(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.AGENT_TURN,
            timestamp=datetime.now(timezone.utc), name="turn",
            data={"speaker": None},
        )
        result = _collect_session_event_metrics([event])
        assert result["speakers"] == set()

    def test_policy_shifts_counted(self):
        events = [
            TraceEvent(
                id="ev1", session_id="s1", event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc), name="policy",
                data={"template_id": "template-a"},
            ),
            TraceEvent(
                id="ev2", session_id="s1", event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc), name="policy",
                data={"template_id": "template-b"},
            ),
            TraceEvent(
                id="ev3", session_id="s1", event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc), name="policy",
                data={"template_id": "template-a"},
            ),
        ]
        result = _collect_session_event_metrics(events)
        # a->b = 1 shift, b->a = 1 shift = 2 total
        assert result["policy_shift_count"] == 2

    def test_policy_shift_uses_name_fallback(self):
        events = [
            TraceEvent(
                id="ev1", session_id="s1", event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc), name="policy",
                data={"name": "policy-x"},
            ),
            TraceEvent(
                id="ev2", session_id="s1", event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc), name="policy",
                data={"name": "policy-y"},
            ),
        ]
        result = _collect_session_event_metrics(events)
        assert result["policy_shift_count"] == 1

    def test_unknown_event_type_ignored(self):
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc), name="llm", data={},
        )
        result = _collect_session_event_metrics([event])
        assert result["decision_count"] == 0
        assert result["tool_result_count"] == 0


class TestGetSessionScalars:
    """Direct tests for _get_session_scalars."""

    def test_normal_session(self):
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=datetime.now(timezone.utc),
            total_cost_usd=0.05, total_tokens=500, replay_value=0.8,
        )
        cost, tokens, replay = _get_session_scalars(session)
        assert cost == 0.05
        assert tokens == 500
        assert replay == 0.8

    def test_session_with_none_scalars(self):
        """Session with None scalar values should default to 0."""
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=datetime.now(timezone.utc),
        )
        cost, tokens, replay = _get_session_scalars(session)
        assert cost == 0.0
        assert tokens == 0
        assert replay == 0.0


class TestBuildMultiAgentMetrics:
    """Direct tests for _build_multi_agent_metrics."""

    def test_all_zeros(self):
        metrics = _build_multi_agent_metrics(0, 0, 0, 0, 0, 0, 0)
        assert metrics.avg_policy_shifts_per_session == 0.0
        assert metrics.avg_turns_per_session == 0
        assert metrics.avg_speaker_count == 0.0
        assert metrics.escalation_pattern_rate == 0.0
        assert metrics.evidence_grounding_rate == 0.0

    def test_zero_session_count_safe(self):
        metrics = _build_multi_agent_metrics(5, 10, 4, 2, 3, 5, 0)
        assert metrics.avg_policy_shifts_per_session == 0.0
        assert metrics.avg_turns_per_session == 0
        assert metrics.escalation_pattern_rate == 0.0

    def test_normal_values(self):
        metrics = _build_multi_agent_metrics(
            total_policy_shifts=6,
            total_turns=30,
            total_speakers=6,
            escalation_sessions=2,
            grounded_decisions=8,
            decision_count=10,
            session_count=5,
        )
        assert metrics.avg_policy_shifts_per_session == 1.2
        assert metrics.avg_turns_per_session == 6
        assert metrics.avg_speaker_count == 1.2
        assert metrics.escalation_pattern_rate == 0.4
        assert metrics.evidence_grounding_rate == 0.8


class TestGetSpeaker:
    """Direct tests for _get_speaker."""

    def test_speaker_from_data(self):
        assert _get_speaker(None, {"speaker": "agent-a"}) == "agent-a"

    def test_agent_id_fallback(self):
        assert _get_speaker(None, {"agent_id": "agent-b"}) == "agent-b"

    def test_event_attribute_fallback(self):
        class MockEvent:
            speaker = "agent-c"
        assert _get_speaker(MockEvent(), {}) == "agent-c"

    def test_none_when_missing(self):
        assert _get_speaker(None, {}) is None

    def test_data_speaker_takes_priority_over_attr(self):
        class MockEvent:
            speaker = "attr-agent"
        assert _get_speaker(MockEvent(), {"speaker": "data-agent"}) == "data-agent"


class TestGetPolicyTemplate:
    """Direct tests for _get_policy_template."""

    def test_template_id_from_data(self):
        assert _get_policy_template(None, {"template_id": "t1"}) == "t1"

    def test_name_fallback(self):
        assert _get_policy_template(None, {"name": "policy-x"}) == "policy-x"

    def test_event_attribute_fallback(self):
        class MockEvent:
            template_id = "attr-t"
        assert _get_policy_template(MockEvent(), {}) == "attr-t"

    def test_none_when_missing(self):
        assert _get_policy_template(None, {}) is None


class TestTrackPolicyShift:
    """Direct tests for _track_policy_shift."""

    def test_no_shift_same_template(self):
        prev, count = _track_policy_shift("t1", "t1", 0)
        assert prev == "t1"
        assert count == 0

    def test_first_template_no_shift(self):
        prev, count = _track_policy_shift("t1", None, 0)
        assert prev == "t1"
        assert count == 0

    def test_shift_between_templates(self):
        prev, count = _track_policy_shift("t2", "t1", 0)
        assert prev == "t2"
        assert count == 1

    def test_none_template_preserves_prev(self):
        prev, count = _track_policy_shift(None, "t1", 0)
        assert prev == "t1"
        assert count == 0

    def test_multiple_shifts(self):
        prev, count = _track_policy_shift("t2", "t1", 3)
        assert count == 4


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Edge cases that should be handled gracefully."""

    def test_events_for_unknown_session_ignored(self):
        """Events for session_ids not in the sessions list should be silently ignored."""
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=datetime.now(timezone.utc),
            total_cost_usd=0.01,
        )
        events = [
            TraceEvent(
                id="ev1", session_id="s1", event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc), name="d",
                data={"confidence": 0.9},
            ),
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={
                "s1": events,
                "unknown-session": [TraceEvent(
                    id="ev-orphan", session_id="unknown-session",
                    event_type=EventType.DECISION,
                    timestamp=datetime.now(timezone.utc), name="d",
                    data={"confidence": 0.1},
                )],
            },
        )
        assert baseline.session_count == 1
        assert baseline.avg_decision_confidence == 0.9  # only s1's event counted

    def test_session_with_no_matching_events_in_map(self):
        """Session with no entry in events_by_session should use empty list."""
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=datetime.now(timezone.utc),
            total_cost_usd=0.01,
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={},  # no events for s1
        )
        assert baseline.session_count == 1
        assert baseline.avg_decision_confidence == 0.0

    def test_event_with_missing_data_dict(self):
        """Event without a data attribute should not crash."""
        class BareEvent:
            event_type = EventType.DECISION
            id = "ev1"
            session_id = "s1"
        result = _collect_session_event_metrics([BareEvent()])
        # Should not crash; decision_count may or may not be incremented
        # depending on how getattr(event, "data", {}) works
        assert isinstance(result, dict)

    def test_event_with_none_data(self):
        """Event with data=None should not crash."""
        event = TraceEvent(
            id="ev1", session_id="s1", event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc), name="d",
            data=None,
        )
        # This might crash if code does data.get(...) on None
        result = _collect_session_event_metrics([event])
        assert isinstance(result, dict)

    def test_mixed_event_types_in_session(self):
        """Session with mixed event types should aggregate correctly."""
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id="ev1", session_id="s1", event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc), name="d",
                data={"confidence": 0.8},
            ),
            TraceEvent(
                id="ev2", session_id="s1", event_type=EventType.TOOL_RESULT,
                timestamp=datetime.now(timezone.utc), name="t",
                data={"duration_ms": 100, "error": None},
            ),
            TraceEvent(
                id="ev3", session_id="s1", event_type=EventType.REFUSAL,
                timestamp=datetime.now(timezone.utc), name="r", data={},
            ),
            TraceEvent(
                id="ev4", session_id="s1", event_type=EventType.AGENT_TURN,
                timestamp=datetime.now(timezone.utc), name="turn",
                data={"speaker": "agent-1"},
            ),
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={"s1": events},
        )
        assert baseline.avg_decision_confidence == 0.8
        assert baseline.avg_tool_duration_ms == 100.0
        assert baseline.error_rate == 0.0
        assert baseline.refusal_rate == 1.0  # 1 session with refusal / 1 session
        assert baseline.multi_agent_metrics is not None
        assert baseline.multi_agent_metrics.avg_turns_per_session == 1

    def test_multiple_sessions_some_empty(self):
        """Baseline across sessions where some have no events."""
        sessions = [
            Session(
                id=f"s{i}", agent_name="test", framework="test",
                started_at=datetime.now(timezone.utc),
                total_cost_usd=0.01 * (i + 1),
            )
            for i in range(3)
        ]
        events_by_session = {
            "s0": [
                TraceEvent(
                    id="ev1", session_id="s0", event_type=EventType.DECISION,
                    timestamp=datetime.now(timezone.utc), name="d",
                    data={"confidence": 0.9},
                ),
            ],
            # s1 has no events
            # s2 has no events
        }
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=sessions,
            events_by_session=events_by_session,
        )
        assert baseline.session_count == 3
        assert baseline.avg_decision_confidence == 0.9  # only s0 has decisions
        assert baseline.avg_cost_per_session == pytest.approx(0.02, rel=0.1)


# =============================================================================
# TESTABILITY: computed_at parameter, configurable thresholds, _is_baseline boundary
# =============================================================================


class TestDeterministicComputedAt:
    """compute_baseline_from_sessions should accept a computed_at parameter."""

    def test_computed_at_parameter(self):
        """Passing computed_at should use that value instead of datetime.now()."""
        fixed_time = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=fixed_time,
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={},
            computed_at=fixed_time,
        )
        assert baseline.computed_at == fixed_time

    def test_computed_at_defaults_to_now(self):
        """Without computed_at, should use current time."""
        before = datetime.now(timezone.utc)
        session = Session(
            id="s1", agent_name="test", framework="test",
            started_at=before,
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={},
        )
        after = datetime.now(timezone.utc)
        assert before <= baseline.computed_at <= after


class TestConfigurableThresholds:
    """detect_drift should accept configurable warning/critical thresholds."""

    def test_custom_warning_threshold(self):
        """Custom warning_threshold should override the default 25%."""
        baseline = AgentBaseline(
            agent_name="test", session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test", session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.7,  # 12.5% decrease — below 25% default
        )
        # With default 25% threshold: no alert
        alerts_default = detect_drift(baseline, current)
        assert len(alerts_default) == 0

        # With 10% warning threshold: should alert
        alerts_custom = detect_drift(
            baseline, current,
            warning_threshold=0.10,
        )
        assert len(alerts_custom) == 1
        assert alerts_custom[0].severity == "warning"

    def test_custom_critical_threshold(self):
        """Custom critical_threshold should override the default 50%."""
        baseline = AgentBaseline(
            agent_name="test", session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test", session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.14,  # 40% increase — warning at 25%, below 50% critical
        )
        # Default: warning
        alerts_default = detect_drift(baseline, current)
        assert len(alerts_default) == 1
        assert alerts_default[0].severity == "warning"

        # With 30% critical threshold: should be critical
        alerts_custom = detect_drift(
            baseline, current,
            critical_threshold=0.30,
        )
        assert len(alerts_custom) == 1
        assert alerts_custom[0].severity == "critical"

    def test_thresholds_default_to_module_constants(self):
        """Without custom thresholds, should use WARNING_THRESHOLD and CRITICAL_THRESHOLD."""
        baseline = AgentBaseline(
            agent_name="test", session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        # Exactly at 25% decrease = warning boundary
        current = AgentBaseline(
            agent_name="test", session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.6,  # exactly 25% decrease
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
