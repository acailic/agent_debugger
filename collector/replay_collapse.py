"""Segment collapsing utilities for selective replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import TraceEvent


@dataclass
class CollapsedSegment:
    """Represents a collapsed segment of low-importance events."""

    start_index: int
    end_index: int
    event_count: int
    summary: str
    event_types: list[str] = field(default_factory=list)
    total_duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "start_index": self.start_index,
            "end_index": self.end_index,
            "event_count": self.event_count,
            "summary": self.summary,
            "event_types": self.event_types,
            "total_duration_ms": self.total_duration_ms,
        }


def _get_high_value_indices(events: list["TraceEvent"], threshold: float) -> set[int]:
    """Identify indices of events with importance >= threshold."""
    return {i for i, event in enumerate(events) if (event.importance or 0) >= threshold}


def _protect_context_around_high_value(
    high_value_indices: set[int], num_events: int, context_window: int
) -> set[int]:
    """Expand protected indices to include context window around high-value events."""
    protected: set[int] = set(high_value_indices)
    for idx in high_value_indices:
        for offset in range(-context_window, context_window + 1):
            new_idx = idx + offset
            if 0 <= new_idx < num_events:
                protected.add(new_idx)
    return protected


def _find_contiguous_low_value_runs(
    num_events: int, protected: set[int], min_segment_length: int
) -> list[tuple[int, int]]:
    """Find contiguous runs of unprotected indices that meet minimum length."""
    segments: list[tuple[int, int]] = []
    run_start: int | None = None

    for i in range(num_events):
        if i not in protected:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                run_length = i - run_start
                if run_length >= min_segment_length:
                    segments.append((run_start, i - 1))
                run_start = None

    # Handle trailing run
    if run_start is not None:
        run_length = num_events - run_start
        if run_length >= min_segment_length:
            segments.append((run_start, num_events - 1))

    return segments


def _build_segment_from_events(
    events: list["TraceEvent"], start: int, end: int
) -> CollapsedSegment:
    """Build a CollapsedSegment from a slice of events."""
    segment_events = events[start : end + 1]
    event_types = list({str(e.event_type) for e in segment_events})

    # Build summary
    types_str = ", ".join(sorted(event_types)[:2])
    summary = f"{len(segment_events)} {types_str} events"

    # Calculate total duration if available
    total_duration_ms: float | None = None
    durations = [getattr(e, "duration_ms", None) for e in segment_events]
    valid_durations = [d for d in durations if d is not None]
    if valid_durations:
        total_duration_ms = sum(valid_durations)

    return CollapsedSegment(
        start_index=start,
        end_index=end,
        event_count=len(segment_events),
        summary=summary,
        event_types=event_types,
        total_duration_ms=total_duration_ms,
    )


def identify_low_value_segments(
    events: list["TraceEvent"],
    threshold: float = 0.35,
    min_segment_length: int = 3,
    context_window: int = 1,
) -> list[CollapsedSegment]:
    """Identify contiguous sequences of low-importance events.

    Args:
        events: List of trace events to analyze.
        threshold: Importance threshold below which events are considered low-value.
        min_segment_length: Minimum number of events to form a collapsible segment.
        context_window: Number of events to preserve around high-value events.

    Returns:
        List of CollapsedSegment objects representing collapsible regions.
    """
    if not events:
        return []

    high_value_indices = _get_high_value_indices(events, threshold)
    protected = _protect_context_around_high_value(
        high_value_indices, len(events), context_window
    )
    segments = _find_contiguous_low_value_runs(len(events), protected, min_segment_length)

    return [_build_segment_from_events(events, start, end) for start, end in segments]
