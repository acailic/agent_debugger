"""Tests for rolling window pattern detection and loop detection enhancements."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.detection import detect_multi_step_loops
from collector.models import RollingWindow
from collector.rolling import RollingWindowCalculator


@pytest.fixture
def sample_events() -> list[TraceEvent]:
    """Create sample trace events for testing."""
    now = datetime.now(timezone.utc)
    events: list[TraceEvent] = []

    # Create some tool call events
    for i in range(5):
        events.append(
            TraceEvent(
                id=f"tool-{i}",
                timestamp=now,
                event_type=EventType.TOOL_CALL,
                name="tool_call",
                data={"tool_name": "search", "result": f"result-{i}"},
            )
        )

    # Create some error events
    for i in range(3):
        events.append(
            TraceEvent(
                id=f"error-{i}",
                timestamp=now,
                event_type=EventType.ERROR,
                name="error",
                data={"error_message": f"error-{i}"},
            )
        )

    # Create some LLM calls with cost
    for i in range(4):
        events.append(
            TraceEvent(
                id=f"llm-{i}",
                timestamp=now,
                event_type=EventType.LLM_REQUEST,
                name="llm_request",
                data={
                    "cost_usd": 0.001 if i < 2 else 0.005,  # Cost acceleration in second half
                    "usage": {"total_tokens": 100},
                },
            )
        )

    return events


class TestRollingPatternDetection:
    """Tests for RollingWindowCalculator.detect_patterns method."""

    def test_detect_repeated_tool_calls(self, sample_events):
        """Test detection of repeated tool call patterns."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)

        patterns = calculator.detect_patterns(window, sample_events)

        # Should detect repeated "search" tool calls (5 times)
        repeated_tool_patterns = [p for p in patterns if p.name == "repeated_tool_calls"]
        assert len(repeated_tool_patterns) == 1
        assert repeated_tool_patterns[0].severity > 0
        assert "search" in repeated_tool_patterns[0].description
        assert "5 times" in repeated_tool_patterns[0].description

    def test_detect_error_spike(self, sample_events):
        """Test detection of error rate spikes."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)

        # 3 errors out of 12 events = 25%, not quite 30%
        # Add more errors to trigger the spike
        for i in range(3, 6):
            sample_events.append(
                TraceEvent(
                    id=f"error-extra-{i}",
                    timestamp=datetime.now(timezone.utc),
                    event_type=EventType.ERROR,
                    name="error",
                    data={"error_message": f"error-{i}"},
                )
            )

        window = calculator.compute_rolling_window(sample_events, window_seconds=60)
        patterns = calculator.detect_patterns(window, sample_events)

        # Should detect error spike (6 errors out of 15 events = 40%)
        error_patterns = [p for p in patterns if p.name == "error_spike"]
        assert len(error_patterns) == 1
        assert error_patterns[0].severity > 0.3

    def test_detect_cost_acceleration(self, sample_events):
        """Test detection of cost acceleration patterns."""
        calculator = RollingWindowCalculator()

        # Create explicit test data with cost acceleration
        now = datetime.now(timezone.utc)
        test_events = []

        # First half: low cost events
        for i in range(3):
            test_events.append(
                TraceEvent(
                    id=f"llm-low-{i}",
                    timestamp=now,
                    event_type=EventType.LLM_REQUEST,
                    name="llm_request",
                    data={
                        "cost_usd": 0.001,
                        "usage": {"total_tokens": 100},
                    },
                )
            )

        # Second half: high cost events (5x acceleration)
        for i in range(3):
            test_events.append(
                TraceEvent(
                    id=f"llm-high-{i}",
                    timestamp=now,
                    event_type=EventType.LLM_REQUEST,
                    name="llm_request",
                    data={
                        "cost_usd": 0.005,
                        "usage": {"total_tokens": 500},
                    },
                )
            )

        window = calculator.compute_rolling_window(test_events, window_seconds=60)
        patterns = calculator.detect_patterns(window, test_events)

        # Should detect cost acceleration (second half has 0.015 vs first half 0.003)
        cost_patterns = [p for p in patterns if p.name == "cost_acceleration"]
        assert len(cost_patterns) == 1
        assert cost_patterns[0].severity > 0
        assert "accelerated" in cost_patterns[0].description.lower()

    def test_no_patterns_empty_window(self):
        """Test that empty window returns no patterns."""
        calculator = RollingWindowCalculator()
        window = RollingWindow(
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            event_count=0,
        )

        patterns = calculator.detect_patterns(window, [])

        assert len(patterns) == 0

    def test_no_patterns_single_event(self):
        """Test that single event returns no significant patterns."""
        calculator = RollingWindowCalculator()
        event = TraceEvent(
            id="single",
            timestamp=datetime.now(timezone.utc),
            event_type=EventType.TOOL_CALL,
            name="tool_call",
            data={"tool_name": "single_tool"},
        )

        window = calculator.compute_rolling_window([event], window_seconds=60)
        patterns = calculator.detect_patterns(window, [event])

        # Should not trigger any pattern (need 3+ for repeated tools, 30% for errors)
        assert len(patterns) == 0

    def test_no_patterns_no_repetition(self):
        """Test that diverse tools without repetition don't trigger patterns."""
        calculator = RollingWindowCalculator()
        events = []
        now = datetime.now(timezone.utc)

        # Create 5 different tools, each called once
        for i, tool_name in enumerate(["search", "read", "write", "delete", "update"]):
            events.append(
                TraceEvent(
                    id=f"tool-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": tool_name},
                )
            )

        window = calculator.compute_rolling_window(events, window_seconds=60)
        patterns = calculator.detect_patterns(window, events)

        # Should not detect repeated tool patterns (none repeated 3+ times)
        repeated_tool_patterns = [p for p in patterns if p.name == "repeated_tool_calls"]
        assert len(repeated_tool_patterns) == 0


