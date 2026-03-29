"""Tests for collector/detection.py oscillation detection module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    DecisionEvent,
    EventType,
    ToolCallEvent,
    TraceEvent,
)
from collector.detection import (
    _build_oscillation_sequence,
    _create_oscillation_alert,
    _detect_pattern_repeats,
    _extract_event_key,
    detect_oscillation,
)


@pytest.fixture
def sample_tool_call():
    """Create a sample tool call event."""
    return ToolCallEvent(
        id="tool-1",
        session_id="session-1",
        name="Tool Call",
        tool_name="search",
        arguments={"query": "test"},
    )


@pytest.fixture
def sample_decision():
    """Create a sample decision event."""
    return DecisionEvent(
        id="decision-1",
        session_id="session-1",
        name="Decision",
        reasoning="Test reasoning",
        confidence=0.8,
        chosen_action="action_a",
        data={"chosen_action": "action_a"},
    )


@pytest.fixture
def sample_agent_turn():
    """Create a sample agent turn event."""
    return AgentTurnEvent(
        id="turn-1",
        session_id="session-1",
        name="Agent Turn",
        agent_id="agent-1",
        goal="Test goal",
        content="Test content",
    )


class TestExtractEventKey:
    """Test event key extraction for oscillation detection."""

    def test_extract_key_from_tool_call_with_tool_name(self, sample_tool_call):
        """Test extracting tool_name from TOOL_CALL event."""
        key = _extract_event_key(sample_tool_call)
        assert key == "search"

    def test_extract_key_from_tool_call_without_tool_name(self):
        """Test extracting default key from TOOL_CALL without tool_name."""
        tool_call = ToolCallEvent(
            id="tool-1",
            session_id="session-1",
            name="Tool Call",
            tool_name=None,
            arguments={},
            data={},
        )
        key = _extract_event_key(tool_call)
        assert key == "Tool Call"

    def test_extract_key_from_decision_with_chosen_action(self, sample_decision):
        """Test extracting chosen_action from DECISION event."""
        key = _extract_event_key(sample_decision)
        assert key == "action_a"

    def test_extract_key_from_decision_without_chosen_action(self):
        """Test extracting default key from DECISION without chosen_action."""
        decision = DecisionEvent(
            id="decision-1",
            session_id="session-1",
            name="Decision",
            reasoning="Test",
        )
        key = _extract_event_key(decision)
        assert key == "Decision"

    def test_extract_key_from_agent_turn(self, sample_agent_turn):
        """Test extracting name from AGENT_TURN event."""
        key = _extract_event_key(sample_agent_turn)
        assert key == "Agent Turn"

    def test_extract_key_from_generic_event(self):
        """Test extracting event type as fallback for unknown events."""
        event = TraceEvent(
            id="event-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="Error Event",
            data={},
        )
        key = _extract_event_key(event)
        assert key == "Error Event"


class TestBuildOscillationSequence:
    """Test oscillation sequence building."""

    def test_build_sequence_with_tool_calls(self, sample_tool_call):
        """Test building sequence from tool calls."""
        tool_call2 = ToolCallEvent(
            id="tool-2",
            session_id="session-1",
            name="Tool Call",
            tool_name="read",
            arguments={},
        )
        sequence, event_map = _build_oscillation_sequence([sample_tool_call, tool_call2])

        assert len(sequence) == 2
        assert len(event_map) == 2
        assert sequence[0] == ("tool_call", "search")
        assert sequence[1] == ("tool_call", "read")

    def test_build_sequence_with_decisions(self, sample_decision):
        """Test building sequence from decisions."""
        decision2 = DecisionEvent(
            id="decision-2",
            session_id="session-1",
            name="Decision",
            reasoning="Test",
            chosen_action="action_b",
            data={"chosen_action": "action_b"},
        )
        sequence, event_map = _build_oscillation_sequence([sample_decision, decision2])

        assert len(sequence) == 2
        assert sequence[0] == ("decision", "action_a")
        assert sequence[1] == ("decision", "action_b")

    def test_build_sequence_with_agent_turns(self, sample_agent_turn):
        """Test building sequence from agent turns."""
        sequence, event_map = _build_oscillation_sequence([sample_agent_turn])

        assert len(sequence) == 1
        assert sequence[0] == ("agent_turn", "Agent Turn")

    def test_build_sequence_filters_irrelevant_events(self):
        """Test that non-tool/decision/turn events are filtered out."""
        error = TraceEvent(
            id="error-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="Error",
            data={},
        )
        sequence, event_map = _build_oscillation_sequence([error])

        assert len(sequence) == 0
        assert len(event_map) == 0

    def test_build_sequence_empty_events(self):
        """Test building sequence from empty event list."""
        sequence, event_map = _build_oscillation_sequence([])
        assert sequence == []
        assert event_map == []

    def test_build_sequence_mixed_events(self, sample_tool_call, sample_decision):
        """Test building sequence from mixed event types."""
        error = TraceEvent(
            id="error-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="Error",
            data={},
        )
        sequence, event_map = _build_oscillation_sequence(
            [error, sample_tool_call, sample_decision]
        )

        # Should only include tool_call and decision, not error
        assert len(sequence) == 2
        assert len(event_map) == 2


class TestDetectPatternRepeats:
    """Test pattern repeat detection."""

    def test_detect_repeats_with_two_length_pattern(self):
        """Test detecting A->B->A->B pattern (length 2)."""
        sequence = [("A", "x"), ("B", "y"), ("A", "x"), ("B", "y")]
        result = _detect_pattern_repeats(sequence, 2)

        assert result is not None
        repeats, matched_indices = result
        assert repeats == 2
        assert matched_indices == [0, 1, 2, 3]

    def test_detect_repeats_with_three_length_pattern(self):
        """Test detecting A->B->C->A->B->C pattern (length 3)."""
        sequence = [
            ("A", "x"),
            ("B", "y"),
            ("C", "z"),
            ("A", "x"),
            ("B", "y"),
            ("C", "z"),
        ]
        result = _detect_pattern_repeats(sequence, 3)

        assert result is not None
        repeats, matched_indices = result
        assert repeats == 2

    def test_detect_repeats_with_four_length_pattern(self):
        """Test detecting 4-length pattern repeating."""
        sequence = [
            ("A", "w"),
            ("B", "x"),
            ("C", "y"),
            ("D", "z"),
            ("A", "w"),
            ("B", "x"),
            ("C", "y"),
            ("D", "z"),
        ]
        result = _detect_pattern_repeats(sequence, 4)

        assert result is not None
        repeats, matched_indices = result
        assert repeats == 2

    def test_no_repeats_for_short_sequence(self):
        """Test that short sequences don't trigger repeat detection."""
        sequence = [("A", "x"), ("B", "y")]
        result = _detect_pattern_repeats(sequence, 2)

        assert result is None

    def test_no_repeats_for_non_repeating_pattern(self):
        """Test that non-repeating patterns return None."""
        sequence = [("A", "x"), ("B", "y"), ("C", "z"), ("D", "w")]
        result = _detect_pattern_repeats(sequence, 2)

        assert result is None

    def test_no_repeats_for_incomplete_pattern(self):
        """Test that incomplete second pattern doesn't count as repeat."""
        sequence = [("A", "x"), ("B", "y"), ("A", "x"), ("C", "z")]
        result = _detect_pattern_repeats(sequence, 2)

        assert result is None

    def test_detects_three_repeats(self):
        """Test detecting pattern that repeats 3 times."""
        sequence = [
            ("A", "x"),
            ("B", "y"),
            ("A", "x"),
            ("B", "y"),
            ("A", "x"),
            ("B", "y"),
        ]
        result = _detect_pattern_repeats(sequence, 2)

        assert result is not None
        repeats, matched_indices = result
        assert repeats == 3


