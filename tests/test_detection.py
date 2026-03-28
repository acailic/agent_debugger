"""Tests for detection algorithms in collector/detection.py."""

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.detection import detect_oscillation

# =============================================================================
# Fixtures
# =============================================================================


def create_tool_call_event(name: str, tool_name: str = "") -> TraceEvent:
    """Create a tool call event for testing.

    Args:
        name: Event name
        tool_name: Name of the tool being called

    Returns:
        TraceEvent with tool call data
    """
    data = {"tool_name": tool_name} if tool_name else {}
    return TraceEvent(
        event_type=EventType.TOOL_CALL,
        name=name,
        data=data,
        timestamp=datetime.now(timezone.utc),
    )


def create_decision_event(name: str, chosen_action: str = "") -> TraceEvent:
    """Create a decision event for testing.

    Args:
        name: Event name
        chosen_action: The action chosen by the agent

    Returns:
        TraceEvent with decision data
    """
    data = {"chosen_action": chosen_action} if chosen_action else {}
    return TraceEvent(
        event_type=EventType.DECISION,
        name=name,
        data=data,
        timestamp=datetime.now(timezone.utc),
    )


def create_agent_turn_event(name: str) -> TraceEvent:
    """Create an agent turn event for testing.

    Args:
        name: Event name

    Returns:
        TraceEvent with agent turn type
    """
    return TraceEvent(
        event_type=EventType.AGENT_TURN,
        name=name,
        timestamp=datetime.now(timezone.utc),
    )


# =============================================================================
# Oscillation Detection Tests
# =============================================================================


