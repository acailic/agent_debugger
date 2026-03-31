"""Computation helpers for trace analysis."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .event_utils import retention_tier
from .helpers import event_value

# Time-decay constants (in days)
RECENT_SESSION_DAYS = 7
STALE_SESSION_DAYS = 30
RECENT_BOOST = 0.2
STALE_PENALTY = 0.3


def compute_session_replay_value(
    session: dict[str, Any],
    events: list[TraceEvent],
    rankings: list[dict[str, Any]],
) -> float:
    """Compute composite replay value for a session with time-decay factors.

    Args:
        session: Session dict with started_at, ended_at fields
        events: List of events in the session
        rankings: Event ranking dicts with replay_value scores

    Returns:
        Composite replay score between 0.0 and 1.0
    """
    now = datetime.now(timezone.utc)
    started_at = session.get("started_at")
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    elif isinstance(started_at, datetime):
        pass  # already a datetime
    elif started_at is None:
        started_at = now
    else:
        started_at = now

    # Ensure timezone-aware for arithmetic with UTC now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    # Calculate session age in days
    session_age = (now - started_at).total_seconds() / 86400

    # Base importance: mean of event replay values
    event_replay_values = [r.get("replay_value", 0.0) for r in rankings]
    base_importance = sum(event_replay_values) / max(len(event_replay_values), 1)

    # Time-decay factors
    time_decay = 0.0
    if session_age <= RECENT_SESSION_DAYS:
        # Recent sessions get a boost
        time_decay = RECENT_BOOST
    elif session_age >= STALE_SESSION_DAYS:
        # Stale sessions get a penalty
        time_decay = -STALE_PENALTY

    # Failure recency: more weight if failures occurred recently
    failure_event_types = {EventType.ERROR, EventType.REFUSAL, EventType.POLICY_VIOLATION}
    failure_events = [e for e in events if e.event_type in failure_event_types]
    failure_recency_boost = 0.0
    if failure_events:
        # Get the most recent failure timestamp
        def _ensure_aware(ts: datetime) -> datetime:
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        def _parse_ts(e):
            if isinstance(e.timestamp, datetime):
                return _ensure_aware(e.timestamp)
            return datetime.fromisoformat(e.timestamp.replace("Z", "+00:00"))

        most_recent_failure_ts = max(
            (_parse_ts(e) for e in failure_events if e.timestamp),
            default=started_at
        )
        days_since_failure = (now - most_recent_failure_ts).total_seconds() / 86400
        if days_since_failure <= RECENT_SESSION_DAYS:
            failure_recency_boost = 0.15

    # Failure pattern uniqueness: rare failure types get higher value
    failure_rankings = [r for r in rankings if r.get("event_type") in {"error", "refusal", "policy_violation"}]
    uniqueness_boost = 0.0
    if failure_rankings:
        avg_novelty = sum(r.get("novelty", 0.0) for r in failure_rankings) / max(len(failure_rankings), 1)
        uniqueness_boost = avg_novelty * 0.1

    # Composite score
    composite = min(1.0, max(0.0, base_importance + time_decay + failure_recency_boost + uniqueness_boost))
    return round(composite, 4)


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
    session_replay_value: float = 0.0,
) -> tuple[list[dict[str, Any]], list[float]]:
    """Compute checkpoint rankings and return rankings list with values.

    Args:
        checkpoints: List of checkpoints
        ranking_by_event_id: Event ID to ranking mapping
        representative_failure_ids: IDs of representative failure events
        session_replay_value: Composite session replay value with time-decay

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

        # Incorporate session-level time-decay replay value
        restore_value = min(
            1.0,
            event_replay * 0.40  # Reduced from 0.45 to make room for session replay
            + event_composite * 0.20
            + checkpoint.importance * 0.20
            + sequence_weight * 0.10  # Reduced from 0.15
            + session_replay_value * 0.10,  # New: session-level time-decay factor
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
