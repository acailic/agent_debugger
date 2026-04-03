"""Memory exporters for trace insights.

This module provides an abstraction layer for exporting Peaky Peek trace insights
(failure patterns, entity data, session summaries) to external memory systems.

The key components are:
- TraceInsight: Data model for trace insights
- MemoryExporter: Protocol/interface for memory exporters
- FileExporter: Reference implementation using JSON/file storage
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

# Import FileExporter after all classes are defined to avoid circular import


@dataclass
class FailurePattern:
    """Represents a recurring failure pattern."""

    fingerprint: str
    count: int
    first_seen_at: str
    last_seen_at: str
    sample_error_types: list[str]
    representative_event_id: str
    severity: float


@dataclass
class EntitySummary:
    """Summary statistics for entities extracted from traces."""

    entity_type: str
    total_unique: int
    top_entities: list[dict[str, Any]]  # Top 5 by frequency


@dataclass
class SessionDigest:
    """Condensed summary of a session for memory storage."""

    session_id: str
    agent_name: str
    framework: str
    started_at: str
    ended_at: str | None
    status: str
    total_tokens: int
    total_cost_usd: float
    tool_calls: int
    llm_calls: int
    errors: int
    replay_value: float
    retention_tier: str
    failure_count: int
    behavior_alert_count: int
    highlights_count: int
    tags: list[str]
    fix_note: str | None


@dataclass
class TraceInsight:
    """Comprehensive insight package from trace analysis.

    This is the standard export format for trace insights that can be
    sent to external memory systems.
    """

    session_digest: SessionDigest
    failure_patterns: list[FailurePattern]
    entity_summaries: list[EntitySummary]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for serialization."""
        return {
            "session_digest": self.session_digest.__dict__,
            "failure_patterns": [fp.__dict__ for fp in self.failure_patterns],
            "entity_summaries": [es.__dict__ for es in self.entity_summaries],
            "generated_at": self.generated_at,
            "metadata": self.metadata,
        }


class MemoryExporter(Protocol):
    """Protocol for memory exporters.

    Memory exporters are responsible for taking trace insights and
    persisting them to external memory systems. Implementations can
    target vector databases, key-value stores, file systems, etc.
    """

    async def export(self, insight: TraceInsight) -> None:
        """Export a trace insight to the memory system.

        Args:
            insight: The trace insight to export

        Raises:
            ExportError: If the export operation fails
        """
        ...

    async def query_similar(
        self,
        session_digest: SessionDigest,
        limit: int = 10,
    ) -> list[SessionDigest]:
        """Query for similar sessions based on the session digest.

        Args:
            session_digest: The session digest to find similar sessions for
            limit: Maximum number of similar sessions to return

        Returns:
            List of similar session digests
        """
        ...

    async def get_failure_patterns(
        self,
        agent_name: str | None = None,
        limit: int = 20,
    ) -> list[FailurePattern]:
        """Get top failure patterns, optionally filtered by agent.

        Args:
            agent_name: Optional agent name to filter by
            limit: Maximum number of patterns to return

        Returns:
            List of failure patterns sorted by frequency
        """
        ...

    async def health_check(self) -> dict[str, Any]:
        """Check the health of the exporter connection.

        Returns:
            Dict with status and any relevant health metrics
        """
        ...


class ExportError(Exception):
    """Exception raised when an export operation fails."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause
        self.message = message


__all__ = [
    "FailurePattern",
    "EntitySummary",
    "SessionDigest",
    "TraceInsight",
    "MemoryExporter",
    "ExportError",
    "FileExporter",
]

# Import FileExporter at the end to avoid circular dependency
from .file import FileExporter  # noqa: E402
