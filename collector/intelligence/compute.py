"""Computation helpers for trace analysis."""

from __future__ import annotations

from collections import Counter
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .helpers import event_value
from .event_utils import retention_tier


def compute_event_ranking(
    event: TraceEvent,
    fingerprint: str,
    counts: Counter,
    total_events: int,
    checkpoint_event_ids: set[str],
    severity_fn: callable,
) -> dict[str, Any]:
    """Compute ranking metrics for a single event.

    Args:
        event: The event to rank
        fingerprint: The event's fingerprint string
        counts: Counter of all fingerprint occurrences
        total_events: Total number of events
        checkpoint_event_ids: Set of checkpoint event IDs
        severity_fn: Function to compute event severity

    Returns:
        Dictionary with ranking metrics
    """
    severity = severity_fn(event)
    recurrence_count = counts[fingerprint]
    recurrence = min((recurrence_count - 1) / max(total_events, 1), 1.0)
    novelty = 1.0 / recurrence_count

    # Calculate replay value components
    replay_value = severity * 0.55
    replay_value += 0.15 if event.id in checkpoint_event_ids else 0.0
    replay_value += (
        0.1
        if event.event_type in {EventType.DECISION, EventType.REFUSAL, EventType.POLICY_VIOLATION}
        else 0.0
    )
    replay_value += (
        0.1
        if bool(event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])))
        else 0.0
    )
    replay_value += 0.1 if bool(event_value(event, "evidence_event_ids", [])) else 0.0

    composite = min(1.0, severity * 0.45 + novelty * 0.2 + recurrence * 0.15 + replay_value * 0.2)

    return {
        "event_id": event.id,
        "event_type": str(event.event_type),
        "fingerprint": fingerprint,
        "severity": round(severity, 4),
        "novelty": round(novelty, 4),
        "recurrence": round(recurrence, 4),
        "replay_value": round(min(replay_value, 1.0), 4),
        "composite": round(composite, 4),
    }


def detect_tool_loop(
    event: TraceEvent,
    consecutive_tool_loop: int,
    previous_tool_name: str | None,
) -> tuple[int, str | None, list[dict[str, Any]]]:
    """Detect tool loops and return updated state with any new alerts.

    Args:
        event: The event to check
        consecutive_tool_loop: Current loop counter
        previous_tool_name: Previous tool name in sequence

    Returns:
        Tuple of (new_counter, new_tool_name, new_alerts)
    """
    new_alerts: list[dict[str, Any]] = []

    if event.event_type != EventType.TOOL_CALL:
        return 0, None, new_alerts

    tool_name = event_value(event, "tool_name", "")
    if not tool_name:
        return 0, None, new_alerts

    # Update loop counter
    if tool_name == previous_tool_name:
        consecutive_tool_loop += 1
    else:
        consecutive_tool_loop = 1

    # Generate alert if loop detected
    if consecutive_tool_loop >= 3:
        new_alerts.append(
            {
                "alert_type": "tool_loop",
                "severity": "high",
                "signal": f"Repeated tool loop for {tool_name}",
                "event_id": event.id,
            }
        )

    return consecutive_tool_loop, tool_name, new_alerts


def compute_checkpoint_rankings(
    checkpoints: list[Checkpoint],
    ranking_by_event_id: dict[str, dict[str, Any]],
    representative_failure_ids: list[str],
) -> tuple[list[dict[str, Any]], list[float]]:
    """Compute checkpoint rankings and return rankings list with values.

    Args:
        checkpoints: List of checkpoints
        ranking_by_event_id: Event ID to ranking mapping
        representative_failure_ids: IDs of representative failure events

    Returns:
        Tuple of (checkpoint_rankings, checkpoint_values)
    """
    checkpoint_rankings: list[dict[str, Any]] = []
    checkpoint_values: list[float] = []

    max_sequence = max((checkpoint.sequence for checkpoint in checkpoints), default=0)

    for checkpoint in checkpoints:
        event_ranking = ranking_by_event_id.get(checkpoint.event_id)
        event_replay = float(event_ranking["replay_value"]) if event_ranking else 0.0
        event_composite = float(event_ranking["composite"]) if event_ranking else 0.0
        sequence_weight = checkpoint.sequence / max(max_sequence, 1)
        restore_value = min(
            1.0,
            event_replay * 0.45
            + event_composite * 0.2
            + checkpoint.importance * 0.2
            + sequence_weight * 0.15,
        )
        checkpoint_values.append(restore_value)

        high_severity_indicator = 1 if event_ranking and event_ranking["severity"] >= 0.92 else 0
        failure_cluster_indicator = 1 if checkpoint.event_id in representative_failure_ids else 0

        checkpoint_rankings.append(
            {
                "checkpoint_id": checkpoint.id,
                "event_id": checkpoint.event_id,
                "sequence": checkpoint.sequence,
                "importance": round(checkpoint.importance, 4),
                "replay_value": round(event_replay, 4),
                "restore_value": round(restore_value, 4),
                "retention_tier": retention_tier(
                    replay_value=restore_value,
                    high_severity_count=high_severity_indicator,
                    failure_cluster_count=failure_cluster_indicator,
                    behavior_alert_count=0,
                ),
            }
        )

    checkpoint_rankings.sort(
        key=lambda item: (-item["restore_value"], -item["importance"], -item["sequence"])
    )
    return checkpoint_rankings, checkpoint_values
