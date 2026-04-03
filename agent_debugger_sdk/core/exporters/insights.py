"""Insight builder for creating TraceInsight from session data.

This module provides the InsightBuilder class which orchestrates the
creation of TraceInsight objects from session events, analysis results,
and entity extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from agent_debugger_sdk.core.exporters import (
    EntitySummary,
    FailurePattern,
    SessionDigest,
    TraceInsight,
)
from storage.entities import EntityType


class InsightBuilder:
    """Build TraceInsight objects from session data.

    This class orchestrates the conversion of session events, analysis results,
    and entity data into the standardized TraceInsight format suitable for
    export to external memory systems.
    """

    def __init__(self):
        """Initialize the insight builder."""
        pass

    def build_insight(
        self,
        session: Session,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint],
        analysis: dict[str, Any],
        entity_data: dict[str, Any] | None = None,
    ) -> TraceInsight:
        """Build a TraceInsight from session data and analysis.

        Args:
            session: The session object
            events: List of trace events
            checkpoints: List of checkpoints
            analysis: Analysis results from TraceIntelligence
            entity_data: Optional entity extraction data

        Returns:
            TraceInsight object ready for export
        """
        session_digest = self._build_session_digest(session, analysis)
        failure_patterns = self._build_failure_patterns(analysis)
        entity_summaries = self._build_entity_summaries(entity_data)

        return TraceInsight(
            session_digest=session_digest,
            failure_patterns=failure_patterns,
            entity_summaries=entity_summaries,
            metadata={
                "event_count": len(events),
                "checkpoint_count": len(checkpoints),
                "analysis_timestamp": analysis.get("live_summary", {}).get("timestamp"),
            },
        )

    def _build_session_digest(self, session: Session, analysis: dict[str, Any]) -> SessionDigest:
        """Build a SessionDigest from a session and analysis."""
        session_summary = analysis.get("session_summary", {})

        return SessionDigest(
            session_id=session.id,
            agent_name=session.agent_name or "",
            framework=session.framework or "",
            started_at=session.started_at.isoformat() if session.started_at else "",
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            status=str(session.status),
            total_tokens=session.total_tokens,
            total_cost_usd=session.total_cost_usd,
            tool_calls=session.tool_calls,
            llm_calls=session.llm_calls,
            errors=session.errors,
            replay_value=analysis.get("session_replay_value", 0.0),
            retention_tier=analysis.get("retention_tier", "downsampled"),
            failure_count=session_summary.get("failure_count", 0),
            behavior_alert_count=session_summary.get("behavior_alert_count", 0),
            highlights_count=len(analysis.get("highlights", [])),
            tags=session.tags or [],
            fix_note=session.fix_note,
        )

    def _build_failure_patterns(self, analysis: dict[str, Any]) -> list[FailurePattern]:
        """Build FailurePattern objects from analysis results."""
        clusters = analysis.get("failure_clusters", [])
        rankings_by_id = {r["event_id"]: r for r in analysis.get("event_rankings", [])}

        patterns: list[FailurePattern] = []

        for cluster in clusters:
            representative_id = cluster.get("representative_event_id", "")
            ranking = rankings_by_id.get(representative_id, {})

            # Extract error types from events in this cluster
            event_ids = cluster.get("event_ids", [])
            error_types = set()
            for event_id in event_ids[:10]:  # Limit to 10 events for performance
                r = rankings_by_id.get(event_id, {})
                if "error" in r.get("fingerprint", "").lower():
                    # Extract error type from fingerprint if available
                    fingerprint = r.get("fingerprint", "")
                    if "error" in fingerprint.lower():
                        error_types.add(fingerprint.split(":")[0] if ":" in fingerprint else "RuntimeError")

            patterns.append(
                FailurePattern(
                    fingerprint=cluster.get("fingerprint", ""),
                    count=cluster.get("count", 1),
                    first_seen_at=ranking.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    last_seen_at=ranking.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    sample_error_types=list(error_types)[:5],
                    representative_event_id=representative_id,
                    severity=ranking.get("severity", 0.5),
                )
            )

        # Sort by count
        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns[:20]

    def _build_entity_summaries(self, entity_data: dict[str, Any] | None) -> list[EntitySummary]:
        """Build EntitySummary objects from entity extraction data."""
        if not entity_data:
            return []

        summaries: list[EntitySummary] = []

        # Process each entity type
        entity_types = [
            EntityType.TOOL_NAME,
            EntityType.ERROR_TYPE,
            EntityType.MODEL,
            EntityType.POLICY_NAME,
            EntityType.ALERT_TYPE,
        ]

        for entity_type in entity_types:
            entities = entity_data.get(entity_type, [])
            if entities:
                top_entities = []
                for entity in entities[:5]:
                    top_entities.append(
                        {
                            "value": entity.get("value", ""),
                            "count": entity.get("count", 1),
                            "session_count": entity.get("session_count", 1),
                        }
                    )

                summaries.append(
                    EntitySummary(
                        entity_type=entity_type,
                        total_unique=len(entities),
                        top_entities=top_entities,
                    )
                )

        return summaries


__all__ = ["InsightBuilder"]
