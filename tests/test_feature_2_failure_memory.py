"""Tests for Feature 2: Failure Memory Search.

This module tests the FailureMemory class which provides:
- Storing failure embeddings for similarity search
- Retrieving similar past failures with fix information
- Extracting failure signatures from error events
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.failure_memory import (
    EmbeddingGenerationError,
    FailureMemory,
    SimilarFailureMatch,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def make_error_event():
    """Factory fixture to create error events for failure memory tests."""

    def _make_error_event(
        session_id: str = "s1",
        name: str = "test_error",
        error_type: str = "ConnectionError",
        error_message: str = "Failed to connect to database",
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> TraceEvent:
        data: dict[str, Any] = {
            "error_type": error_type,
            "error_message": error_message,
        }
        if tool_name:
            data["tool_name"] = tool_name
        return TraceEvent(
            session_id=session_id,
            parent_id=None,
            event_type=EventType.ERROR,
            name=name,
            data=data,
            metadata=metadata or {},
            importance=0.8,
            upstream_event_ids=[],
        )

    return _make_error_event


@pytest.fixture
def make_decision_event():
    """Factory fixture to create decision events for failure memory tests."""

    def _make_decision_event(
        session_id: str = "s1",
        name: str = "test_decision",
        reasoning: str = "Test reasoning",
        confidence: float = 0.75,
        chosen_action: str = "proceed",
        metadata: dict | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            session_id=session_id,
            parent_id=None,
            event_type=EventType.DECISION,
            name=name,
            data={
                "reasoning": reasoning,
                "confidence": confidence,
                "chosen_action": chosen_action,
                "alternatives": [],
                "evidence": [],
            },
            metadata=metadata or {},
            importance=0.5,
            upstream_event_ids=[],
        )

    return _make_decision_event


@pytest.fixture
def make_session():
    """Factory fixture to create a session context for failure memory tests."""

    def _make_session(
        session_id: str = "s1",
        agent_name: str = "test_agent",
        framework: str = "test_framework",
        events: list[TraceEvent] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "agent_name": agent_name,
            "framework": framework,
            "events": events or [],
        }

    return _make_session


@pytest.fixture
def mock_embedding_model():
    """Mock embedding model that returns fixed embeddings."""
    model = MagicMock()
    # Default: return a 384-dimensional embedding (typical sentence transformer size)
    model.encode.return_value = [0.1] * 384
    return model


@pytest.fixture
def mock_vector_db():
    """Mock vector database for failure memory storage."""
    db = MagicMock()
    # Default: empty results
    db.query.return_value = {"ids": [], "distances": [], "metadatas": []}
    db.add.return_value = None
    return db


# =============================================================================
# TestFailureMemoryHappyPath
# =============================================================================


class TestFailureMemoryHappyPath:
    """Tests for the happy path of failure memory operations."""

    def test_remember_failure_stores_embedding(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Storing a failure should generate an embedding and call vector_db.add."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)
        error_event = make_error_event(
            error_type="TimeoutError",
            error_message="Connection timed out after 30s",
        )

        # Act
        memory.remember_failure(error_event, fix_applied="Added retry logic")

        # Assert
        mock_embedding_model.encode.assert_called_once()
        call_arg = mock_embedding_model.encode.call_args[0][0]
        assert "TimeoutError" in call_arg
        assert "Connection timed out" in call_arg

        mock_vector_db.add.assert_called_once()
        add_args = mock_vector_db.add.call_args
        assert add_args[1]["metadatas"][0]["error_type"] == "TimeoutError"
        assert add_args[1]["metadatas"][0]["fix_applied"] == "Added retry logic"

    def test_search_similar_returns_matches(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Searching for similar failures should return a ranked list with scores."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Mock the query to return some matches
        mock_vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2"],
            "distances": [0.15, 0.35],  # Lower distance = higher similarity
            "metadatas": [
                {
                    "error_type": "TimeoutError",
                    "error_message": "Connection timed out",
                    "fix_applied": "Added retry",
                    "occurrence_count": 3,
                },
                {
                    "error_type": "ConnectionError",
                    "error_message": "Failed to connect",
                    "fix_applied": "Checked network",
                    "occurrence_count": 1,
                },
            ],
        }

        error_event = make_error_event(
            error_type="TimeoutError",
            error_message="Request timed out",
        )

        # Act
        results = memory.search_similar(error_event, threshold=0.5)

        # Assert
        mock_embedding_model.encode.assert_called()
        mock_vector_db.query.assert_called_once()

        assert len(results) == 2
        assert all(isinstance(r, SimilarFailureMatch) for r in results)
        # Results should be ranked by similarity (highest first)
        assert results[0].similarity_score >= results[1].similarity_score

    def test_search_includes_fix_information(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Search results should include the fix that was previously applied."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        mock_vector_db.query.return_value = {
            "ids": ["fail-1"],
            "distances": [0.1],
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "Invalid input",
                    "fix_applied": "Added input validation with try/except",
                    "occurrence_count": 2,
                },
            ],
        }

        error_event = make_error_event(
            error_type="ValueError",
            error_message="Bad value provided",
        )

        # Act
        results = memory.search_similar(error_event)

        # Assert
        assert len(results) == 1
        assert results[0].fix_applied == "Added input validation with try/except"
        assert results[0].occurrence_count == 2

    def test_failure_signature_extracts_key_fields(self, make_error_event):
        """The failure signature should extract error type and message."""
        # Arrange

        error_event = make_error_event(
            error_type="KeyError",
            error_message="Missing required key 'user_id'",
            tool_name="get_user",
        )

        # Act
        signature = FailureMemory.extract_signature(error_event)

        # Assert
        assert signature.error_type == "KeyError"
        assert "Missing required key" in signature.error_message
        assert signature.tool_name == "get_user"
        assert signature.session_id == error_event.session_id

        # Signature text should include key fields
        sig_text = signature.to_text()
        assert "KeyError" in sig_text
        assert "Missing required key" in sig_text


# =============================================================================
# TestFailureMemoryEdgeCases
# =============================================================================


class TestFailureMemoryEdgeCases:
    """Tests for edge cases in failure memory operations."""

    def test_empty_memory_returns_empty_list(self, make_error_event, mock_embedding_model, mock_vector_db):
        """An empty vector DB should return an empty list, not an error."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Mock empty response
        mock_vector_db.query.return_value = {
            "ids": [],
            "distances": [],
            "metadatas": [],
        }

        error_event = make_error_event()

        # Act
        results = memory.search_similar(error_event)

        # Assert
        assert results == []
        assert isinstance(results, list)

    def test_low_similarity_excluded(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Results below the similarity threshold should be excluded."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Mock results with varying distances
        # High distance = low similarity
        mock_vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2", "fail-3"],
            "distances": [0.2, 0.6, 0.9],  # Only first should pass 0.7 threshold
            "metadatas": [
                {"error_type": "Error1", "error_message": "Msg1", "occurrence_count": 1},
                {"error_type": "Error2", "error_message": "Msg2", "occurrence_count": 1},
                {"error_type": "Error3", "error_message": "Msg3", "occurrence_count": 1},
            ],
        }

        error_event = make_error_event()

        # Act - use high threshold (0.7 similarity = 0.3 max distance)
        results = memory.search_similar(error_event, threshold=0.7)

        # Assert
        assert len(results) == 1
        assert results[0].failure_id == "fail-1"

    def test_duplicate_failures_update_existing(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Storing the same failure again should update the occurrence count."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Mock that the failure already exists
        mock_vector_db.query.return_value = {
            "ids": ["existing-fail-1"],
            "distances": [0.01],  # Very similar
            "metadatas": [
                {
                    "error_type": "ConnectionError",
                    "error_message": "DB connection failed",
                    "occurrence_count": 2,
                    "fix_applied": None,
                },
            ],
        }

        error_event = make_error_event(
            error_type="ConnectionError",
            error_message="DB connection failed",
        )

        # Act
        memory.remember_failure(error_event)

        # Assert - should update existing, not add new
        # The implementation should call update with incremented count
        mock_vector_db.update.assert_called_once()
        update_args = mock_vector_db.update.call_args
        assert update_args[1]["metadatas"][0]["occurrence_count"] == 3

    def test_session_without_error_skipped(
        self,
        make_decision_event,
        make_session,
        mock_embedding_model,
        mock_vector_db,
    ):
        """A session without an error event should not be stored in memory."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        decision = make_decision_event()
        session = make_session(events=[decision])

        # Act
        result = memory.remember_session_failures(session)

        # Assert
        assert result is False or result == []
        mock_vector_db.add.assert_not_called()


# =============================================================================
# TestFailureMemoryErrorHandling
# =============================================================================


class TestFailureMemoryErrorHandling:
    """Tests for error handling in failure memory operations."""

    def test_embedding_failure_returns_graceful_error(self, make_error_event, mock_embedding_model, mock_vector_db):
        """If embedding generation fails, EmbeddingGenerationError should be raised."""
        # Arrange

        mock_embedding_model.encode.side_effect = RuntimeError("Model not loaded")
        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        error_event = make_error_event()

        # Act & Assert
        with pytest.raises(EmbeddingGenerationError) as exc_info:
            memory.remember_failure(error_event)

        assert "Model not loaded" in str(exc_info.value)

    def test_vector_db_unavailable_returns_empty(self, make_error_event, mock_embedding_model, mock_vector_db):
        """If vector DB connection fails, search should return empty list."""
        # Arrange

        mock_vector_db.query.side_effect = ConnectionError("Vector DB unavailable")
        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        error_event = make_error_event()

        # Act
        results = memory.search_similar(error_event)

        # Assert - should return empty list, not raise
        assert results == []

    def test_malformed_metadata_handled(self, make_error_event, mock_embedding_model, mock_vector_db):
        """Malformed or None metadata in results should not crash the search."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Mock results with malformed metadata
        mock_vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2"],
            "distances": [0.1, 0.2],
            "metadatas": [
                None,  # Malformed: None instead of dict
                {"error_type": "Error", "error_message": "Msg"},  # Missing fields
            ],
        }

        error_event = make_error_event()

        # Act - should not raise
        results = memory.search_similar(error_event)

        # Assert - should gracefully handle malformed data
        assert isinstance(results, list)
        # Should filter out or provide defaults for malformed entries
        for result in results:
            assert isinstance(result, SimilarFailureMatch)


