"""Failure Memory module for storing and searching similar failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class EmbeddingGenerationError(Exception):
    """Raised when embedding generation fails."""

    pass


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
    """Stores and searches for similar failures using embeddings."""

    def __init__(self, embedding_model: Any, vector_db: Any):
        """Initialize failure memory with embedding model and vector database."""
        self.embedding_model = embedding_model
        self.vector_db = vector_db

    def remember_failure(self, error_event: Any, fix_applied: str | None = None) -> None:
        """Store a failure in memory with optional fix information."""
        signature = self.extract_signature(error_event)
        text = signature.to_text()

        try:
            embedding = self.embedding_model.encode(text)
        except Exception as e:
            raise EmbeddingGenerationError(f"Failed to generate embedding: {e}") from e

        metadata = {
            "error_type": signature.error_type,
            "error_message": signature.error_message,
            "tool_name": signature.tool_name,
            "session_id": signature.session_id,
            "fix_applied": fix_applied,
            "occurrence_count": 1,
        }

        # Check if similar failure already exists
        existing_results = self.vector_db.query(
            query_embeddings=[embedding],
            n_results=1,
        )

        if existing_results["ids"] and existing_results.get("distances") and existing_results["distances"][0] < 0.1:
            # Update existing failure
            existing_id = existing_results["ids"][0]
            existing_metadata = existing_results["metadatas"][0]
            existing_metadata["occurrence_count"] += 1
            if fix_applied:
                existing_metadata["fix_applied"] = fix_applied

            self.vector_db.update(
                ids=[existing_id],
                embeddings=[embedding],
                metadatas=[existing_metadata],
            )
        else:
            # Add new failure
            self.vector_db.add(
                embeddings=[embedding],
                metadatas=[metadata],
            )

    def search_similar(self, error_event: Any, threshold: float = 0.5) -> list[SimilarFailureMatch]:
        """Search for similar failures in memory."""
        try:
            signature = self.extract_signature(error_event)
            text = signature.to_text()
            embedding = self.embedding_model.encode(text)

            results = self.vector_db.query(
                query_embeddings=[embedding],
                n_results=10,
            )
        except Exception:
            # Return empty list on any error
            return []

        matches = []
        for i, failure_id in enumerate(results["ids"]):
            distance = results["distances"][i]
            similarity_score = 1 - distance

            if similarity_score < threshold:
                continue

            metadata = results["metadatas"][i]
            if metadata is None:
                continue

            sig = FailureSignature(
                error_type=metadata.get("error_type", "Unknown"),
                error_message=metadata.get("error_message", ""),
                tool_name=metadata.get("tool_name"),
                session_id=metadata.get("session_id"),
            )

            match = SimilarFailureMatch(
                failure_id=failure_id,
                similarity_score=similarity_score,
                signature=sig,
                fix_applied=metadata.get("fix_applied"),
                occurrence_count=metadata.get("occurrence_count", 1),
                session_id=metadata.get("session_id"),
            )
            matches.append(match)

        # Sort by similarity score (highest first)
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    @staticmethod
    def extract_signature(error_event: Any) -> FailureSignature:
        """Extract signature from an error event."""
        data = error_event.data or {}
        return FailureSignature(
            error_type=data.get("error_type", "Unknown"),
            error_message=data.get("error_message", ""),
            tool_name=data.get("tool_name"),
            session_id=error_event.session_id,
        )

    def remember_session_failures(self, session: dict[str, Any]) -> bool | list[Any]:
        """Store all failures from a session."""
        events = session.get("events", [])
        error_events = [e for e in events if hasattr(e, "event_type") and e.event_type.name == "ERROR"]

        if not error_events:
            return False

        for error_event in error_events:
            self.remember_failure(error_event)

        return True
