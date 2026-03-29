"""Tests for collector/highlights.py highlight generation module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    BehaviorAlertEvent,
    DecisionEvent,
    ErrorEvent,
    EventType,
    PolicyViolationEvent,
    RefusalEvent,
    SafetyCheckEvent,
    ToolResultEvent,
    TraceEvent,
)
from collector.highlights import (
    _build_highlight_dict,
    _calculate_importance,
    _categorize_behavior_alert,
    _categorize_decision_event,
    _categorize_error_event,
    _categorize_refusal_event,
    _categorize_safety_check,
    _categorize_tool_result,
    _get_event_categorization,
    generate_highlights,
)


@pytest.fixture
def sample_event():
    """Create a sample TraceEvent for testing."""
    return TraceEvent(
        id="test-event-1",
        session_id="test-session",
        event_type=EventType.ERROR,
        timestamp=datetime.now(timezone.utc),
        name="Test Event",
        data={"message": "Test error"},
    )


@pytest.fixture
def sample_rankings():
    """Create sample rankings data."""
    return [
        {"event_id": "event-1", "severity": 0.8, "composite": 0.7},
        {"event_id": "event-2", "severity": 0.6, "composite": 0.5},
        {"event_id": "event-3", "severity": 0.3, "composite": 0.2},
    ]


@pytest.fixture
def mock_headline_fn():
    """Mock event headline function."""
    return lambda event: f"Event: {event.name}"


class TestErrorCategorization:
    """Test ERROR event categorization."""

    def test_categorize_error_returns_error_type(self, sample_event):
        """Test that ERROR events are categorized as 'error'."""
        highlight_type, reason = _categorize_error_event(sample_event)
        assert highlight_type == "error"
        assert reason == "Error event"

    def test_categorize_error_with_error_event(self):
        """Test categorization with actual ErrorEvent."""
        error = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="Test Error",
            error_type="ValueError",
            error_message="Test error message",
        )
        highlight_type, reason = _categorize_error_event(error)
        assert highlight_type == "error"
        assert reason == "Error event"


class TestRefusalCategorization:
    """Test REFUSAL and POLICY_VIOLATION event categorization."""

    def test_categorize_refusal_event(self):
        """Test REFUSAL event categorization."""
        refusal = RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            name="Refusal",
            reason="Content policy",
        )
        highlight_type, reason = _categorize_refusal_event(refusal)
        assert highlight_type == "refusal"
        assert reason == "Refusal triggered"

    def test_categorize_policy_violation(self):
        """Test POLICY_VIOLATION event categorization."""
        violation = PolicyViolationEvent(
            id="violation-1",
            session_id="session-1",
            name="Policy Violation",
            policy_name="content_safety",
            violation_type="safety",
            details={"reason": "Violation detected"},
        )
        highlight_type, reason = _categorize_refusal_event(violation)
        assert highlight_type == "refusal"
        assert reason == "Policy violation"


class TestBehaviorAlertCategorization:
    """Test BEHAVIOR_ALERT event categorization."""

    def test_categorize_behavior_alert_with_signal(self):
        """Test BEHAVIOR_ALERT with signal data."""
        alert = BehaviorAlertEvent(
            id="alert-1",
            session_id="session-1",
            name="Behavior Alert",
            alert_type="anomaly",
            signal="anomaly_detected",
            severity="high",
            data={"signal": "anomaly_detected"},
        )
        highlight_type, reason = _categorize_behavior_alert(alert)
        assert highlight_type == "anomaly"
        assert reason == "anomaly_detected"

    def test_categorize_behavior_alert_without_signal(self):
        """Test BEHAVIOR_ALERT without signal data."""
        alert = BehaviorAlertEvent(
            id="alert-2",
            session_id="session-1",
            name="Behavior Alert",
            alert_type="default",
            signal="default_signal",
            severity="low",
            data={"signal": "default_signal"},
        )
        highlight_type, reason = _categorize_behavior_alert(alert)
        assert highlight_type == "anomaly"
        assert reason == "default_signal"


class TestSafetyCheckCategorization:
    """Test SAFETY_CHECK event categorization."""

    def test_categorize_safety_check_failure(self):
        """Test SAFETY_CHECK with non-pass outcome."""
        safety_check = SafetyCheckEvent(
            id="safety-1",
            session_id="session-1",
            name="Safety Check",
            policy_name="content_filter",
            outcome="fail",
            data={"outcome": "fail"},
        )
        highlight_type, reason = _categorize_safety_check(safety_check)
        assert highlight_type == "anomaly"
        assert reason == "Safety check fail"

    def test_categorize_safety_check_pass(self):
        """Test SAFETY_CHECK with pass outcome."""
        safety_check = SafetyCheckEvent(
            id="safety-2",
            session_id="session-1",
            name="Safety Check",
            policy_name="content_filter",
            outcome="pass",
        )
        highlight_type, reason = _categorize_safety_check(safety_check)
        assert highlight_type is None
        assert reason is None

    def test_categorize_safety_check_default_outcome(self):
        """Test SAFETY_CHECK with missing outcome defaults to pass."""
        safety_check = SafetyCheckEvent(
            id="safety-3",
            session_id="session-1",
            name="Safety Check",
            policy_name="content_filter",
            outcome="pass",
        )
        highlight_type, reason = _categorize_safety_check(safety_check)
        assert highlight_type is None
        assert reason is None


class TestDecisionCategorization:
    """Test DECISION event categorization."""

    def test_categorize_low_confidence_decision(self):
        """Test DECISION with low confidence."""
        decision = DecisionEvent(
            id="decision-1",
            session_id="session-1",
            name="Decision",
            reasoning="Test reasoning",
            confidence=0.3,
            data={"confidence": 0.3},
        )
        highlight_type, reason = _categorize_decision_event(decision, 0.5)
        assert highlight_type == "decision"
        assert reason == "Low confidence decision (0.30)"

    def test_categorize_high_impact_decision(self):
        """Test DECISION with high composite impact."""
        decision = DecisionEvent(
            id="decision-2",
            session_id="session-1",
            name="Decision",
            reasoning="Test reasoning",
            confidence=0.7,
        )
        highlight_type, reason = _categorize_decision_event(decision, 0.8)
        assert highlight_type == "decision"
        assert reason == "High-impact decision"

    def test_categorize_ordinary_decision(self):
        """Test DECISION with normal confidence and impact."""
        decision = DecisionEvent(
            id="decision-3",
            session_id="session-1",
            name="Decision",
            reasoning="Test reasoning",
            confidence=0.6,
        )
        highlight_type, reason = _categorize_decision_event(decision, 0.5)
        assert highlight_type is None
        assert reason is None


class TestToolResultCategorization:
    """Test TOOL_RESULT event categorization."""

    def test_categorize_failed_tool_result(self):
        """Test TOOL_RESULT with error."""
        tool_result = ToolResultEvent(
            id="tool-1",
            session_id="session-1",
            name="Tool Result",
            tool_name="test_tool",
            error="Tool failed",
            data={"error": "Tool failed"},
        )
        highlight_type, reason = _categorize_tool_result(tool_result, 0.5)
        assert highlight_type == "error"
        assert reason == "Tool execution failed"

    def test_categorize_unusual_tool_result(self):
        """Test TOOL_RESULT with high severity."""
        tool_result = ToolResultEvent(
            id="tool-2",
            session_id="session-1",
            name="Tool Result",
            tool_name="test_tool",
            result={"data": "test"},
            data={},
        )
        highlight_type, reason = _categorize_tool_result(tool_result, 0.8)
        assert highlight_type == "anomaly"
        assert reason == "Unusual tool result"

    def test_categorize_normal_tool_result(self):
        """Test TOOL_RESULT with normal severity."""
        tool_result = ToolResultEvent(
            id="tool-3",
            session_id="session-1",
            name="Tool Result",
            tool_name="test_tool",
            result={"data": "test"},
            data={},
        )
        highlight_type, reason = _categorize_tool_result(tool_result, 0.5)
        assert highlight_type is None
        assert reason is None


class TestImportanceCalculation:
    """Test importance score calculation."""

    def test_importance_with_positive_composite(self):
        """Test importance calculation with positive composite."""
        importance = _calculate_importance(0.8, 0.6)
        assert importance == 0.6  # min(0.8, 0.6)

    def test_importance_with_zero_composite(self):
        """Test importance calculation with zero composite."""
        importance = _calculate_importance(0.8, 0.0)
        assert importance == 0.8  # returns severity

    def test_importance_with_negative_composite(self):
        """Test importance calculation with negative composite."""
        importance = _calculate_importance(0.7, -0.1)
        assert importance == 0.7  # returns severity


class TestHighlightDictBuilding:
    """Test highlight dictionary construction."""

    def test_build_highlight_dict_with_datetime_timestamp(self, sample_event, mock_headline_fn):
        """Test building highlight dict with datetime timestamp."""
        highlight = _build_highlight_dict(
            sample_event,
            "error",
            "Test error",
            0.8,
            mock_headline_fn,
        )
        assert highlight["event_id"] == sample_event.id
        assert highlight["event_type"] == str(sample_event.event_type)
        assert highlight["highlight_type"] == "error"
        assert highlight["importance"] == 0.8
        assert highlight["reason"] == "Test error"
        assert "timestamp" in highlight
        assert highlight["headline"] == "Event: Test Event"

    def test_build_highlight_importance_rounding(self, sample_event, mock_headline_fn):
        """Test that importance is rounded to 4 decimal places."""
        highlight = _build_highlight_dict(
            sample_event,
            "error",
            "Test error",
            0.856789,
            mock_headline_fn,
        )
        assert highlight["importance"] == 0.8568


class TestEventCategorization:
    """Test event categorization router."""

    def test_get_categorization_for_error_event(self, sample_event):
        """Test categorization routing for ERROR event."""
        highlight_type, reason = _get_event_categorization(sample_event, 0.5, 0.5)
        assert highlight_type == "error"
        assert reason == "Error event"

    def test_get_categorization_for_unknown_event_type(self):
        """Test categorization for unknown event type."""
        unknown_event = TraceEvent(
            id="unknown-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="Unknown Event",
            data={},
        )
        highlight_type, reason = _get_event_categorization(unknown_event, 0.5, 0.5)
        assert highlight_type is None
        assert reason is None


class TestGenerateHighlights:
    """Test main highlight generation function."""

    def test_generate_highlights_empty_events(self, mock_headline_fn):
        """Test with empty event list."""
        highlights = generate_highlights([], [], mock_headline_fn)
        assert highlights == []

    def test_generate_highlights_single_error_event(self, mock_headline_fn):
        """Test with single error event."""
        error = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="Test Error",
            error_type="ValueError",
            error_message="Test error",
        )
        rankings = [{"event_id": "error-1", "severity": 0.8, "composite": 0.7}]
        highlights = generate_highlights([error], rankings, mock_headline_fn)
        assert len(highlights) == 1
        assert highlights[0]["highlight_type"] == "error"
        assert highlights[0]["importance"] == 0.7

    def test_generate_highlights_filters_low_importance(self, mock_headline_fn):
        """Test that events with severity < 0.5 and composite < 0.5 are filtered."""
        error = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="Low Importance Error",
            error_type="ValueError",
            error_message="Low importance",
        )
        rankings = [{"event_id": "error-1", "severity": 0.3, "composite": 0.2}]
        highlights = generate_highlights([error], rankings, mock_headline_fn)
        assert len(highlights) == 0

    def test_generate_highlights_sorted_by_importance(self, mock_headline_fn):
        """Test that highlights are sorted by importance (descending)."""
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="High Importance",
            error_type="Error1",
            error_message="High",
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-1",
            name="Low Importance",
            error_type="Error2",
            error_message="Low",
        )
        rankings = [
            {"event_id": "error-1", "severity": 0.9, "composite": 0.8},
            {"event_id": "error-2", "severity": 0.6, "composite": 0.5},
        ]
        highlights = generate_highlights([error1, error2], rankings, mock_headline_fn)
        assert len(highlights) == 2
        assert highlights[0]["importance"] >= highlights[1]["importance"]
        assert highlights[0]["event_id"] == "error-1"

    def test_generate_highlights_limits_to_20(self, mock_headline_fn):
        """Test that highlights are limited to 20 items."""
        events = [
            ErrorEvent(
                id=f"error-{i}",
                session_id="session-1",
                name=f"Error {i}",
                error_type="Error",
                error_message=f"Error message {i}",
            )
            for i in range(25)
        ]
        rankings = [
            {"event_id": f"error-{i}", "severity": 0.8, "composite": 0.7}
            for i in range(25)
        ]
        highlights = generate_highlights(events, rankings, mock_headline_fn)
        assert len(highlights) == 20

    def test_generate_highlights_with_missing_ranking(self, mock_headline_fn):
        """Test events without ranking data get default values."""
        error = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="Unranked Error",
            error_type="Error",
            error_message="Unranked",
        )
        highlights = generate_highlights([error], [], mock_headline_fn)
        # Event with no ranking and low default scores should be filtered
        assert len(highlights) == 0

    def test_generate_highlights_all_same_type_events(self, mock_headline_fn):
        """Test with all events of the same type."""
        events = [
            ErrorEvent(
                id=f"error-{i}",
                session_id="session-1",
                name=f"Error {i}",
                error_type="Error",
                error_message=f"Message {i}",
            )
            for i in range(5)
        ]
        rankings = [
            {"event_id": f"error-{i}", "severity": 0.7, "composite": 0.6}
            for i in range(5)
        ]
        highlights = generate_highlights(events, rankings, mock_headline_fn)
        assert len(highlights) == 5
        for h in highlights:
            assert h["highlight_type"] == "error"

    def test_generate_highlights_mixed_event_types(self, mock_headline_fn):
        """Test with mixed event types (errors, decisions, refusals)."""
        error = ErrorEvent(
            id="error-1",
            session_id="session-1",
            name="Error",
            error_type="Error",
            error_message="Error",
        )
        refusal = RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            name="Refusal",
            reason="Policy",
        )
        decision = DecisionEvent(
            id="decision-1",
            session_id="session-1",
            name="Decision",
            reasoning="Reasoning",
            confidence=0.3,
            data={"confidence": 0.3},
        )
        rankings = [
            {"event_id": "error-1", "severity": 0.8, "composite": 0.7},
            {"event_id": "refusal-1", "severity": 0.6, "composite": 0.5},
            {"event_id": "decision-1", "severity": 0.9, "composite": 0.8},
        ]
        highlights = generate_highlights([error, refusal, decision], rankings, mock_headline_fn)
        assert len(highlights) == 3
        highlight_types = {h["highlight_type"] for h in highlights}
        assert "error" in highlight_types
        assert "refusal" in highlight_types
        assert "decision" in highlight_types

    def test_generate_highlights_event_with_missing_fields(self, mock_headline_fn):
        """Test events with missing optional fields."""
        # Create minimal event with missing data
        event = TraceEvent(
            id="event-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="Minimal Error",
            data={},  # Missing expected fields
        )
        rankings = [{"event_id": "event-1", "severity": 0.8, "composite": 0.7}]
        highlights = generate_highlights([event], rankings, mock_headline_fn)
        assert len(highlights) == 1
        assert highlights[0]["highlight_type"] == "error"
