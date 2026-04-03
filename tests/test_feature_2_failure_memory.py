"""Tests for Feature 2: Failure Memory.

Tests for collector.failure_memory.FailureMemory which stores and
searches for similar failures using embeddings and a vector database.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from collector.failure_memory import (
    EmbeddingGenerationError,
    FailureMemory,
    FailureSignature,
    SimilarFailureMatch,
)

# =============================================================================
# Happy Path Tests
# =============================================================================


class TestFailureMemoryHappyPath:
    """Tests for normal operation of FailureMemory."""

    def test_remember_failure_adds_to_vector_db(self, make_error_event):
        """remember_failure stores the failure in the vector database."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.return_value = {"ids": [], "distances": [], "metadatas": []}

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event(
            session_id="session-1",
            error_type="ValueError",
            error_message="Invalid input",
        )

        memory.remember_failure(error_event)

        assert vector_db.add.called
        add_args = vector_db.add.call_args
        assert add_args[1]["metadatas"][0]["error_type"] == "ValueError"
        assert add_args[1]["metadatas"][0]["error_message"] == "Invalid input"

    def test_remember_failure_with_fix_stores_fix(self, make_error_event):
        """remember_failure stores fix_applied when provided."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.return_value = {"ids": [], "distances": [], "metadatas": []}

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event(error_type="NetworkError", error_message="Timeout")

        memory.remember_failure(error_event, fix_applied="retry_with_backoff")

        add_args = vector_db.add.call_args
        assert add_args[1]["metadatas"][0]["fix_applied"] == "retry_with_backoff"

    def test_remember_failure_updates_existing_similar(self, make_error_event):
        """remember_failure updates existing entry when a very similar failure exists."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        # Simulate existing similar failure (distance < 0.1 triggers update path)
        vector_db.query.return_value = {
            "ids": ["existing-failure-id"],
            "distances": [0.05],
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "Same class of error",
                    "occurrence_count": 1,
                    "fix_applied": None,
                }
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event(error_type="ValueError", error_message="Same error")

        memory.remember_failure(error_event)

        assert vector_db.update.called
        assert not vector_db.add.called
        update_args = vector_db.update.call_args
        assert update_args[1]["metadatas"][0]["occurrence_count"] == 2

    def test_remember_failure_update_stores_new_fix(self, make_error_event):
        """remember_failure overwrites fix_applied when updating an existing entry."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.return_value = {
            "ids": ["existing-id"],
            "distances": [0.04],
            "metadatas": [{"occurrence_count": 1, "fix_applied": None}],
        }

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        memory.remember_failure(error_event, fix_applied="new_fix")

        update_args = vector_db.update.call_args
        assert update_args[1]["metadatas"][0]["fix_applied"] == "new_fix"

    def test_search_similar_returns_match_instances(self, make_error_event):
        """search_similar returns SimilarFailureMatch instances."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.return_value = {
            "ids": ["failure-1"],
            "distances": [0.2],
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "Bad input",
                    "tool_name": None,
                    "session_id": "s1",
                    "fix_applied": "validated_input",
                    "occurrence_count": 3,
                }
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event(error_type="ValueError", error_message="Invalid value")

        matches = memory.search_similar(error_event)

        assert len(matches) == 1
        assert isinstance(matches[0], SimilarFailureMatch)
        assert matches[0].failure_id == "failure-1"
        assert matches[0].fix_applied == "validated_input"
        assert matches[0].occurrence_count == 3

    def test_search_similar_filters_below_threshold(self, make_error_event):
        """search_similar excludes matches with similarity below threshold."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        # distance=0.7 => similarity_score=0.3, below default threshold of 0.5
        vector_db.query.return_value = {
            "ids": ["failure-1"],
            "distances": [0.7],
            "metadatas": [
                {
                    "error_type": "DifferentError",
                    "error_message": "Different",
                    "tool_name": None,
                    "session_id": None,
                    "fix_applied": None,
                    "occurrence_count": 1,
                }
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        matches = memory.search_similar(error_event)

        assert matches == []

    def test_search_similar_sorted_by_score_descending(self, make_error_event):
        """search_similar returns matches sorted by similarity score descending."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.return_value = {
            "ids": ["failure-low", "failure-high"],
            "distances": [0.3, 0.1],  # similarity_scores: 0.7, 0.9
            "metadatas": [
                {
                    "error_type": "Error1",
                    "error_message": "msg1",
                    "tool_name": None,
                    "session_id": None,
                    "fix_applied": None,
                    "occurrence_count": 1,
                },
                {
                    "error_type": "Error2",
                    "error_message": "msg2",
                    "tool_name": None,
                    "session_id": None,
                    "fix_applied": None,
                    "occurrence_count": 1,
                },
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        matches = memory.search_similar(error_event)

        assert len(matches) == 2
        assert matches[0].similarity_score >= matches[1].similarity_score

    def test_extract_signature_from_error_event(self, make_error_event):
        """extract_signature returns FailureSignature with correct fields."""
        error_event = make_error_event(
            session_id="session-42",
            error_type="TimeoutError",
            error_message="Connection timed out",
        )

        sig = FailureMemory.extract_signature(error_event)

        assert isinstance(sig, FailureSignature)
        assert sig.error_type == "TimeoutError"
        assert sig.error_message == "Connection timed out"
        assert sig.session_id == "session-42"

    def test_remember_session_failures_stores_all_errors(self, make_error_event):
        """remember_session_failures processes all ERROR events in a session."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2]
        vector_db.query.return_value = {"ids": [], "distances": [], "metadatas": []}

        memory = FailureMemory(embedding_model, vector_db)

        error1 = make_error_event(session_id="s1", error_type="Error1", error_message="First")
        error2 = make_error_event(session_id="s1", error_type="Error2", error_message="Second")
        session = {"events": [error1, error2]}

        result = memory.remember_session_failures(session)

        assert result is True
        assert vector_db.add.call_count == 2

    def test_remember_session_failures_no_errors_returns_false(self, make_event):
        """remember_session_failures returns False when session has no ERROR events."""
        embedding_model = MagicMock()
        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # make_event defaults to TOOL_CALL type, not ERROR
        tool_event = make_event()
        session = {"events": [tool_event]}

        result = memory.remember_session_failures(session)

        assert result is False
        assert not vector_db.add.called

    def test_remember_session_failures_empty_session_returns_false(self):
        """remember_session_failures returns False for empty event list."""
        embedding_model = MagicMock()
        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)
        result = memory.remember_session_failures({"events": []})

        assert result is False


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestFailureMemoryErrorHandling:
    """Error handling tests for FailureMemory."""

    def test_remember_failure_raises_embedding_generation_error(self, make_error_event):
        """remember_failure raises EmbeddingGenerationError when encode fails."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.side_effect = RuntimeError("GPU out of memory")
        vector_db.query.return_value = {"ids": [], "distances": [], "metadatas": []}

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        with pytest.raises(EmbeddingGenerationError):
            memory.remember_failure(error_event)

    def test_search_similar_returns_empty_on_encode_error(self, make_error_event):
        """search_similar returns empty list when embedding encode fails."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.side_effect = Exception("Unexpected failure")

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        matches = memory.search_similar(error_event)

        assert matches == []

    def test_search_similar_returns_empty_on_query_error(self, make_error_event):
        """search_similar returns empty list when vector_db.query fails."""
        embedding_model = MagicMock()
        vector_db = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]
        vector_db.query.side_effect = Exception("DB connection error")

        memory = FailureMemory(embedding_model, vector_db)
        error_event = make_error_event()

        matches = memory.search_similar(error_event)

        assert matches == []


# =============================================================================
# FailureSignature Tests
# =============================================================================


class TestFailureSignature:
    """Tests for FailureSignature.to_text()."""

    def test_to_text_includes_error_type_and_message(self):
        """to_text includes error type and message."""
        sig = FailureSignature(error_type="ValueError", error_message="Bad input")
        text = sig.to_text()

        assert "ValueError" in text
        assert "Bad input" in text

    def test_to_text_includes_tool_name_when_present(self):
        """to_text includes tool name when provided."""
        sig = FailureSignature(
            error_type="ToolError",
            error_message="Tool failed",
            tool_name="file_writer",
        )
        text = sig.to_text()

        assert "file_writer" in text

    def test_to_text_omits_tool_section_when_none(self):
        """to_text skips tool name section when tool_name is None."""
        sig = FailureSignature(error_type="Error", error_message="msg", tool_name=None)
        text = sig.to_text()

        assert "Tool:" not in text