class TestCreateOscillationAlert:
    """Test oscillation alert creation."""

    def test_create_alert_basic(self):
        """Test creating basic oscillation alert."""
        pattern = [("A", "x"), ("B", "y")]
        event_map = [
            ToolCallEvent(
                id="tool-1",
                session_id="session-1",
                name="x",
                tool_name="x",
                arguments={},
            ),
            ToolCallEvent(
                id="tool-2",
                session_id="session-1",
                name="y",
                tool_name="y",
                arguments={},
            ),
        ]

        alert = _create_oscillation_alert(pattern, 2, [0, 1, 2, 3], event_map)

        assert alert.pattern == "x->y"
        assert alert.event_type == "A"
        assert alert.repeat_count == 2
        assert alert.severity > 0
        assert len(alert.event_ids) == 2

    def test_alert_severity_increases_with_repeats(self):
        """Test that severity increases with more repeats."""
        pattern = [("A", "x"), ("B", "y")]
        event_map = [
            ToolCallEvent(
                id="tool-1",
                session_id="session-1",
                name="x",
                tool_name="x",
                arguments={},
            ),
        ]

        alert_2_repeats = _create_oscillation_alert(pattern, 2, [0, 1], event_map)
        alert_3_repeats = _create_oscillation_alert(pattern, 3, [0, 1, 2], event_map)

        assert alert_3_repeats.severity > alert_2_repeats.severity

    def test_alert_severity_capped_at_one(self):
        """Test that severity is capped at 1.0."""
        pattern = [("A", "x"), ("B", "y")]
        event_map = [
            ToolCallEvent(
                id="tool-1",
                session_id="session-1",
                name="x",
                tool_name="x",
                arguments={},
            ),
        ]

        alert = _create_oscillation_alert(pattern, 10, [0, 1], event_map)

        assert alert.severity <= 1.0


