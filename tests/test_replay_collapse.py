"""Tests for replay segment collapsing."""

from __future__ import annotations

from unittest.mock import MagicMock

from collector.replay_collapse import CollapsedSegment, identify_low_value_segments


class TestIdentifyLowValueSegments:
    """Tests for identify_low_value_segments function."""

    def test_empty_events_returns_empty(self) -> None:
        """Empty event list should return empty segments."""
        assert identify_low_value_segments([]) == []

    def test_no_low_value_segments_when_all_high_importance(self) -> None:
        """When all events have high importance, no segments should be collapsed."""
        events = [MagicMock(importance=0.8, event_type="tool", duration_ms=100) for _ in range(5)]
        assert identify_low_value_segments(events) == []

    def test_finds_contiguous_low_value_run_with_context_window(self) -> None:
        """Context window protects events around high-value events."""
        events = [
            MagicMock(importance=0.2, event_type="tool", duration_ms=10),
            MagicMock(importance=0.2, event_type="tool", duration_ms=10),
            MagicMock(importance=0.2, event_type="tool", duration_ms=10),
            MagicMock(importance=0.9, event_type="decision", duration_ms=50),
        ]
        # With default context_window=1, the high-value event at index 3
        # protects indices 2, 3 (and 4 if it existed)
        # So indices 0-1 are unprotected, but min_segment_length=3 means no segment
        segments = identify_low_value_segments(events, min_segment_length=2)
        # The context window of 1 around index 3 protects indices 2, 3
        # So only indices 0, 1 are unprotected - but that's length 2 which meets min_segment_length
        assert len(segments) == 1
        assert segments[0].start_index == 0
        assert segments[0].end_index == 1

    def test_finds_single_segment(self) -> None:
        """A single contiguous low-value run should be identified."""
        events = [
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
        ]
        segments = identify_low_value_segments(events, threshold=0.35, min_segment_length=3)
        assert len(segments) == 1
        assert segments[0].start_index == 0
        assert segments[0].end_index == 4
        assert segments[0].event_count == 5

    def test_respects_min_segment_length(self) -> None:
        """Runs shorter than min_segment_length should not be collapsed."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.9, event_type="decision"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        # With context_window=0, indices 0, 1, 3 are low-value
        # But the longest contiguous run is only 2 (indices 0-1), less than min_segment_length=3
        assert segments == []

    def test_multiple_segments(self) -> None:
        """Multiple low-value runs separated by high-value events."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.9, event_type="decision"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        # With context_window=0, we should get two segments
        assert len(segments) == 2
        assert segments[0].start_index == 0
        assert segments[0].end_index == 2
        assert segments[1].start_index == 4
        assert segments[1].end_index == 6

    def test_context_window_expands_protection(self) -> None:
        """Context window should protect events around high-value ones."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.9, event_type="decision"),  # index 2
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        # With context_window=1, indices 1, 2, 3 are protected
        # Only indices 0 and 4 are unprotected but they're not contiguous
        segments = identify_low_value_segments(events, context_window=1, min_segment_length=2)
        assert segments == []

    def test_context_window_zero(self) -> None:
        """With context_window=0, only the high-value event itself is protected."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.9, event_type="decision"),  # index 2
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        # With context_window=0, only index 2 is protected
        # So we have segments 0-1 and 3-4, both of length 2
        segments = identify_low_value_segments(events, context_window=0, min_segment_length=2)
        assert len(segments) == 2

    def test_threshold_parameter(self) -> None:
        """Higher threshold means more events considered low-value."""
        events = [
            MagicMock(importance=0.5, event_type="tool"),
            MagicMock(importance=0.5, event_type="tool"),
            MagicMock(importance=0.5, event_type="tool"),
        ]
        # With default threshold 0.35, 0.5 >= 0.35, so no segments
        segments_default = identify_low_value_segments(events, threshold=0.35, context_window=0)
        assert segments_default == []

        # With threshold 0.6, 0.5 < 0.6, so all events are low-value
        segments_high = identify_low_value_segments(events, threshold=0.6, min_segment_length=3, context_window=0)
        assert len(segments_high) == 1

    def test_event_types_collected(self) -> None:
        """Segment should collect unique event types."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="decision"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        assert len(segments) == 1
        # Event types should be unique
        assert set(segments[0].event_types) == {"tool", "decision"}

    def test_duration_summed(self) -> None:
        """Segment should sum durations of events with valid durations."""
        events = [
            MagicMock(importance=0.1, event_type="tool", duration_ms=10),
            MagicMock(importance=0.1, event_type="tool", duration_ms=20),
            MagicMock(importance=0.1, event_type="tool", duration_ms=30),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        assert len(segments) == 1
        assert segments[0].total_duration_ms == 60

    def test_duration_none_when_no_valid_durations(self) -> None:
        """Duration should be None when no events have valid durations."""
        events = [
            MagicMock(importance=0.1, event_type="tool", duration_ms=None),
            MagicMock(importance=0.1, event_type="tool", duration_ms=None),
            MagicMock(importance=0.1, event_type="tool", duration_ms=None),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        assert len(segments) == 1
        assert segments[0].total_duration_ms is None

    def test_summary_format(self) -> None:
        """Summary should include event count and types."""
        events = [
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
            MagicMock(importance=0.1, event_type="tool"),
        ]
        segments = identify_low_value_segments(events, min_segment_length=3, context_window=0)
        assert len(segments) == 1
        assert "3" in segments[0].summary
        assert "tool" in segments[0].summary


class TestCollapsedSegment:
    """Tests for CollapsedSegment dataclass."""

    def test_to_dict(self) -> None:
        """to_dict should return all fields."""
        segment = CollapsedSegment(
            start_index=0,
            end_index=5,
            event_count=6,
            summary="6 tool events",
            event_types=["tool"],
            total_duration_ms=100.0,
        )
        result = segment.to_dict()
        assert result["start_index"] == 0
        assert result["end_index"] == 5
        assert result["event_count"] == 6
        assert result["summary"] == "6 tool events"
        assert result["event_types"] == ["tool"]
        assert result["total_duration_ms"] == 100.0

    def test_to_dict_with_none_duration(self) -> None:
        """to_dict should handle None duration."""
        segment = CollapsedSegment(
            start_index=0,
            end_index=2,
            event_count=3,
            summary="3 events",
            event_types=["tool"],
            total_duration_ms=None,
        )
        result = segment.to_dict()
        assert result["total_duration_ms"] is None
