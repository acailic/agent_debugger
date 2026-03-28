"""Detection algorithms for agent behavior analysis."""

from __future__ import annotations

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .causal_analysis import _event_value
from .models import OscillationAlert


def _extract_event_key(event: TraceEvent) -> str:
    """Extract the key value from an event for oscillation detection."""
    key = event.name or str(event.event_type)

    if event.event_type == EventType.TOOL_CALL:
        tool_name = _event_value(event, "tool_name", "")
        if tool_name:
            key = tool_name
    elif event.event_type == EventType.DECISION:
        chosen_action = _event_value(event, "chosen_action", "")
        if chosen_action:
            key = chosen_action

    return key


def _build_oscillation_sequence(events: list[TraceEvent]) -> tuple[list[tuple[str, str]], list[TraceEvent]]:
    """Build sequence of (event_type, key) tuples from relevant events."""
    sequence: list[tuple[str, str]] = []
    event_map: list[TraceEvent] = []

    for event in events:
        if event.event_type not in {EventType.TOOL_CALL, EventType.DECISION, EventType.AGENT_TURN}:
            continue

        key = _extract_event_key(event)
        sequence.append((str(event.event_type), key))
        event_map.append(event)

    return sequence, event_map


def _detect_pattern_repeats(sequence: list[tuple[str, str]], pattern_len: int) -> tuple[int, list[int]] | None:
    """Detect if a pattern of given length repeats in the sequence.

    Returns:
        Tuple of (repeat_count, matched_indices) if pattern found, None otherwise
    """
    if len(sequence) < pattern_len * 2:
        return None

    pattern = sequence[:pattern_len]
    repeats = 1
    matched_indices: list[int] = list(range(pattern_len))

    for i in range(pattern_len, len(sequence) - pattern_len + 1, pattern_len):
        if sequence[i : i + pattern_len] == pattern:
            repeats += 1
            matched_indices.extend(range(i, i + pattern_len))

    if repeats >= 2:
        return repeats, matched_indices

    return None


def _create_oscillation_alert(
    pattern: list[tuple[str, str]],
    repeats: int,
    matched_indices: list[int],
    event_map: list[TraceEvent],
) -> OscillationAlert:
    """Create an OscillationAlert from detected pattern."""
    pattern_str = "->".join(p[1] for p in pattern)
    severity = min(1.0, repeats / 3.0 + (0.1 if repeats >= 3 else 0.0))
    matched_events = [event_map[i] for i in matched_indices if i < len(event_map)]

    return OscillationAlert(
        pattern=pattern_str,
        event_type=pattern[0][0],
        repeat_count=repeats,
        severity=severity,
        event_ids=[e.id for e in matched_events],
    )


def detect_oscillation(
    events: list[TraceEvent],
    window: int = 10,
) -> OscillationAlert | None:
    """Detect A->B->A->B patterns in tool calls or decisions.

    Algorithm:
    1. Extract sequence of (event_type, key_field) tuples
    2. For each subsequence length 2-4:
       - Check if sequence repeats at least twice
       - Compute oscillation score: repeat_count / window_size
    3. Return highest-scoring oscillation with severity
    """
    if len(events) < 4:
        return None

    recent = events[-window:] if len(events) > window else events
    sequence, event_map = _build_oscillation_sequence(recent)

    if len(sequence) < 4:
        return None

    # Check for oscillation patterns of different lengths
    best_alert: OscillationAlert | None = None

    for pattern_len in [2, 3, 4]:
        result = _detect_pattern_repeats(sequence, pattern_len)
        if result is None:
            continue

        repeats, matched_indices = result
        pattern = sequence[:pattern_len]
        alert = _create_oscillation_alert(pattern, repeats, matched_indices, event_map)

        if best_alert is None or alert.severity > best_alert.severity:
            best_alert = alert

    return best_alert
