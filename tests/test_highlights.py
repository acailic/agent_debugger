"""Tests for highlight generation module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.highlights import Highlight, generate_highlights


class TestHighlight:
    """Tests for the Highlight dataclass."""

    def test_highlight_creation(self):
        """Test creating a highlight with all fields."""
        highlight = Highlight(
            event_id="event-123",
            event_type="ERROR",
            highlight_type="error",
            importance=0.95,
            reason="Error event",
            timestamp="2026-03-29T12:00:00Z",
        )

        assert highlight.event_id == "event-123"
        assert highlight.event_type == "ERROR"
        assert highlight.highlight_type == "error"
        assert highlight.importance == 0.95
        assert highlight.reason == "Error event"
        assert highlight.timestamp == "2026-03-29T12:00:00Z"

    def test_highlight_with_decision_type(self):
        """Test creating a highlight with decision type."""
        highlight = Highlight(
            event_id="event-456",
            event_type="DECISION",
            highlight_type="decision",
            importance=0.75,
            reason="High-impact decision",
            timestamp="2026-03-29T12:01:00Z",
        )

        assert highlight.highlight_type == "decision"
        assert highlight.importance == 0.75


class TestGenerateHighlights:
    """Tests for the generate_highlights function."""

    def test_empty_events_returns_empty_list(self):
        """Test with empty events list."""
        result = generate_highlights([], [], MagicMock())

        assert result == []

    def test_single_error_event(self):
        """Test with a single error event."""
        event = TraceEvent(
            id="error-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Test error"},
        )
        rankings = [{"event_id": "error-1", "severity": 0.9, "composite": 0.8}]
        headline_fn = MagicMock(return_value="Error: Test error")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["event_id"] == "error-1"
        assert result[0]["highlight_type"] == "error"
        assert result[0]["reason"] == "Error event"
        assert result[0]["importance"] == 0.8

    def test_refusal_event(self):
        """Test with a refusal event."""
        event = TraceEvent(
            id="refusal-1",
            timestamp=datetime.now(),
            event_type=EventType.REFUSAL,
            data={"reason": "Unsafe request"},
        )
        rankings = [{"event_id": "refusal-1", "severity": 0.8, "composite": 0.7}]
        headline_fn = MagicMock(return_value="Refusal: Unsafe request")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "refusal"
        assert result[0]["reason"] == "Refusal triggered"

    def test_policy_violation_event(self):
        """Test with a policy violation event."""
        event = TraceEvent(
            id="policy-1",
            timestamp=datetime.now(),
            event_type=EventType.POLICY_VIOLATION,
            data={"policy": "no-harm"},
        )
        rankings = [{"event_id": "policy-1", "severity": 0.85, "composite": 0.75}]
        headline_fn = MagicMock(return_value="Policy violation")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "refusal"
        assert result[0]["reason"] == "Policy violation"

    def test_behavior_alert_event(self):
        """Test with a behavior alert event."""
        event = TraceEvent(
            id="alert-1",
            timestamp=datetime.now(),
            event_type=EventType.BEHAVIOR_ALERT,
            data={"signal": "Unusual pattern detected"},
        )
        rankings = [{"event_id": "alert-1", "severity": 0.7, "composite": 0.6}]
        headline_fn = MagicMock(return_value="Behavior anomaly")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "anomaly"
        assert result[0]["reason"] == "Unusual pattern detected"

    def test_safety_check_fail_event(self):
        """Test with a failed safety check event."""
        event = TraceEvent(
            id="safety-1",
            timestamp=datetime.now(),
            event_type=EventType.SAFETY_CHECK,
            data={"outcome": "fail"},
        )
        rankings = [{"event_id": "safety-1", "severity": 0.9, "composite": 0.8}]
        headline_fn = MagicMock(return_value="Safety check failed")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "anomaly"
        assert result[0]["reason"] == "Safety check fail"

    def test_safety_check_pass_ignored(self):
        """Test that passing safety checks are not highlighted."""
        event = TraceEvent(
            id="safety-2",
            timestamp=datetime.now(),
            event_type=EventType.SAFETY_CHECK,
            data={"outcome": "pass"},
        )
        rankings = [{"event_id": "safety-2", "severity": 0.1, "composite": 0.0}]
        headline_fn = MagicMock(return_value="Safety check passed")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 0

    def test_low_confidence_decision(self):
        """Test with a low confidence decision event."""
        event = TraceEvent(
            id="decision-1",
            timestamp=datetime.now(),
            event_type=EventType.DECISION,
            data={"confidence": 0.3},
        )
        rankings = [{"event_id": "decision-1", "severity": 0.6, "composite": 0.7}]
        headline_fn = MagicMock(return_value="Low confidence decision")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "decision"
        assert result[0]["reason"] == "Low confidence decision (0.30)"

    def test_high_impact_decision(self):
        """Test with a high-impact decision event."""
        event = TraceEvent(
            id="decision-2",
            timestamp=datetime.now(),
            event_type=EventType.DECISION,
            data={"confidence": 0.8},
        )
        rankings = [{"event_id": "decision-2", "severity": 0.5, "composite": 0.7}]
        headline_fn = MagicMock(return_value="High-impact decision")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "decision"
        assert result[0]["reason"] == "High-impact decision"

    def test_tool_result_error(self):
        """Test with a tool result error event."""
        event = TraceEvent(
            id="tool-1",
            timestamp=datetime.now(),
            event_type=EventType.TOOL_RESULT,
            data={"error": "Tool execution failed"},
        )
        rankings = [{"event_id": "tool-1", "severity": 0.8, "composite": 0.7}]
        headline_fn = MagicMock(return_value="Tool error")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "error"
        assert result[0]["reason"] == "Tool execution failed"

    def test_unusual_tool_result(self):
        """Test with an unusual tool result event."""
        event = TraceEvent(
            id="tool-2",
            timestamp=datetime.now(),
            event_type=EventType.TOOL_RESULT,
            data={"result": "unusual output"},
        )
        rankings = [{"event_id": "tool-2", "severity": 0.8, "composite": 0.6}]
        headline_fn = MagicMock(return_value="Unusual tool result")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "anomaly"
        assert result[0]["reason"] == "Unusual tool result"

    def test_importance_threshold_filtering(self):
        """Test that low importance events are filtered out."""
        event = TraceEvent(
            id="low-impact-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Minor error"},
        )
        # Both severity and composite below threshold
        rankings = [{"event_id": "low-impact-1", "severity": 0.3, "composite": 0.2}]
        headline_fn = MagicMock(return_value="Low impact error")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 0

    def test_multiple_events_sorted_by_importance(self):
        """Test that multiple events are sorted by importance."""
        events = [
            TraceEvent(
                id="event-1",
                timestamp=datetime.now(),
                event_type=EventType.ERROR,
                data={"message": "Error 1"},
            ),
            TraceEvent(
                id="event-2",
                timestamp=datetime.now(),
                event_type=EventType.REFUSAL,
                data={"reason": "Refusal 1"},
            ),
            TraceEvent(
                id="event-3",
                timestamp=datetime.now(),
                event_type=EventType.DECISION,
                data={"confidence": 0.2},
            ),
        ]
        rankings = [
            {"event_id": "event-1", "severity": 0.5, "composite": 0.7},  # 0.5
            {"event_id": "event-2", "severity": 0.8, "composite": 0.9},  # 0.8
            {"event_id": "event-3", "severity": 0.9, "composite": 0.6},  # 0.6
        ]
        headline_fn = MagicMock(side_effect=lambda e: f"Headline: {e.id}")

        result = generate_highlights(events, rankings, headline_fn)

        assert len(result) == 3
        # Sorted by importance descending
        assert result[0]["event_id"] == "event-2"
        assert result[0]["importance"] == 0.8
        assert result[1]["event_id"] == "event-3"
        assert result[1]["importance"] == 0.6
        assert result[2]["event_id"] == "event-1"
        assert result[2]["importance"] == 0.5

    def test_limits_to_top_20_highlights(self):
        """Test that results are limited to top 20 highlights."""
        events = [
            TraceEvent(
                id=f"event-{i}",
                timestamp=datetime.now(),
                event_type=EventType.ERROR,
                data={"message": f"Error {i}"},
            )
            for i in range(25)
        ]
        rankings = [
            {"event_id": f"event-{i}", "severity": 0.6 + (i * 0.01), "composite": 0.7}
            for i in range(25)
        ]
        headline_fn = MagicMock(side_effect=lambda e: f"Headline: {e.id}")

        result = generate_highlights(events, rankings, headline_fn)

        assert len(result) == 20

    def test_event_without_ranking(self):
        """Test handling of events without ranking data."""
        event = TraceEvent(
            id="no-ranking-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Error without ranking"},
        )
        rankings = []
        headline_fn = MagicMock(return_value="No ranking error")

        result = generate_highlights([event], rankings, headline_fn)

        # Event without ranking gets empty dict, severity=0, composite=0
        # ERROR event gets highlight_type="error" but low importance
        # Should be filtered out since severity and composite are both 0
        assert len(result) == 0

    def test_all_same_type_events(self):
        """Test with all events of the same type."""
        events = [
            TraceEvent(
                id=f"decision-{i}",
                timestamp=datetime.now(),
                event_type=EventType.DECISION,
                data={"confidence": 0.3},
            )
            for i in range(5)
        ]
        rankings = [
            {"event_id": f"decision-{i}", "severity": 0.6, "composite": 0.7}
            for i in range(5)
        ]
        headline_fn = MagicMock(side_effect=lambda e: f"Headline: {e.id}")

        result = generate_highlights(events, rankings, headline_fn)

        assert len(result) == 5
        for highlight in result:
            assert highlight["highlight_type"] == "decision"

    def test_missing_data_fields(self):
        """Test events with missing data fields."""
        event = TraceEvent(
            id="missing-data-1",
            timestamp=datetime.now(),
            event_type=EventType.BEHAVIOR_ALERT,
            data={},  # Missing 'signal' field
        )
        rankings = [{"event_id": "missing-data-1", "severity": 0.7, "composite": 0.6}]
        headline_fn = MagicMock(return_value="Alert without signal")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["highlight_type"] == "anomaly"
        # Uses default "Behavior anomaly" when signal is missing
        assert result[0]["reason"] == "Behavior anomaly"

    def test_headline_function_called(self):
        """Test that the headline function is called for highlighted events."""
        event = TraceEvent(
            id="headline-test-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Test"},
        )
        rankings = [{"event_id": "headline-test-1", "severity": 0.8, "composite": 0.7}]
        headline_fn = MagicMock(return_value="Custom headline")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        headline_fn.assert_called_once_with(event)
        assert result[0]["headline"] == "Custom headline"

    def test_importance_calculation_with_composite(self):
        """Test importance calculation when composite > 0."""
        event = TraceEvent(
            id="importance-test-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Test"},
        )
        # When composite > 0, use min(severity, composite)
        rankings = [{"event_id": "importance-test-1", "severity": 0.9, "composite": 0.6}]
        headline_fn = MagicMock(return_value="Test headline")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["importance"] == 0.6  # min(0.9, 0.6)

    def test_importance_calculation_without_composite(self):
        """Test importance calculation when composite is 0."""
        event = TraceEvent(
            id="importance-test-2",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Test"},
        )
        # When composite is 0, use severity
        rankings = [{"event_id": "importance-test-2", "severity": 0.7, "composite": 0.0}]
        headline_fn = MagicMock(return_value="Test headline")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        assert result[0]["importance"] == 0.7  # severity

    def test_timestamp_serialization(self):
        """Test that timestamps are properly serialized."""
        event = TraceEvent(
            id="timestamp-test-1",
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            data={"message": "Test"},
        )
        rankings = [{"event_id": "timestamp-test-1", "severity": 0.8, "composite": 0.7}]
        headline_fn = MagicMock(return_value="Test headline")

        result = generate_highlights([event], rankings, headline_fn)

        assert len(result) == 1
        # Timestamp should be a string
        assert isinstance(result[0]["timestamp"], str)
        # Should be ISO format string
        assert "T" in result[0]["timestamp"] or "-" in result[0]["timestamp"]

    def test_high_confidence_decision_not_highlighted_without_composite(self):
        """Test that high confidence decisions are not highlighted without high composite."""
        event = TraceEvent(
            id="high-conf-1",
            timestamp=datetime.now(),
            event_type=EventType.DECISION,
            data={"confidence": 0.9},
        )
        # Low severity and composite
        rankings = [{"event_id": "high-conf-1", "severity": 0.3, "composite": 0.2}]
        headline_fn = MagicMock(return_value="High confidence decision")

        result = generate_highlights([event], rankings, headline_fn)

        # Not highlighted - doesn't meet low confidence or high composite criteria
        assert len(result) == 0

    def test_decision_with_exact_threshold_confidence(self):
        """Test decision with confidence exactly at threshold (0.5)."""
        event = TraceEvent(
            id="threshold-1",
            timestamp=datetime.now(),
            event_type=EventType.DECISION,
            data={"confidence": 0.5},
        )
        rankings = [{"event_id": "threshold-1", "severity": 0.6, "composite": 0.6}]
        headline_fn = MagicMock(return_value="Threshold decision")

        result = generate_highlights([event], rankings, headline_fn)

        # Confidence >= 0.5, so not highlighted as low confidence
        # Unless composite is high enough
        assert len(result) == 0