class TestDetectOscillation:
    """Test main oscillation detection function."""

    def test_detect_oscillation_empty_events(self):
        """Test with empty event list."""
        result = detect_oscillation([])
        assert result is None

    def test_detect_oscillation_fewer_than_4_events(self, sample_tool_call):
        """Test with fewer than 4 events returns None."""
        result = detect_oscillation([sample_tool_call])
        assert result is None

    def test_detects_simple_oscillation(self):
        """Test detecting A->B->A->B oscillation."""
        events = [
            ToolCallEvent(
                id=f"tool-{i}",
                session_id="session-1",
                name="search",
                tool_name="search" if i % 2 == 0 else "read",
                arguments={},
            )
            for i in range(4)
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert result.repeat_count >= 2
        assert "search" in result.pattern or "read" in result.pattern

    def test_detect_oscillation_with_decisions(self):
        """Test detecting oscillation in decision actions."""
        events = [
            DecisionEvent(
                id=f"decision-{i}",
                session_id="session-1",
                name="Decision",
                reasoning="Test",
                chosen_action="action_a" if i % 2 == 0 else "action_b",
                data={"chosen_action": "action_a" if i % 2 == 0 else "action_b"},
            )
            for i in range(4)
        ]

        result = detect_oscillation(events)

        assert result is not None
        assert "action_a" in result.pattern and "action_b" in result.pattern

    def test_no_oscillation_for_unique_sequence(self):
        """Test that unique sequences don't trigger oscillation detection."""
        events = [
            ToolCallEvent(
                id=f"tool-{i}",
                session_id="session-1",
                name=f"tool_{i}",
                tool_name=f"tool_{i}",
                arguments={},
            )
            for i in range(5)
        ]

        result = detect_oscillation(events)

        assert result is None

    def test_oscillation_window_limit(self):
        """Test that window parameter limits event processing."""
        # Create 15 events with oscillation in first 10
        events = [
            ToolCallEvent(
                id=f"tool-{i}",
                session_id="session-1",
                name="search" if i % 2 == 0 else "read",
                tool_name="search" if i % 2 == 0 else "read",
                arguments={},
            )
            for i in range(15)
        ]

        result = detect_oscillation(events, window=10)

        # Should detect oscillation within the window
        assert result is not None

    def test_oscillation_defaults_to_full_sequence(self):
        """Test that default window processes all events when len <= window."""
        events = [
            ToolCallEvent(
                id=f"tool-{i}",
                session_id="session-1",
                name="search" if i % 2 == 0 else "read",
                tool_name="search" if i % 2 == 0 else "read",
                arguments={},
            )
            for i in range(8)
        ]

        result = detect_oscillation(events, window=10)

        assert result is not None

    def test_no_oscillation_with_filtered_events(self):
        """Test that events without tool/decision/turn don't contribute to oscillation."""
        events = [
            TraceEvent(
                id=f"error-{i}",
                session_id="session-1",
                event_type=EventType.ERROR,
                timestamp=datetime.now(timezone.utc),
                name=f"Error {i}",
                data={},
            )
            for i in range(5)
        ]

        result = detect_oscillation(events)

        assert result is None

    def test_oscillation_with_mixed_event_types(self):
        """Test oscillation detection with mix of relevant and irrelevant events."""
        events = []
        for i in range(6):
            # Add tool calls that oscillate
            events.append(
                ToolCallEvent(
                    id=f"tool-{i}",
                    session_id="session-1",
                    name="search" if i % 2 == 0 else "read",
                    tool_name="search" if i % 2 == 0 else "read",
                    arguments={},
                )
            )
            # Add errors (should be filtered)
            events.append(
                TraceEvent(
                    id=f"error-{i}",
                    session_id="session-1",
                    event_type=EventType.ERROR,
                    timestamp=datetime.now(timezone.utc),
                    name="Error",
                    data={},
                )
            )

        result = detect_oscillation(events)

        # Should detect oscillation in tool calls despite errors
        assert result is not None
        assert result.repeat_count >= 2
