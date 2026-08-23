"""Utility functions for trace analysis."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import TraceEvent


def event_value(event: TraceEvent | None, key: str, default: Any = None) -> Any:
    """Extract a value from an event, checking both attributes and data dict.

    Args:
        event: The event to extract from (can be None)
        key: The key to look for
        default: Default value if key not found

    Returns:
        The value or default
    """
    if event is None:
        return default
    if hasattr(event, key):
        return getattr(event, key)
    return event.data.get(key, default)


def mean(values: list[float]) -> float:
    """Calculate the mean of a list of values.

    Args:
        values: List of float values

    Returns:
        The mean, or 0.0 if list is empty
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def event_label(event: TraceEvent) -> str:
    """Short human-facing label for an event (tool name, action, or goal)."""
    label = (
        event_value(event, "tool_name", None)
        or event_value(event, "chosen_action", None)
        or event_value(event, "goal", None)
        or event.name
        or str(event.event_type).replace("_", " ")
    )
    return str(label)[:96]