class TestSummaryGeneration:
    """Tests for RollingWindowCalculator.generate_summary method."""

    def test_summary_includes_patterns(self, sample_events):
        """Test that summary includes detected patterns."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)
        patterns = calculator.detect_patterns(window, sample_events)

        summary = calculator.generate_summary(window, patterns)

        # Should include pattern descriptions
        assert "Patterns:" in summary
        assert "search" in summary or "accelerated" in summary

    def test_summary_without_patterns(self, sample_events):
        """Test that summary works without patterns."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)

        summary = calculator.generate_summary(window, patterns=None)

        # Should return base summary text
        assert summary is not None
        assert len(summary) > 0

    def test_summary_empty_patterns(self):
        """Test that summary handles empty pattern list."""
        calculator = RollingWindowCalculator()
        window = RollingWindow(
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            event_count=5,
        )

        summary = calculator.generate_summary(window, patterns=[])

        # Should return base summary without pattern section
        assert summary is not None


class TestToDict:
    """Tests for RollingWindowCalculator.to_dict method."""

    def test_to_dict_includes_patterns(self, sample_events):
        """Test that to_dict includes detected patterns."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)
        patterns = calculator.detect_patterns(window, sample_events)

        result = calculator.to_dict(window, patterns)

        assert "patterns" in result
        assert isinstance(result["patterns"], list)
        assert len(result["patterns"]) > 0
        assert "name" in result["patterns"][0]
        assert "severity" in result["patterns"][0]
        assert "description" in result["patterns"][0]

    def test_to_dict_without_patterns(self, sample_events):
        """Test that to_dict works without patterns."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)

        result = calculator.to_dict(window, patterns=None)

        # Should not include patterns key
        assert "patterns" not in result

    def test_to_dict_serializable(self, sample_events):
        """Test that to_dict returns JSON-serializable data."""
        calculator = RollingWindowCalculator()
        window = calculator.compute_rolling_window(sample_events, window_seconds=60)
        patterns = calculator.detect_patterns(window, sample_events)

        result = calculator.to_dict(window, patterns)

        # Convert to JSON to verify serializability
        import json

        json_str = json.dumps(result)
        assert len(json_str) > 0

        # Verify key fields
        assert "window_start" in result
        assert "window_end" in result
        assert "event_count" in result
        assert "unique_tools" in result
        assert isinstance(result["unique_tools"], list)


