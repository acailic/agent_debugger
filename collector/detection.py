"""Detection algorithms for agent behavior analysis."""

from __future__ import annotations

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .causal_analysis import _event_value
from .models import OscillationAlert


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

    # Extract sequence of (event_type, key) tuples for relevant event types
    sequence: list[tuple[str, str]] = []
    event_map: list[TraceEvent] = []

    for e in recent:
        # Only consider tool calls, decisions, and state changes for oscillation
        if e.event_type not in {EventType.TOOL_CALL, EventType.DECISION, EventType.AGENT_TURN}:
            continue

        key = e.name or str(e.event_type)
        if e.event_type == EventType.TOOL_CALL:
            tool_name = _event_value(e, "tool_name", "")
            if tool_name:
                key = tool_name
        elif e.event_type == EventType.DECISION:
            chosen_action = _event_value(e, "chosen_action", "")
            if chosen_action:
                key = chosen_action

        sequence.append((str(e.event_type), key))
        event_map.append(e)

    if len(sequence) < 4:
        return None

    # Check for oscillation patterns of different lengths
    best_alert: OscillationAlert | None = None

    for pattern_len in [2, 3, 4]:
        if len(sequence) < pattern_len * 2:
            continue

        pattern = sequence[:pattern_len]
        repeats = 1
        matched_indices: list[int] = list(range(pattern_len))

        for i in range(pattern_len, len(sequence) - pattern_len + 1, pattern_len):
            if sequence[i : i + pattern_len] == pattern:
                repeats += 1
                matched_indices.extend(range(i, i + pattern_len))

        if repeats >= 2:
            pattern_str = "->".join(p[1] for p in pattern)
            severity = min(1.0, repeats / 3.0 + (0.1 if repeats >= 3 else 0.0))
            matched_events = [event_map[i] for i in matched_indices if i < len(event_map)]

            if best_alert is None or severity > best_alert.severity:
                best_alert = OscillationAlert(
                    pattern=pattern_str,
                    event_type=pattern[0][0],
                    repeat_count=repeats,
                    severity=severity,
                    event_ids=[e.id for e in matched_events],
                )

    return best_alert
