"""Failure memory for similarity-based failure search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent


class EmbeddingGenerationError(Exception):
    """Raised when embedding generation fails."""


@dataclass
class FailureSignature:
    """Signature extracted from a failure event for embedding."""

    error_type: str
    error_message: str
    tool_name: str | None = None
    session_id: str | None = None
    additional_context: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        """Convert signature to text for embedding."""
        parts = [f"Error: {self.error_type}", f"Message: {self.error_message}"]
        if self.tool_name:
            parts.append(f"Tool: {self.tool_name}")
        return " | ".join(parts)


@dataclass
class SimilarFailureMatch:
    """A match from the failure memory search."""

    failure_id: str
    similarity_score: float
    signature: FailureSignature
    fix_applied: str | None = None
    occurrence_count: int = 1
    session_id: str | None = None


class FailureMemory:
    """Stores and searches failure embeddings for similarity-based lookup."""

    _DUPLICATE_DISTANCE_THRESHOLD = 0.05

    def __init__(self, embedding_model: Any, vector_db: Any) -> None:
        self._embedding_model = embedding_model
        self._vector_db = vector_db

    @staticmethod
    def extract_signature(error_event: TraceEvent) -> FailureSignature:
        """Extract a failure signature from an error event."""
        data = error_event.data or {}
        return FailureSignature(
            error_type=data.get("error_type", "Unknown"),
            error_message=data.get("error_message", ""),
            tool_name=data.get("tool_name"),
            session_id=error_event.session_id,
        )

    def _generate_embedding(self, text: str) -> list[float]:
        try:
            return self._embedding_model.encode(text)
        except Exception as exc:
            raise EmbeddingGenerationError(str(exc)) from exc

    def remember_failure(self, error_event: TraceEvent, fix_applied: str | None = None) -> None:
        """Store a failure embedding, updating occurrence count for near-duplicates."""
        signature = self.extract_signature(error_event)
        embedding = self._generate_embedding(signature.to_text())

        existing = self._vector_db.query(
            query_embeddings=[embedding],
            n_results=1,
        )

        ids = existing.get("ids", [])
        distances = existing.get("distances", [])
        metadatas = existing.get("metadatas", [])

        if ids and distances and distances[0] <= self._DUPLICATE_DISTANCE_THRESHOLD:
            existing_id = ids[0]
            existing_meta = (metadatas[0] if metadatas else None) or {}
            new_count = existing_meta.get("occurrence_count", 1) + 1
            self._vector_db.update(
                id=existing_id,
                metadata={
                    **existing_meta,
                    "occurrence_count": new_count,
                    "fix_applied": fix_applied or existing_meta.get("fix_applied"),
                },
            )
        else:
            failure_id = str(uuid.uuid4())
            self._vector_db.add(
                embeddings=[embedding],
                ids=[failure_id],
                metadata={
                    "error_type": signature.error_type,
                    "error_message": signature.error_message,
                    "tool_name": signature.tool_name,
                    "session_id": signature.session_id,
                    "fix_applied": fix_applied,
                    "occurrence_count": 1,
                },
            )

    def search_similar(self, error_event: TraceEvent, threshold: float = 0.5) -> list[SimilarFailureMatch]:
        """Return failures similar to the given event, ranked by similarity score."""
        try:
            signature = self.extract_signature(error_event)
            embedding = self._generate_embedding(signature.to_text())
            results = self._vector_db.query(
                query_embeddings=[embedding],
                n_results=10,
            )
        except (ConnectionError, EmbeddingGenerationError):
            return []

        ids = results.get("ids", [])
        distances = results.get("distances", [])
        metadatas = results.get("metadatas", [])

        matches: list[SimilarFailureMatch] = []
        for i, failure_id in enumerate(ids):
            dist = distances[i] if i < len(distances) else 1.0
            meta = (metadatas[i] if i < len(metadatas) else None) or {}

            similarity_score = 1.0 - dist
            if similarity_score < threshold:
                continue

            sig = FailureSignature(
                error_type=meta.get("error_type", "Unknown"),
                error_message=meta.get("error_message", ""),
                tool_name=meta.get("tool_name"),
                session_id=meta.get("session_id"),
            )
            matches.append(
                SimilarFailureMatch(
                    failure_id=failure_id,
                    similarity_score=similarity_score,
                    signature=sig,
                    fix_applied=meta.get("fix_applied"),
                    occurrence_count=meta.get("occurrence_count", 1),
                    session_id=meta.get("session_id"),
                )
            )

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    def remember_session_failures(self, session: dict[str, Any]) -> bool | list[TraceEvent]:
        """Store all error events from a session. Returns False if no errors found."""
        events = session.get("events", [])
        error_events = [e for e in events if hasattr(e, "event_type") and e.event_type == EventType.ERROR]
        if not error_events:
            return False
        for event in error_events:
            self.remember_failure(event)
        return error_events