class TestMultiStepLoopDetection:
    """Tests for detect_multi_step_loops function."""

    def test_detect_2_step_loop(self):
        """Test detection of A->B->A->B pattern."""
        now = datetime.now(timezone.utc)
        events = []

        # Create A->B->A->B pattern
        for i in range(2):
            events.append(
                TraceEvent(
                    id=f"tool-a-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_a"},
                )
            )
            events.append(
                TraceEvent(
                    id=f"tool-b-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_b"},
                )
            )

        loops = detect_multi_step_loops(events, min_repetitions=2)

        assert len(loops) > 0
        assert loops[0].repeat_count >= 2
        assert len(loops[0].pattern) == 2
        assert loops[0].severity > 0

    def test_detect_3_step_loop(self):
        """Test detection of A->B->C->A->B->C pattern."""
        now = datetime.now(timezone.utc)
        events = []

        # Create A->B->C->A->B->C pattern
        for i in range(2):
            for tool_name in ["tool_a", "tool_b", "tool_c"]:
                events.append(
                    TraceEvent(
                        id=f"{tool_name}-{i}",
                        timestamp=now,
                        event_type=EventType.TOOL_CALL,
                        name="tool_call",
                        data={"tool_name": tool_name},
                    )
                )

        loops = detect_multi_step_loops(events, min_repetitions=2)

        assert len(loops) > 0
        # Should find the 3-step pattern
        three_step_loops = [loop for loop in loops if len(loop.pattern) == 3]
        assert len(three_step_loops) > 0
        assert three_step_loops[0].repeat_count >= 2

    def test_detect_4_step_loop(self):
        """Test detection of A->B->C->D->A->B->C->D pattern."""
        now = datetime.now(timezone.utc)
        events = []

        # Create A->B->C->D->A->B->C->D pattern
        for i in range(2):
            for tool_name in ["tool_a", "tool_b", "tool_c", "tool_d"]:
                events.append(
                    TraceEvent(
                        id=f"{tool_name}-{i}",
                        timestamp=now,
                        event_type=EventType.TOOL_CALL,
                        name="tool_call",
                        data={"tool_name": tool_name},
                    )
                )

        loops = detect_multi_step_loops(events, min_repetitions=2, max_pattern_length=4)

        assert len(loops) > 0
        # Should find the 4-step pattern
        four_step_loops = [loop for loop in loops if len(loop.pattern) == 4]
        assert len(four_step_loops) > 0

    def test_no_loop_insufficient_repetitions(self):
        """Test that insufficient repetitions don't trigger loop detection."""
        now = datetime.now(timezone.utc)
        events = []

        # Create A->B pattern only once (no repetition)
        events.append(
            TraceEvent(
                id="tool-a-0",
                timestamp=now,
                event_type=EventType.TOOL_CALL,
                name="tool_call",
                data={"tool_name": "tool_a"},
            )
        )
        events.append(
            TraceEvent(
                id="tool-b-0",
                timestamp=now,
                event_type=EventType.TOOL_CALL,
                name="tool_call",
                data={"tool_name": "tool_b"},
            )
        )

        loops = detect_multi_step_loops(events, min_repetitions=2)

        # Should not detect any loops with min_repetitions=2
        assert len(loops) == 0

    def test_no_loop_empty_events(self):
        """Test that empty events list returns no loops."""
        loops = detect_multi_step_loops([], min_repetitions=2)
        assert len(loops) == 0

    def test_no_loop_single_event(self):
        """Test that single event returns no loops."""
        now = datetime.now(timezone.utc)
        event = TraceEvent(
            id="single",
            timestamp=now,
            event_type=EventType.TOOL_CALL,
            name="tool_call",
            data={"tool_name": "single_tool"},
        )

        loops = detect_multi_step_loops([event], min_repetitions=2)
        assert len(loops) == 0

    def test_loop_severity_calculation(self):
        """Test that loop severity increases with more repetitions."""
        now = datetime.now(timezone.utc)
        events_low_reps = []
        events_high_reps = []

        # Create pattern with 2 repetitions
        for i in range(2):
            events_low_reps.append(
                TraceEvent(
                    id=f"tool-a-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_a"},
                )
            )
            events_low_reps.append(
                TraceEvent(
                    id=f"tool-b-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_b"},
                )
            )

        # Create pattern with 4 repetitions
        for i in range(4):
            events_high_reps.append(
                TraceEvent(
                    id=f"tool-a-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_a"},
                )
            )
            events_high_reps.append(
                TraceEvent(
                    id=f"tool-b-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_b"},
                )
            )

        loops_low = detect_multi_step_loops(events_low_reps, min_repetitions=2)
        loops_high = detect_multi_step_loops(events_high_reps, min_repetitions=2)

        # Higher repetitions should result in higher severity
        if loops_low and loops_high:
            assert loops_high[0].severity >= loops_low[0].severity

    def test_loops_sorted_by_severity(self):
        """Test that detected loops are sorted by severity descending."""
        now = datetime.now(timezone.utc)
        events = []

        # Add a 2-step pattern with 3 repetitions (higher severity)
        for i in range(3):
            events.append(
                TraceEvent(
                    id=f"tool-x-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_x"},
                )
            )
            events.append(
                TraceEvent(
                    id=f"tool-y-{i}",
                    timestamp=now,
                    event_type=EventType.TOOL_CALL,
                    name="tool_call",
                    data={"tool_name": "tool_y"},
                )
            )

        # Add a 3-step pattern with 2 repetitions (lower severity)
        for i in range(2):
            for tool_name in ["tool_a", "tool_b", "tool_c"]:
                events.append(
                    TraceEvent(
                        id=f"{tool_name}-{i}",
                        timestamp=now,
                        event_type=EventType.TOOL_CALL,
                        name="tool_call",
                        data={"tool_name": tool_name},
                    )
                )

        loops = detect_multi_step_loops(events, min_repetitions=2)

        # Check that loops are sorted by severity descending
        if len(loops) > 1:
            for i in range(len(loops) - 1):
                assert loops[i].severity >= loops[i + 1].severity
