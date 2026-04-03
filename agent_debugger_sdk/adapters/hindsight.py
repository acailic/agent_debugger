"""Hindsight memory integration adapter.

This module provides the HindsightMemoryAdapter which implements the MemoryExporter
protocol to send debugging insights to a Hindsight memory bank. It maps Peaky Peek
insights to Hindsight memory unit types (failures → experiences, patterns → observations,
entities → world facts) and uses TEMPR retrieval for context recall.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from agent_debugger_sdk.core.exporters import (
    EntitySummary,
    ExportError,
    FailurePattern,
    SessionDigest,
    TraceInsight,
)

logger = logging.getLogger(__name__)


@dataclass
class HindsightConfig:
    """Configuration for Hindsight memory integration."""

    endpoint: str = "http://localhost:9000"
    bank_id: str = "agent_debugger"
    api_key: str | None = None
    timeout_seconds: float = 30.0
    enabled: bool = False

    # Memory type mappings
    experience_memory_type: str = "failure_experience"
    observation_memory_type: str = "pattern_observation"
    world_fact_memory_type: str = "entity_fact"

    # TEMPR retrieval settings
    tempr_enabled: bool = True
    tempr_top_k: int = 5
    tempr_threshold: float = 0.3


class HindsightMemoryAdapter:
    """Adapter for exporting trace insights to Hindsight memory bank.

    This class implements the MemoryExporter protocol and maps Peaky Peek
    trace insights to Hindsight memory unit types:
    - Failure patterns → Experience memories
    - Entity summaries → World fact memories
    - Session digests → Observation memories

    It also supports TEMPR (Temporal Episode Memory with Progressive Retrieval)
    for recalling relevant past debugging context.
    """

    def __init__(self, config: HindsightConfig | None = None):
        """Initialize the Hindsight memory adapter.

        Args:
            config: Hindsight configuration. If None, uses defaults.
        """
        self.config = config or HindsightConfig()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for Hindsight API."""
        if self._client is None:
            timeout = httpx.Timeout(self.config.timeout_seconds)
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.config.endpoint,
                timeout=timeout,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def export(self, insight: TraceInsight) -> None:
        """Export a trace insight to Hindsight memory bank.

        Maps Peaky Peek insights to Hindsight memory units:
        - Session digest → Observation memory
        - Failure patterns → Experience memories
        - Entity summaries → World fact memories

        Args:
            insight: The trace insight to export

        Raises:
            ExportError: If the export operation fails
        """
        if not self.config.enabled:
            logger.debug("Hindsight integration disabled, skipping export")
            return

        try:
            client = await self._get_client()

            # Export session digest as observation memory
            await self._export_observation_memory(client, insight.session_digest)

            # Export failure patterns as experience memories
            for pattern in insight.failure_patterns:
                await self._export_experience_memory(client, pattern, insight.session_digest)

            # Export entity summaries as world fact memories
            for summary in insight.entity_summaries:
                await self._export_world_fact_memory(client, summary, insight.session_digest)

            logger.info(f"Exported insight for session {insight.session_digest.session_id} to Hindsight")

        except httpx.HTTPStatusError as e:
            raise ExportError(
                f"Hindsight API error: {e.response.status_code}", cause=e
            ) from e
        except Exception as e:
            raise ExportError(
                f"Failed to export insight to Hindsight: {e}", cause=e
            ) from e

    async def query_similar(
        self,
        session_digest: SessionDigest,
        limit: int = 10,
    ) -> list[SessionDigest]:
        """Query Hindsight for similar sessions using TEMPR retrieval.

        Args:
            session_digest: The session digest to find similar sessions for
            limit: Maximum number of similar sessions to return

        Returns:
            List of similar session digests
        """
        if not self.config.enabled or not self.config.tempr_enabled:
            return []

        try:
            client = await self._get_client()

            # Build TEMPR query from session digest
            query = self._build_tempr_query(session_digest)

            response = await client.post(
                f"/api/v1/banks/{self.config.bank_id}/retrieve",
                json={
                    "query": query,
                    "top_k": min(limit, self.config.tempr_top_k),
                    "threshold": self.config.tempr_threshold,
                    "memory_types": [
                        self.config.experience_memory_type,
                        self.config.observation_memory_type,
                    ],
                },
            )
            response.raise_for_status()

            data = response.json()
            return self._parse_retrieved_sessions(data.get("memories", []))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Hindsight bank {self.config.bank_id} not found, returning empty results")
                return []
            logger.error(f"Hindsight retrieval error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Failed to query similar sessions from Hindsight: {e}")
            return []

    async def get_failure_patterns(
        self,
        agent_name: str | None = None,
        limit: int = 20,
    ) -> list[FailurePattern]:
        """Get top failure patterns from Hindsight experience memories.

        Args:
            agent_name: Optional agent name to filter by
            limit: Maximum number of patterns to return

        Returns:
            List of failure patterns sorted by frequency
        """
        if not self.config.enabled:
            return []

        try:
            client = await self._get_client()

            # Query experience memories by type
            params: dict[str, Any] = {
                "memory_type": self.config.experience_memory_type,
                "limit": limit,
                "sort": "-frequency",
            }
            if agent_name:
                params["agent_name"] = agent_name

            response = await client.get(
                f"/api/v1/banks/{self.config.bank_id}/memories",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            return self._parse_hindsight_patterns(data.get("memories", []))

        except Exception as e:
            logger.error(f"Failed to get failure patterns from Hindsight: {e}")
            return []

    async def health_check(self) -> dict[str, Any]:
        """Check the health of the Hindsight connection.

        Returns:
            Dict with status and health metrics
        """
        if not self.config.enabled:
            return {
                "status": "disabled",
                "exporter_type": "hindsight",
                "message": "Hindsight integration is disabled",
            }

        try:
            client = await self._get_client()

            response = await client.get("/api/v1/health")
            response.raise_for_status()

            health_data = response.json()
            return {
                "status": "healthy",
                "exporter_type": "hindsight",
                "endpoint": self.config.endpoint,
                "bank_id": self.config.bank_id,
                "hindsight_status": health_data.get("status", "unknown"),
                "tempr_enabled": self.config.tempr_enabled,
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "exporter_type": "hindsight",
                "endpoint": self.config.endpoint,
                "bank_id": self.config.bank_id,
                "error": str(e),
            }

    async def _export_observation_memory(
        self,
        client: httpx.AsyncClient,
        digest: SessionDigest,
    ) -> None:
        """Export session digest as observation memory."""
        memory = {
            "memory_type": self.config.observation_memory_type,
            "bank_id": self.config.bank_id,
            "content": {
                "session_id": digest.session_id,
                "agent_name": digest.agent_name,
                "framework": digest.framework,
                "status": digest.status,
                "errors": digest.errors,
                "replay_value": digest.replay_value,
                "failure_count": digest.failure_count,
                "behavior_alert_count": digest.behavior_alert_count,
                "highlights_count": digest.highlights_count,
                "tags": digest.tags,
            },
            "metadata": {
                "started_at": digest.started_at,
                "ended_at": digest.ended_at,
                "total_tokens": digest.total_tokens,
                "total_cost_usd": digest.total_cost_usd,
                "tool_calls": digest.tool_calls,
                "llm_calls": digest.llm_calls,
                "retention_tier": digest.retention_tier,
                "fix_note": digest.fix_note,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = await client.post(
            f"/api/v1/banks/{self.config.bank_id}/memories",
            json=memory,
        )
        response.raise_for_status()

    async def _export_experience_memory(
        self,
        client: httpx.AsyncClient,
        pattern: FailurePattern,
        digest: SessionDigest,
    ) -> None:
        """Export failure pattern as experience memory."""
        memory = {
            "memory_type": self.config.experience_memory_type,
            "bank_id": self.config.bank_id,
            "content": {
                "fingerprint": pattern.fingerprint,
                "error_types": pattern.sample_error_types,
                "severity": pattern.severity,
                "agent_name": digest.agent_name,
                "session_id": digest.session_id,
                "representative_event_id": pattern.representative_event_id,
            },
            "metadata": {
                "count": pattern.count,
                "first_seen_at": pattern.first_seen_at,
                "last_seen_at": pattern.last_seen_at,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = await client.post(
            f"/api/v1/banks/{self.config.bank_id}/memories",
            json=memory,
        )
        response.raise_for_status()

    async def _export_world_fact_memory(
        self,
        client: httpx.AsyncClient,
        summary: EntitySummary,
        digest: SessionDigest,
    ) -> None:
        """Export entity summary as world fact memory."""
        memory = {
            "memory_type": self.config.world_fact_memory_type,
            "bank_id": self.config.bank_id,
            "content": {
                "entity_type": summary.entity_type,
                "total_unique": summary.total_unique,
                "top_entities": summary.top_entities,
                "agent_name": digest.agent_name,
            },
            "metadata": {
                "session_id": digest.session_id,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = await client.post(
            f"/api/v1/banks/{self.config.bank_id}/memories",
            json=memory,
        )
        response.raise_for_status()

    def _build_tempr_query(self, digest: SessionDigest) -> str:
        """Build TEMPR retrieval query from session digest."""
        query_parts = [
            f"agent:{digest.agent_name}",
            f"framework:{digest.framework}",
        ]

        if digest.errors > 0:
            query_parts.append(f"errors:{digest.errors}")

        if digest.failure_count > 0:
            query_parts.append(f"failures:{digest.failure_count}")

        if digest.tags:
            query_parts.append(f"tags:{','.join(digest.tags)}")

        return " ".join(query_parts)

    def _parse_retrieved_sessions(self, memories: list[dict]) -> list[SessionDigest]:
        """Parse retrieved memories into session digests."""
        digests: list[SessionDigest] = []

        for memory in memories:
            try:
                content = memory.get("content", {})
                metadata = memory.get("metadata", {})

                if memory.get("memory_type") == self.config.observation_memory_type:
                    digest = SessionDigest(
                        session_id=content.get("session_id", ""),
                        agent_name=content.get("agent_name", ""),
                        framework=content.get("framework", ""),
                        started_at=metadata.get("started_at", ""),
                        ended_at=metadata.get("ended_at"),
                        status=content.get("status", ""),
                        total_tokens=metadata.get("total_tokens", 0),
                        total_cost_usd=metadata.get("total_cost_usd", 0.0),
                        tool_calls=metadata.get("tool_calls", 0),
                        llm_calls=metadata.get("llm_calls", 0),
                        errors=content.get("errors", 0),
                        replay_value=content.get("replay_value", 0.0),
                        retention_tier=metadata.get("retention_tier", "downsampled"),
                        failure_count=content.get("failure_count", 0),
                        behavior_alert_count=content.get("behavior_alert_count", 0),
                        highlights_count=content.get("highlights_count", 0),
                        tags=content.get("tags", []),
                        fix_note=metadata.get("fix_note"),
                    )
                    digests.append(digest)
            except Exception as e:
                logger.warning(f"Failed to parse retrieved memory: {e}")
                continue

        return digests

    def _parse_hindsight_patterns(self, memories: list[dict]) -> list[FailurePattern]:
        """Parse Hindsight memories into failure patterns."""
        patterns: list[FailurePattern] = []

        for memory in memories:
            try:
                content = memory.get("content", {})
                metadata = memory.get("metadata", {})

                pattern = FailurePattern(
                    fingerprint=content.get("fingerprint", ""),
                    count=metadata.get("count", 1),
                    first_seen_at=metadata.get("first_seen_at", ""),
                    last_seen_at=metadata.get("last_seen_at", ""),
                    sample_error_types=content.get("error_types", []),
                    representative_event_id=content.get("representative_event_id", ""),
                    severity=content.get("severity", 0.5),
                )
                patterns.append(pattern)
            except Exception as e:
                logger.warning(f"Failed to parse Hindsight pattern: {e}")
                continue

        return patterns


__all__ = ["HindsightMemoryAdapter", "HindsightConfig"]
