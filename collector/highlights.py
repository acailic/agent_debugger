"""Highlight generation for session analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent


@dataclass
class Highlight:
    """Represents a highlight-worthy moment in a session trace."""

    event_id: str
    event_type: str
    highlight_type: str  # "decision", "error", "refusal", "anomaly", "state_change"
    importance: float
    reason: str  # Human-readable reason why this is highlighted
    timestamp: str


def _categorize_event(event: TraceEvent, composite: float, severity: float) -> tuple[str | None, str | None]:
    """Determine highlight type and reason for an event.

    Args:
        event: The trace event to categorize
        composite: Composite ranking score
        severity: Severity ranking score

    Returns:
        Tuple of (highlight_type, reason) or (None, None) if not highlight-worthy
    """
    if event.event_type == EventType.ERROR:
        return "error", "Error event"
    if event.event_type == EventType.REFUSAL:
        return "refusal", "Refusal triggered"
    if event.event_type == EventType.POLICY_VIOLATION:
        return "refusal", "Policy violation"
    if event.event_type == EventType.BEHAVIOR_ALERT:
        return "anomaly", str(event.data.get("signal", "Behavior anomaly"))
    if event.event_type == EventType.SAFETY_CHECK:
        outcome = event.data.get("outcome", "pass")
        if outcome != "pass":
            return "anomaly", f"Safety check {outcome}"
    if event.event_type == EventType.DECISION:
        confidence = event.data.get("confidence", 0.5)
        if confidence < 0.5:
            return "decision", f"Low confidence decision ({confidence:.2f})"
        if composite > 0.6:
            return "decision", "High-impact decision"
    if event.event_type == EventType.TOOL_RESULT:
        if event.data.get("error"):
            return "error", "Tool execution failed"
        if severity > 0.7:
            return "anomaly", "Unusual tool result"
    return None, None


def _create_highlight_dict(
    event: TraceEvent,
    highlight_type: str,
    reason: str,
    importance: float,
    event_headline_fn: Any,
) -> dict[str, Any]:
    """Create a highlight dictionary from an event.

    Args:
        event: The trace event
        highlight_type: Type of highlight
        reason: Human-readable reason
        importance: Importance score
        event_headline_fn: Function to generate headline

    Returns:
        Highlight dictionary
    """
    timestamp = event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp)
    return {
        "event_id": event.id,
        "event_type": str(event.event_type),
        "highlight_type": highlight_type,
        "importance": round(importance, 4),
        "reason": reason,
        "timestamp": timestamp,
        "headline": event_headline_fn(event),
    }


def generate_highlights(
    events: list[TraceEvent],
    rankings: list[dict[str, Any]],
    event_headline_fn: Any,
) -> list[dict[str, Any]]:
    """Generate a curated list of highlight-worthy moments.

    Args:
        events: List of trace events
        rankings: List of event rankings with severity, composite
        event_headline_fn: Function to generate headline for an event

    Returns:
        List of highlight dicts sorted by importance, limited to 20
    """
    highlights: list[dict[str, Any]] = []
    ranking_by_id = {r["event_id"]: r for r in rankings}

    for event in events:
        ranking = ranking_by_id.get(event.id, {})
        composite = ranking.get("composite", 0)
        severity = ranking.get("severity", 0)

        highlight_type, reason = _categorize_event(event, composite, severity)

        if highlight_type and (severity > 0.5 or composite > 0.5):
            importance = min(severity, composite) if composite > 0 else severity
            highlight = _create_highlight_dict(event, highlight_type, reason, importance, event_headline_fn)
            highlights.append(highlight)

    highlights.sort(key=lambda h: -h["importance"])
    return highlights[:20]
