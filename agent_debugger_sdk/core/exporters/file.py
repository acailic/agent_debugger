"""File-based memory exporter implementation.

This module provides a reference implementation of the MemoryExporter
protocol using JSON file storage. Useful for local development and testing.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any


class ExportError(Exception):
    """Exception raised when an export operation fails."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause
        self.message = message


# Data class definitions (moved here to avoid circular import)
class _FailurePattern:
    """Represents a recurring failure pattern."""

    def __init__(
        self,
        fingerprint: str,
        count: int,
        first_seen_at: str,
        last_seen_at: str,
        sample_error_types: list[str],
        representative_event_id: str,
        severity: float,
    ):
        self.fingerprint = fingerprint
        self.count = count
        self.first_seen_at = first_seen_at
        self.last_seen_at = last_seen_at
        self.sample_error_types = sample_error_types
        self.representative_event_id = representative_event_id
        self.severity = severity


class _SessionDigest:
    """Condensed summary of a session for memory storage."""

    def __init__(
        self,
        session_id: str,
        agent_name: str,
        framework: str,
        started_at: str,
        ended_at: str | None,
        status: str,
        total_tokens: int,
        total_cost_usd: float,
        tool_calls: int,
        llm_calls: int,
        errors: int,
        replay_value: float,
        retention_tier: str,
        failure_count: int,
        behavior_alert_count: int,
        highlights_count: int,
        tags: list[str],
        fix_note: str | None,
    ):
        self.session_id = session_id
        self.agent_name = agent_name
        self.framework = framework
        self.started_at = started_at
        self.ended_at = ended_at
        self.status = status
        self.total_tokens = total_tokens
        self.total_cost_usd = total_cost_usd
        self.tool_calls = tool_calls
        self.llm_calls = llm_calls
        self.errors = errors
        self.replay_value = replay_value
        self.retention_tier = retention_tier
        self.failure_count = failure_count
        self.behavior_alert_count = behavior_alert_count
        self.highlights_count = highlights_count
        self.tags = tags
        self.fix_note = fix_note


