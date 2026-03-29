"""Tests for collector/highlights.py — highlight generation and ranking."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.events.base import EventType, TraceEvent
from collector.highlights import Highlight, generate_highlights

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(event_type: EventType, data: dict | None = None, event_id: str | None = None) -> TraceEvent:
    kwargs: dict = {"event_type": event_type, "data": data or {}}
    if event_id:
        kwargs["id"] = event_id
    return TraceEvent(**kwargs)


def _ranking(event_id: str, severity: float = 0.0, composite: float = 0.0) -> dict:
    return {"event_id": event_id, "severity": severity, "composite": composite}


def _headline(event: TraceEvent) -> str:
    return f"headline:{event.event_type}"


# ---------------------------------------------------------------------------
# Highlight dataclass
# ---------------------------------------------------------------------------


def test_highlight_dataclass_fields():
    h = Highlight(
        event_id="e1",
        event_type="error",
        highlight_type="error",
        importance=0.9,
        reason="Test",
        timestamp="2024-01-01T00:00:00",
    )
    assert h.event_id == "e1"
    assert h.importance == 0.9


# ---------------------------------------------------------------------------
# generate_highlights — empty / no-op cases
# ---------------------------------------------------------------------------


def test_generate_highlights_empty_events():
    result = generate_highlights([], [], _headline)
    assert result == []


def test_generate_highlights_no_rankings_keeps_events_below_threshold():
    # Without ranking entries severity=0, composite=0 → below threshold
    event = _event(EventType.ERROR, event_id="e1")
    result = generate_highlights([event], [], _headline)
    assert result == []


def test_generate_highlights_event_without_matching_ranking_excluded():
    event = _event(EventType.ERROR, event_id="no-ranking")
    rankings = [_ranking("other-id", severity=0.9, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result == []


def test_generate_highlights_uncategorized_type_excluded():
    # AGENT_START is not a highlight-triggering event type
    event = _event(EventType.AGENT_START, event_id="e1")
    rankings = [_ranking("e1", severity=0.9, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result == []


# ---------------------------------------------------------------------------
# Threshold behaviour
# ---------------------------------------------------------------------------


def test_generate_highlights_severity_above_threshold_included():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.6, composite=0.3)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1


def test_generate_highlights_composite_above_threshold_included():
    event = _event(EventType.REFUSAL, event_id="e1")
    rankings = [_ranking("e1", severity=0.3, composite=0.7)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1


def test_generate_highlights_both_below_threshold_excluded():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.4, composite=0.4)]
    result = generate_highlights([event], rankings, _headline)
    assert result == []


# ---------------------------------------------------------------------------
# Event type categorisation
# ---------------------------------------------------------------------------


def test_generate_highlights_error_event():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.7)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1
    assert result[0]["highlight_type"] == "error"
    assert result[0]["reason"] == "Error event"


def test_generate_highlights_refusal_event():
    event = _event(EventType.REFUSAL, event_id="e1")
    rankings = [_ranking("e1", severity=0.7, composite=0.8)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "refusal"
    assert "Refusal" in result[0]["reason"]


def test_generate_highlights_policy_violation_event():
    event = _event(EventType.POLICY_VIOLATION, event_id="e1")
    rankings = [_ranking("e1", severity=0.7, composite=0.8)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "refusal"
    assert "Policy violation" in result[0]["reason"]


def test_generate_highlights_behavior_alert_uses_signal():
    event = _event(EventType.BEHAVIOR_ALERT, data={"signal": "unusual_loop"}, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "anomaly"
    assert result[0]["reason"] == "unusual_loop"


def test_generate_highlights_behavior_alert_missing_signal_fallback():
    event = _event(EventType.BEHAVIOR_ALERT, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["reason"] == "Behavior anomaly"


def test_generate_highlights_safety_check_pass_excluded():
    event = _event(EventType.SAFETY_CHECK, data={"outcome": "pass"}, event_id="e1")
    rankings = [_ranking("e1", severity=0.9, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result == []


def test_generate_highlights_safety_check_fail_included():
    event = _event(EventType.SAFETY_CHECK, data={"outcome": "fail"}, event_id="e1")
    rankings = [_ranking("e1", severity=0.9, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1
    assert result[0]["highlight_type"] == "anomaly"
    assert "fail" in result[0]["reason"]


def test_generate_highlights_decision_low_confidence():
    event = _event(EventType.DECISION, data={"confidence": 0.3}, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.8)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "decision"
    assert "0.30" in result[0]["reason"]


def test_generate_highlights_decision_high_impact():
    event = _event(EventType.DECISION, data={"confidence": 0.9}, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "decision"
    assert "High-impact" in result[0]["reason"]


def test_generate_highlights_decision_unremarkable_excluded():
    # confidence >= 0.5 and composite <= 0.6 → no highlight type assigned
    event = _event(EventType.DECISION, data={"confidence": 0.8}, event_id="e1")
    rankings = [_ranking("e1", severity=0.9, composite=0.4)]
    result = generate_highlights([event], rankings, _headline)
    assert result == []


def test_generate_highlights_tool_result_with_error():
    event = _event(EventType.TOOL_RESULT, data={"error": "timeout"}, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "error"
    assert "failed" in result[0]["reason"]


def test_generate_highlights_tool_result_high_severity():
    event = _event(EventType.TOOL_RESULT, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.9)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["highlight_type"] == "anomaly"


# ---------------------------------------------------------------------------
# Output structure and ordering
# ---------------------------------------------------------------------------


def test_generate_highlights_contains_required_fields():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.7)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1
    h = result[0]
    assert "event_id" in h
    assert "event_type" in h
    assert "highlight_type" in h
    assert "importance" in h
    assert "reason" in h
    assert "timestamp" in h
    assert "headline" in h


def test_generate_highlights_headline_fn_called():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.7)]
    result = generate_highlights([event], rankings, _headline)
    assert result[0]["headline"] == "headline:error"


def test_generate_highlights_sorted_by_importance_descending():
    e1 = _event(EventType.ERROR, event_id="e1")
    e2 = _event(EventType.REFUSAL, event_id="e2")
    rankings = [
        _ranking("e1", severity=0.6, composite=0.6),
        _ranking("e2", severity=0.9, composite=0.9),
    ]
    result = generate_highlights([e1, e2], rankings, _headline)
    assert len(result) == 2
    assert result[0]["importance"] >= result[1]["importance"]
    assert result[0]["event_id"] == "e2"


def test_generate_highlights_limited_to_20():
    events = [_event(EventType.ERROR, event_id=f"e{i}") for i in range(30)]
    rankings = [_ranking(f"e{i}", severity=0.8, composite=0.8) for i in range(30)]
    result = generate_highlights(events, rankings, _headline)
    assert len(result) == 20


def test_generate_highlights_importance_rounded_to_4_decimals():
    event = _event(EventType.ERROR, event_id="e1")
    # min(0.123456, 0.654321) = 0.123456, rounded to 4dp
    rankings = [_ranking("e1", severity=0.123456, composite=0.654321)]
    result = generate_highlights([event], rankings, _headline)
    assert len(result) == 1
    assert result[0]["importance"] == round(0.123456, 4)


def test_generate_highlights_importance_uses_severity_when_composite_zero():
    event = _event(EventType.ERROR, event_id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.0)]
    result = generate_highlights([event], rankings, _headline)
    # composite=0 means threshold not met (severity=0.8 > 0.5 is OK)
    # importance = severity when composite == 0
    assert len(result) == 1
    assert result[0]["importance"] == 0.8


def test_generate_highlights_timestamp_iso_format():
    ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    event = TraceEvent(event_type=EventType.ERROR, timestamp=ts, id="e1")
    rankings = [_ranking("e1", severity=0.8, composite=0.8)]
    result = generate_highlights([event], rankings, _headline)
    assert "2024-06-01" in result[0]["timestamp"]