# =============================================================================
# TestFailureMemoryIntegration
# =============================================================================


class TestFailureMemoryIntegration:
    """Integration tests for failure memory with other components."""

    def test_link_to_why_button_analysis(
        self,
        make_error_event,
        make_decision_event,
        make_session,
        mock_embedding_model,
        mock_vector_db,
    ):
        """Failure memory should be queryable from Why button results."""
        # Arrange

        memory = FailureMemory(embedding_model=mock_embedding_model, vector_db=mock_vector_db)

        # Set up a previous similar failure
        mock_vector_db.query.return_value = {
            "ids": ["past-fail-1"],
            "distances": [0.15],
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "Invalid configuration",
                    "fix_applied": "Added config validation in startup",
                    "occurrence_count": 5,
                    "session_id": "past-session-123",
                },
            ],
        }

        # Simulate a new error that would trigger "Why" button
        error_event = make_error_event(
            session_id="current-session",
            error_type="ValueError",
            error_message="Invalid configuration detected",
        )

        # Act - simulate what happens when Why button is clicked
        similar_failures = memory.search_similar(error_event, threshold=0.6)

        # Assert
        assert len(similar_failures) == 1
        match = similar_failures[0]
        assert match.fix_applied == "Added config validation in startup"
        assert match.occurrence_count == 5
        assert match.session_id == "past-session-123"

        # The match can be used to populate the Why button tooltip/modal
        why_button_context = {
            "similar_failure_count": len(similar_failures),
            "most_recent_fix": match.fix_applied,
            "times_seen": match.occurrence_count,
        }
        assert why_button_context["similar_failure_count"] == 1
        assert why_button_context["most_recent_fix"] is not None
