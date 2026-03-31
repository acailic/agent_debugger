"""Checkpoint ranking service for computing restore value."""

from __future__ import annotations

from typing import Any, Callable

from agent_debugger_sdk.core.events import Checkpoint


class CheckpointRankingService:
    """Compute checkpoint rankings for restore value."""

    def rank_checkpoints(
        self,
        checkpoints: list[Checkpoint],
        event_rankings: list[dict[str, Any]],
        retention_tier_fn: Callable[..., str],
        representative_failure_ids: list[str],
        session_replay_value: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Compute restore values for checkpoints.

        Args:
            checkpoints: List of checkpoints to rank.
            event_rankings: List of event ranking dicts (from EventRankingService).
            retention_tier_fn: Function to compute retention tier.
            representative_failure_ids: List of event IDs representing failures.
            session_replay_value: Composite session replay value with time-decay factors.

        Returns:
            List of dicts with:
            - checkpoint_id, event_id, sequence, importance
            - replay_value, restore_value, retention_tier
        """
        if not checkpoints:
            return []

        ranking_by_event_id = {ranking["event_id"]: ranking for ranking in event_rankings}
        checkpoint_rankings: list[dict[str, Any]] = []

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
            checkpoint_rankings.append(
                {
                    "checkpoint_id": checkpoint.id,
                    "event_id": checkpoint.event_id,
                    "sequence": checkpoint.sequence,
                    "importance": round(checkpoint.importance, 4),
                    "replay_value": round(event_replay, 4),
                    "restore_value": round(restore_value, 4),
                    "retention_tier": retention_tier_fn(
                        replay_value=restore_value,
                        high_severity_count=1 if event_ranking and event_ranking["severity"] >= 0.92 else 0,
                        failure_cluster_count=1 if checkpoint.event_id in representative_failure_ids else 0,
                        behavior_alert_count=0,
                    ),
                }
            )

        checkpoint_rankings.sort(key=lambda item: (-item["restore_value"], -item["importance"], -item["sequence"]))
        return checkpoint_rankings
