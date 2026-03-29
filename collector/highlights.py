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


def _categorize_error_event(event: TraceEvent) -> tuple[str | None, str | None]:
    """Categorize ERROR events."""
    return "error", "Error event"


def _categorize_refusal_event(event: TraceEvent) -> tuple[str | None, str | None]:
    """Categorize REFUSAL and POLICY_VIOLATION events."""
    if event.event_type == EventType.POLICY_VIOLATION:
        return "refusal", "Policy violation"
    return "refusal", "Refusal triggered"


def _categorize_behavior_alert(event: TraceEvent) -> tuple[str | None, str | None]:
    """Categorize BEHAVIOR_ALERT events."""
    return "anomaly", str(event.data.get("signal", "Behavior anomaly"))


def _categorize_safety_check(event: TraceEvent) -> tuple[str | None, str | None]:
    """Categorize SAFETY_CHECK events."""
    outcome = event.data.get("outcome", "pass")
    if outcome != "pass":
        return "anomaly", f"Safety check {outcome}"
    return None, None


def _categorize_decision_event(event: TraceEvent, composite: float) -> tuple[str | None, str | None]:
    """Categorize DECISION events."""
    confidence = event.data.get("confidence", 0.5)
    if confidence < 0.5:
        return "decision", f"Low confidence decision ({confidence:.2f})"
    if composite > 0.6:
        return "decision", "High-impact decision"
    return None, None


def _categorize_tool_result(event: TraceEvent, severity: float) -> tuple[str | None, str | None]:
    """Categorize TOOL_RESULT events."""
    if event.data.get("error"):
        return "error", "Tool execution failed"
    if severity > 0.7:
        return "anomaly", "Unusual tool result"
    return None, None


def _get_event_categorization(
    event: TraceEvent,
    composite: float,
    severity: float,
) -> tuple[str | None, str | None]:
    """Determine highlight type and reason for an event.

    Returns:
        Tuple of (highlight_type, reason) or (None, None) if not highlight-worthy
    """
    categorizer = {
        EventType.ERROR: lambda e: _categorize_error_event(e),
        EventType.REFUSAL: lambda e: _categorize_refusal_event(e),
        EventType.POLICY_VIOLATION: lambda e: _categorize_refusal_event(e),
        EventType.BEHAVIOR_ALERT: lambda e: _categorize_behavior_alert(e),
        EventType.SAFETY_CHECK: lambda e: _categorize_safety_check(e),
        EventType.DECISION: lambda e: _categorize_decision_event(e, composite),
        EventType.TOOL_RESULT: lambda e: _categorize_tool_result(e, severity),
    }

    handler = categorizer.get(event.event_type)
    if handler:
        return handler(event)
    return None, None


def _calculate_importance(severity: float, composite: float) -> float:
    """Calculate importance score from severity and composite rankings."""
    return min(severity, composite) if composite > 0 else severity


def _build_highlight_dict(
    event: TraceEvent,
    highlight_type: str,
    reason: str,
    importance: float,
    event_headline_fn: Any,
) -> dict[str, Any]:
    """Build a highlight dictionary from event data."""
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

        highlight_type, reason = _get_event_categorization(event, composite, severity)

        if highlight_type and (severity > 0.5 or composite > 0.5):
            importance = _calculate_importance(severity, composite)
            highlight = _build_highlight_dict(event, highlight_type, reason, importance, event_headline_fn)
            highlights.append(highlight)

    highlights.sort(key=lambda h: -h["importance"])
    return highlights[:20]
