"""Event utility methods for trace analysis."""

from __future__ import annotations

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .helpers import event_value


def event_headline(event: TraceEvent) -> str:
    """Return a compact human-readable label for an event.

    Args:
        event: The event to generate a headline for

    Returns:
        A compact human-readable label
    """
    match event.event_type:
        case EventType.DECISION:
            return event_value(event, "chosen_action", event.name or "decision")
        case EventType.TOOL_CALL | EventType.TOOL_RESULT:
            return event_value(event, "tool_name", event.name or "tool")
        case EventType.REFUSAL:
            return event_value(event, "reason", event.name or "refusal")
        case EventType.SAFETY_CHECK:
            policy_name = event_value(event, "policy_name", "safety")
            outcome = event_value(event, "outcome", "pass")
            return f"{policy_name} -> {outcome}"
        case EventType.POLICY_VIOLATION:
            return event_value(event, "violation_type", event.name or "policy violation")
        case EventType.BEHAVIOR_ALERT:
            return event_value(event, "alert_type", event.name or "behavior alert")
        case EventType.ERROR:
            return event_value(event, "error_type", event.name or "error")
        case EventType.AGENT_TURN:
            return event_value(
                event, "speaker", event_value(event, "agent_id", event.name or "turn")
            )
        case _:
            return event.name or str(event.event_type)


def fingerprint(event: TraceEvent) -> str:
    """Return a coarse fingerprint used for recurrence clustering.

    Args:
        event: The event to fingerprint

    Returns:
        A fingerprint string for clustering similar events
    """
    match event.event_type:
        case EventType.ERROR:
            return (
                f"error:{event_value(event, 'error_type', 'unknown')}:"
                f"{event_value(event, 'error_message', '')}"
            )
        case EventType.TOOL_RESULT:
            return f"tool:{event_value(event, 'tool_name', 'unknown')}:{bool(event_value(event, 'error'))}"
        case EventType.REFUSAL:
            return (
                f"refusal:{event_value(event, 'policy_name', 'unknown')}:"
                f"{event_value(event, 'risk_level', 'medium')}"
            )
        case EventType.POLICY_VIOLATION:
            return (
                f"policy:{event_value(event, 'policy_name', 'unknown')}:"
                f"{event_value(event, 'violation_type', 'unknown')}"
            )
        case EventType.BEHAVIOR_ALERT:
            return f"alert:{event_value(event, 'alert_type', 'unknown')}"
        case EventType.SAFETY_CHECK:
            return (
                f"safety:{event_value(event, 'policy_name', 'unknown')}:"
                f"{event_value(event, 'outcome', 'pass')}"
            )
        case EventType.DECISION:
            return f"decision:{event_value(event, 'chosen_action', 'unknown')}"
        case _:
            return f"{event.event_type}:{event.name}"


def retention_tier(
    *,
    replay_value: float,
    high_severity_count: int,
    failure_cluster_count: int,
    behavior_alert_count: int,
) -> str:
    """Assign a coarse retention tier for a session or checkpoint.

    Args:
        replay_value: The computed replay value (0-1)
        high_severity_count: Number of high-severity events
        failure_cluster_count: Number of failure clusters
        behavior_alert_count: Number of behavior alerts

    Returns:
        "full", "summarized", or "downsampled"
    """
    if replay_value >= 0.72 or high_severity_count > 0 or failure_cluster_count >= 2:
        return "full"
    if replay_value >= 0.42 or behavior_alert_count > 0 or failure_cluster_count > 0:
        return "summarized"
    return "downsampled"
