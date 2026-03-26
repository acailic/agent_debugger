"""Retention policy enforcement for session data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage import TraceRepository


@dataclass
class RetentionConfig:
    """Configuration for retention policy enforcement.

    Attributes:
        full_tier_days: Days to retain full-fidelity data.
        summarized_tier_days: Days to retain summarized data.
        downsampled_tier_days: Days to retain metadata only.
        verbose_fields: Fields to strip during summarization.
        checkpoint_importance_threshold: Minimum importance for checkpoints.
    """

    full_tier_days: int = 365
    summarized_tier_days: int = 90
    downsampled_tier_days: int = 30
    verbose_fields: list[str] = field(
        default_factory=lambda: [
            "data",
            "messages",
            "result",
            "stack_trace",
            "content",
            "reasoning",
            "evidence",
        ]
    )
    checkpoint_importance_threshold: float = 0.8


@dataclass
class RetentionResult:
    """Result of applying retention policy.

    Attributes:
        sessions_processed: Total number of sessions processed.
        events_deleted: Total events deleted.
        checkpoints_deleted: Total checkpoints deleted.
        events_summarized: Total events summarized.
    """

    sessions_processed: int = 0
    events_deleted: int = 0
    checkpoints_deleted: int = 0
    events_summarized: int = 0


class RetentionEnforcer:
    """Enforce retention policies based on session tier.

    Tier rules:
        - full: Keep all events with full data, keep all checkpoints
        - summarized: Keep events but strip verbose fields,
                      keep only high-importance checkpoints
        - downsampled: Delete all events and checkpoints
    """

    def __init__(self, repository: TraceRepository):
        """Initialize the retention enforcer.

        Args:
            repository: TraceRepository for database operations.
        """
        self.repository = repository

    async def apply_retention_policy(
        self,
        config: RetentionConfig | None = None,
    ) -> RetentionResult:
        """Apply retention policy based on tier.

        Args:
            config: Retention configuration. Uses defaults if not provided.

        Returns:
            RetentionResult with counts of affected records.
        """
        if config is None:
            config = RetentionConfig()

        now = datetime.now(timezone.utc)
        result = RetentionResult()

        # Process each tier in order (summarized before downsampled)
        tier_configs = [
            ("summarized", config.summarized_tier_days),
            ("downsampled", config.downsampled_tier_days),
        ]

        for tier, days in tier_configs:
            cutoff = now - timedelta(days=days)
            sessions = await self.repository.list_sessions_by_retention_tier(tier, older_than=cutoff)

            for session in sessions:
                if tier == "summarized":
                    # Strip verbose data from events
                    events_summarized = await self.repository.summarize_session_events(
                        session.id,
                        verbose_fields=config.verbose_fields,
                    )
                    result.events_summarized += events_summarized

                    # Delete low-importance checkpoints
                    checkpoints_deleted = await self.repository.delete_checkpoints_below_threshold(
                        session.id,
                        min_importance=config.checkpoint_importance_threshold,
                    )
                    result.checkpoints_deleted += checkpoints_deleted

                elif tier == "downsampled":
                    # Delete all events and checkpoints
                    events_deleted = await self.repository.delete_events_for_session(session.id)
                    result.events_deleted += events_deleted

                    checkpoints_deleted = await self.repository.delete_checkpoints_for_session(session.id)
                    result.checkpoints_deleted += checkpoints_deleted

                result.sessions_processed += 1

        # Commit changes
        await self.repository.commit()

        return result

    async def get_retention_stats(self) -> dict[str, int]:
        """Get statistics about sessions by retention tier.

        Returns:
            Dict with counts of sessions per tier.
        """
        now = datetime.now(timezone.utc)
        stats = {}

        for tier in ["full", "summarized", "downsampled"]:
            # Count all sessions in this tier
            sessions = await self.repository.list_sessions_by_retention_tier(
                tier,
                older_than=now,  # Use far future to get all
            )
            stats[f"{tier}_count"] = len(sessions)

        return stats