class TestDetectOscillation:
    """Test suite for oscillation detection."""

    def test_no_oscillation_with_fewer_than_four_events(self):
        """Should return None when fewer than 4 events are provided."""
        events = [create_tool_call_event("tool1", "search"), create_tool_call_event("tool2", "lookup")]

        result = detect_oscillation(events)

        assert result is None

    def test_no_oscillation_with_non_oscillating_events(self):
        """Should return None when events don't form an oscillating pattern."""
        events = [
            create_tool_call_event("t1", "search"),
            create_tool_call_event("t2", "lookup"),
            create_tool_call_event("t3", "retrieve"),
            create_tool_call_event("t4", "update"),
        ]

        result = detect_oscillation(events)

        assert result is None

    def test_detects_simple_ab_oscillation_with_tools(self):
        """Should detect A->B->A->B pattern in tool calls."""
        events = [
            create_tool_call_event("call1", "search"),
            create_tool_call_event("call2", "lookup"),
            create_tool_call_event("call3", "search"),
            create_tool_call_event("call4", "lookup"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.pattern == "search->lookup"
        assert result.event_type == str(EventType.TOOL_CALL)
        assert result.repeat_count >= 2
        assert result.severity > 0
        assert len(result.event_ids) == 4

    def test_detects_abc_oscillation_with_decisions(self):
        """Should detect A->B->C->A->B->C pattern in decisions."""
        events = [
            create_decision_event("d1", "option_a"),
            create_decision_event("d2", "option_b"),
            create_decision_event("d3", "option_c"),
            create_decision_event("d4", "option_a"),
            create_decision_event("d5", "option_b"),
            create_decision_event("d6", "option_c"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.pattern == "option_a->option_b->option_c"
        assert result.event_type == str(EventType.DECISION)
        assert result.repeat_count >= 2

    def test_detects_oscillation_with_agent_turns(self):
        """Should detect oscillation in agent turn events."""
        events = [
            create_agent_turn_event("turn1"),
            create_agent_turn_event("turn2"),
            create_agent_turn_event("turn1"),
            create_agent_turn_event("turn2"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.event_type == str(EventType.AGENT_TURN)
        assert result.repeat_count >= 2

    def test_uses_tool_name_from_data_when_available(self):
        """Should prioritize tool_name from event data over event name."""
        events = [
            create_tool_call_event("generic_call", "search_api"),
            create_tool_call_event("generic_call", "lookup_db"),
            create_tool_call_event("generic_call", "search_api"),
            create_tool_call_event("generic_call", "lookup_db"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert "search_api" in result.pattern
        assert "lookup_db" in result.pattern

    def test_uses_chosen_action_from_data_for_decisions(self):
        """Should prioritize chosen_action from event data for decisions."""
        events = [
            create_decision_event("decision", "action_x"),
            create_decision_event("decision", "action_y"),
            create_decision_event("decision", "action_x"),
            create_decision_event("decision", "action_y"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.pattern == "action_x->action_y"

    def test_respects_window_parameter(self):
        """Should only consider events within the specified window."""
        events = []
        for i in range(20):
            events.append(create_tool_call_event(f"t{i}", "search" if i % 2 == 0 else "lookup"))

        result = detect_oscillation(events, window=5)

        # Should detect oscillation in the last 5 events
        assert result is not None

    def test_returns_highest_severity_oscillation(self):
        """Should return the oscillation pattern with highest severity."""
        events = [
            create_tool_call_event("t1", "search"),
            create_tool_call_event("t2", "lookup"),
            create_tool_call_event("t3", "search"),
            create_tool_call_event("t4", "lookup"),
            create_tool_call_event("t5", "search"),
            create_tool_call_event("t6", "lookup"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.repeat_count >= 2
        # Higher repeat count should increase severity
        assert result.severity > 0

    def test_ignores_non_relevant_event_types(self):
        """Should only consider TOOL_CALL, DECISION, and AGENT_TURN events."""
        from agent_debugger_sdk.core.events import ErrorEvent

        events = [
            create_tool_call_event("t1", "search"),
            ErrorEvent(
                id="e1",
                session_id="test",
                message="error",
                timestamp=datetime.now(timezone.utc),
            ),
            create_tool_call_event("t2", "lookup"),
            create_tool_call_event("t3", "search"),
            create_tool_call_event("t4", "lookup"),
        ]

        result = detect_oscillation(events)

        # Should still detect oscillation ignoring the error event
        assert result is not None
        assert len(result.event_ids) == 4

    def test_returns_none_for_empty_sequence(self):
        """Should return None for empty event list."""
        result = detect_oscillation([])

        assert result is None

    def test_returns_none_for_single_event(self):
        """Should return None for single event."""
        events = [create_tool_call_event("t1", "search")]

        result = detect_oscillation(events)

        assert result is None

    def test_handles_window_larger_than_sequence(self):
        """Should handle case where window is larger than event sequence."""
        events = [
            create_tool_call_event("t1", "search"),
            create_tool_call_event("t2", "lookup"),
            create_tool_call_event("t3", "search"),
            create_tool_call_event("t4", "lookup"),
        ]

        result = detect_oscillation(events, window=100)

        assert result is not None

    def test_calculates_severity_based_on_repeat_count(self):
        """Severity should increase with repeat count."""
        # 2 repeats
        events_2 = [
            create_tool_call_event("t1", "a"),
            create_tool_call_event("t2", "b"),
            create_tool_call_event("t3", "a"),
            create_tool_call_event("t4", "b"),
        ]

        # 3 repeats
        events_3 = [
            create_tool_call_event("t1", "a"),
            create_tool_call_event("t2", "b"),
            create_tool_call_event("t3", "a"),
            create_tool_call_event("t4", "b"),
            create_tool_call_event("t5", "a"),
            create_tool_call_event("t6", "b"),
        ]

        result_2 = detect_oscillation(events_2)
        result_3 = detect_oscillation(events_3)

        assert result_2 is not None
        assert result_3 is not None
        assert result_3.severity >= result_2.severity

    def test_captures_correct_event_ids(self):
        """Should capture IDs of all events in the oscillating pattern."""
        events = [
            create_tool_call_event("t1", "search"),
            create_tool_call_event("t2", "lookup"),
            create_tool_call_event("t3", "search"),
            create_tool_call_event("t4", "lookup"),
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert len(result.event_ids) == 4
        # Verify the captured event IDs match the original events
        captured_ids = set(result.event_ids)
        original_ids = {e.id for e in events}
        assert captured_ids == original_ids
