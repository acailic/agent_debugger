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

    # Build ranking lookup
    ranking_by_id = {r["event_id"]: r for r in rankings}

    for event in events:
        ranking = ranking_by_id.get(event.id, {})
        composite = ranking.get("composite", 0)
        severity = ranking.get("severity", 0)

        highlight_type: str | None = None
        reason: str | None = None

        # Determine highlight type and reason
        if event.event_type == EventType.ERROR:
            highlight_type = "error"
            reason = "Error event"
        elif event.event_type == EventType.REFUSAL:
            highlight_type = "refusal"
            reason = "Refusal triggered"
        elif event.event_type == EventType.POLICY_VIOLATION:
            highlight_type = "refusal"
            reason = "Policy violation"
        elif event.event_type == EventType.BEHAVIOR_ALERT:
            highlight_type = "anomaly"
            reason = str(event.data.get("signal", "Behavior anomaly"))
        elif event.event_type == EventType.SAFETY_CHECK:
            outcome = event.data.get("outcome", "pass")
            if outcome != "pass":
                highlight_type = "anomaly"
                reason = f"Safety check {outcome}"
        elif event.event_type == EventType.DECISION:
            confidence = event.data.get("confidence", 0.5)
            if confidence < 0.5:
                highlight_type = "decision"
                reason = f"Low confidence decision ({confidence:.2f})"
            elif composite > 0.6:
                highlight_type = "decision"
                reason = "High-impact decision"
        elif event.event_type == EventType.TOOL_RESULT:
            if event.data.get("error"):
                highlight_type = "error"
                reason = "Tool execution failed"
            elif severity > 0.7:
                highlight_type = "anomaly"
                reason = "Unusual tool result"

        # Only add if we have a highlight type and sufficient importance
        if highlight_type and (severity > 0.5 or composite > 0.5):
            importance = min(severity, composite) if composite > 0 else severity
            timestamp = event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp)
            highlights.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "highlight_type": highlight_type,
                    "importance": round(importance, 4),
                    "reason": reason,
                    "timestamp": timestamp,
                    "headline": event_headline_fn(event),
                }
            )

    # Sort by importance, limit to top 20
    highlights.sort(key=lambda h: -h["importance"])
    return highlights[:20]