class _TraceInsight:
    """Comprehensive insight package from trace analysis."""

    def __init__(
        self,
        session_digest: _SessionDigest,
        failure_patterns: list[_FailurePattern],
        entity_summaries: list[Any],
        generated_at: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.session_digest = session_digest
        self.failure_patterns = failure_patterns
        self.entity_summaries = entity_summaries
        self.generated_at = generated_at
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for serialization."""
        return {
            "session_digest": self.session_digest.__dict__,
            "failure_patterns": [fp.__dict__ for fp in self.failure_patterns],
            "entity_summaries": [es.__dict__ for es in self.entity_summaries],
            "generated_at": self.generated_at,
            "metadata": self.metadata,
        }


# Type aliases for compatibility
FailurePattern = _FailurePattern
SessionDigest = _SessionDigest
TraceInsight = _TraceInsight


class FileExporter:
    """File-based memory exporter using JSON storage.

    Stores trace insights as JSON files in a directory structure:
    <base_dir>/sessions/<session_id>.json
    <base_dir>/patterns/failure_patterns.json
    <base_dir>/entities/entity_summaries.json

    This is a reference implementation suitable for local development
    and testing. For production use, consider a vector database or
    key-value store implementation.
    """

    def __init__(self, base_dir: str | Path | None = None):
        """Initialize the file exporter.

        Args:
            base_dir: Base directory for storing exported data.
                     Defaults to ~/.peaky-peek/memory
        """
        if base_dir is None:
            home = Path.home()
            base_dir = home / ".peaky-peek" / "memory"

        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.patterns_dir = self.base_dir / "patterns"
        self.entities_dir = self.base_dir / "entities"

        # Create directories if they don't exist
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)

        # Initialize index files
        self._init_index_files()

    def _init_index_files(self) -> None:
        """Initialize index files if they don't exist."""
        patterns_file = self.patterns_dir / "failure_patterns.json"
        entities_file = self.entities_dir / "entity_summaries.json"

        if not patterns_file.exists():
            self._write_json(patterns_file, {"patterns": [], "last_updated": None})

        if not entities_file.exists():
            self._write_json(entities_file, {"summaries": [], "last_updated": None})

    async def export(self, insight: TraceInsight) -> None:
        """Export a trace insight to the file system.

        Args:
            insight: The trace insight to export

        Raises:
            ExportError: If the export operation fails
        """
        try:
            # Write session digest
            session_file = self.sessions_dir / f"{insight.session_digest.session_id}.json"
            self._write_json(session_file, insight.to_dict())

            # Update failure patterns index
            await self._update_failure_patterns(insight)

            # Update entity summaries index
            await self._update_entity_summaries(insight)

        except Exception as e:
            session_id = getattr(insight.session_digest, "session_id", "unknown")
            raise ExportError(
                f"Failed to export insight for session {session_id}", cause=e
            ) from e

    async def query_similar(
        self,
        session_digest: SessionDigest,
        limit: int = 10,
    ) -> list[SessionDigest]:
        """Query for similar sessions based on agent name and error count.

        Args:
            session_digest: The session digest to find similar sessions for
            limit: Maximum number of similar sessions to return

        Returns:
            List of similar session digests
        """
        similar: list[SessionDigest] = []

        # Simple similarity: same agent, overlapping error range
        target_errors = session_digest.errors
        agent_name = session_digest.agent_name

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                data = self._read_json(session_file)
                session_data = data.get("session_digest", {})

                # Skip the same session
                if session_data.get("session_id") == session_digest.session_id:
                    continue

                # Match by agent name
                if session_data.get("agent_name") != agent_name:
                    continue

                # Check if error count is within range
                errors = session_data.get("errors", 0)
                if abs(errors - target_errors) <= max(2, target_errors // 2):
                    similar.append(SessionDigest(**session_data))

                    if len(similar) >= limit:
                        break

            except Exception:
                # Skip invalid files
                continue

        # Sort by replay value (most similar first)
        similar.sort(key=lambda s: s.replay_value, reverse=True)
        return similar[:limit]

    async def get_failure_patterns(
        self,
        agent_name: str | None = None,
        limit: int = 20,
    ) -> list[FailurePattern]:
        """Get top failure patterns from the index.

        Args:
            agent_name: Optional agent name to filter by
            limit: Maximum number of patterns to return

        Returns:
            List of failure patterns sorted by frequency
        """
        patterns_file = self.patterns_dir / "failure_patterns.json"
        data = self._read_json(patterns_file)
        all_patterns = [FailurePattern(**p) for p in data.get("patterns", [])]

        # Filter by agent if specified
        if agent_name:
            all_patterns = [p for p in all_patterns if agent_name in p.representative_event_id]

        # Sort by count
        all_patterns.sort(key=lambda p: p.count, reverse=True)
        return all_patterns[:limit]

    async def health_check(self) -> dict[str, Any]:
        """Check the health of the file exporter.

        Returns:
            Dict with status and health metrics
        """
        session_count = len(list(self.sessions_dir.glob("*.json")))
        patterns_file = self.patterns_dir / "failure_patterns.json"
        entities_file = self.entities_dir / "entity_summaries.json"

        patterns_data = self._read_json(patterns_file)
        entities_data = self._read_json(entities_file)

        return {
            "status": "healthy",
            "exporter_type": "file",
            "base_dir": str(self.base_dir),
            "session_count": session_count,
            "failure_pattern_count": len(patterns_data.get("patterns", [])),
            "entity_summary_count": len(entities_data.get("summaries", [])),
            "last_updated": patterns_data.get("last_updated"),
        }

    async def _update_failure_patterns(self, insight: TraceInsight) -> None:
        """Update the failure patterns index with new patterns from the insight."""
        patterns_file = self.patterns_dir / "failure_patterns.json"
        data = self._read_json(patterns_file)

        existing_patterns = {p["fingerprint"]: p for p in data.get("patterns", [])}

        # Update or add new patterns
        for pattern in insight.failure_patterns:
            fp_dict = asdict(pattern)
            fingerprint = pattern.fingerprint

            if fingerprint in existing_patterns:
                # Update existing pattern
                existing = existing_patterns[fingerprint]
                existing["count"] += pattern.count
                existing["last_seen_at"] = pattern.last_seen_at
                existing["sample_error_types"].extend(pattern.sample_error_types)
                existing["sample_error_types"] = list(set(existing["sample_error_types"]))
            else:
                # Add new pattern
                existing_patterns[fingerprint] = fp_dict

        # Convert back to list and sort by count
        patterns_list = list(existing_patterns.values())
        patterns_list.sort(key=lambda p: p["count"], reverse=True)

        # Keep only top 100 patterns
        patterns_list = patterns_list[:100]

        data["patterns"] = patterns_list
        data["last_updated"] = datetime.now().isoformat()
        self._write_json(patterns_file, data)

    async def _update_entity_summaries(self, insight: TraceInsight) -> None:
        """Update the entity summaries index with new summaries from the insight."""
        entities_file = self.entities_dir / "entity_summaries.json"
        data = self._read_json(entities_file)

        existing_summaries = {s["entity_type"]: s for s in data.get("summaries", [])}

        # Update or add new summaries
        for summary in insight.entity_summaries:
            es_dict = asdict(summary)
            entity_type = summary.entity_type

            if entity_type in existing_summaries:
                # Merge top entities
                existing = existing_summaries[entity_type]
                existing["total_unique"] += summary.total_unique

                # Merge top entity lists and recalculate
                existing_top = {e["value"]: e for e in existing.get("top_entities", [])}
                new_top = {e["value"]: e for e in summary.top_entities}

                for value, entity in new_top.items():
                    if value in existing_top:
                        existing_top[value]["count"] += entity.get("count", 1)
                    else:
                        existing_top[value] = entity

                # Sort by count and keep top 5
                merged_top = sorted(existing_top.values(), key=lambda e: e.get("count", 0), reverse=True)[:5]
                existing["top_entities"] = merged_top
            else:
                existing_summaries[entity_type] = es_dict

        data["summaries"] = list(existing_summaries.values())
        data["last_updated"] = datetime.now().isoformat()
        self._write_json(entities_file, data)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write data to a JSON file atomically."""
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(path)

    def _read_json(self, path: Path) -> dict[str, Any]:
        """Read data from a JSON file."""
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)


__all__ = ["FileExporter"]
