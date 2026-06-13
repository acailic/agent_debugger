"""Unit tests for collector/failure_memory.py"""

from unittest.mock import MagicMock

import pytest

from collector.failure_memory import (
    EmbeddingGenerationError,
    FailureMemory,
    FailureSignature,
    SimilarFailureMatch,
)


class TestFailureSignature:
    """Test FailureSignature dataclass."""

    def test_to_text_with_tool_name(self):
        """Test to_text() includes tool_name when set."""
        sig = FailureSignature(
            error_type="ValueError",
            error_message="invalid input",
            tool_name="data_processor",
        )
        result = sig.to_text()
        assert result == "Error: ValueError | Message: invalid input | Tool: data_processor"

    def test_to_text_without_tool_name(self):
        """Test to_text() excludes tool_name when None."""
        sig = FailureSignature(
            error_type="ValueError",
            error_message="invalid input",
            tool_name=None,
        )
        result = sig.to_text()
        assert result == "Error: ValueError | Message: invalid input"

    def test_defaults(self):
        """Test FailureSignature default values."""
        sig = FailureSignature(
            error_type="TypeError",
            error_message="wrong type",
        )
        assert sig.tool_name is None
        assert sig.session_id is None
        assert sig.additional_context == {}


class TestSimilarFailureMatch:
    """Test SimilarFailureMatch dataclass."""

    def test_defaults(self):
        """Test SimilarFailureMatch default values."""
        sig = FailureSignature(
            error_type="RuntimeError",
            error_message="something failed",
        )
        match = SimilarFailureMatch(
            failure_id="fail-123",
            similarity_score=0.85,
            signature=sig,
        )
        assert match.fix_applied is None
        assert match.occurrence_count == 1
        assert match.session_id is None


class TestFailureMemoryRememberFailure:
    """Test FailureMemory.remember_failure method."""

    def test_new_failure_added_when_no_similar_exists(self):
        """Test remember_failure adds new failure when no similar exists."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return empty results (no similar failures)
        vector_db.query.return_value = {
            "ids": [],
            "distances": [],
            "metadatas": [],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {
            "error_type": "ValueError",
            "error_message": "test error",
            "tool_name": "test_tool",
        }
        error_event.session_id = "session-123"

        # Call remember_failure
        memory.remember_failure(error_event, fix_applied="restarted service")

        # Verify encode was called
        embedding_model.encode.assert_called_once()
        text_arg = embedding_model.encode.call_args[0][0]
        assert "Error: ValueError" in text_arg
        assert "Message: test error" in text_arg
        assert "Tool: test_tool" in text_arg

        # Verify query was called to check for similar failures
        vector_db.query.assert_called_once()

        # Verify add was called (not update, since no similar exists)
        vector_db.add.assert_called_once()
        add_call = vector_db.add.call_args[1]
        assert add_call["embeddings"] == [[0.1, 0.2, 0.3]]
        metadata = add_call["metadatas"][0]
        assert metadata["error_type"] == "ValueError"
        assert metadata["error_message"] == "test error"
        assert metadata["tool_name"] == "test_tool"
        assert metadata["session_id"] == "session-123"
        assert metadata["fix_applied"] == "restarted service"
        assert metadata["occurrence_count"] == 1

        # Verify update was NOT called
        vector_db.update.assert_not_called()

    def test_existing_failure_updated_when_similar(self):
        """Test remember_failure updates existing when similar (distance < 0.1)."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return existing failure with distance < 0.1
        vector_db.query.return_value = {
            "ids": ["existing-fail-123"],
            "distances": [0.05],  # Less than 0.1 threshold
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "test error",
                    "tool_name": "test_tool",
                    "session_id": "session-456",
                    "fix_applied": "old fix",
                    "occurrence_count": 3,
                }
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {
            "error_type": "ValueError",
            "error_message": "test error",
            "tool_name": "test_tool",
        }
        error_event.session_id = "session-789"

        # Call remember_failure
        memory.remember_failure(error_event, fix_applied="new fix")

        # Verify encode was called
        embedding_model.encode.assert_called_once()

        # Verify query was called
        vector_db.query.assert_called_once()

        # Verify update was called (not add, since similar exists)
        vector_db.update.assert_called_once()
        update_call = vector_db.update.call_args[1]
        assert update_call["ids"] == ["existing-fail-123"]
        assert update_call["embeddings"] == [[0.1, 0.2, 0.3]]
        metadata = update_call["metadatas"][0]
        assert metadata["occurrence_count"] == 4  # Incremented from 3
        assert metadata["fix_applied"] == "new fix"  # Updated

        # Verify add was NOT called
        vector_db.add.assert_not_called()

    def test_embedding_generation_error_raises(self):
        """Test remember_failure raises EmbeddingGenerationError when encoding fails."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.side_effect = RuntimeError("model crashed")

        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Call remember_failure and expect exception
        with pytest.raises(EmbeddingGenerationError) as exc_info:
            memory.remember_failure(error_event)

        assert "Failed to generate embedding" in str(exc_info.value)
        assert "model crashed" in str(exc_info.value)

        # Verify no database operations
        vector_db.query.assert_not_called()
        vector_db.add.assert_not_called()
        vector_db.update.assert_not_called()


class TestFailureMemorySearchSimilar:
    """Test FailureMemory.search_similar method."""

    def test_search_similar_returns_matches_above_threshold(self):
        """Test search_similar returns matches above threshold."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return 3 matches with varying distances
        vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2", "fail-3"],
            "distances": [0.1, 0.4, 0.7],  # Similarities: 0.9, 0.6, 0.3
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "error 1",
                    "tool_name": "tool1",
                    "session_id": "sess1",
                    "fix_applied": "fix1",
                    "occurrence_count": 5,
                },
                {
                    "error_type": "TypeError",
                    "error_message": "error 2",
                    "tool_name": None,
                    "session_id": None,
                    "fix_applied": None,
                    "occurrence_count": 2,
                },
                {
                    "error_type": "RuntimeError",
                    "error_message": "error 3",
                    "tool_name": "tool3",
                    "session_id": "sess3",
                    "fix_applied": "fix3",
                    "occurrence_count": 1,
                },
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Search with threshold 0.5
        results = memory.search_similar(error_event, threshold=0.5)

        # Should return 2 matches (similarities 0.9 and 0.6, both >= 0.5)
        assert len(results) == 2

        # Verify sorted by similarity descending
        assert results[0].failure_id == "fail-1"
        assert results[0].similarity_score == 0.9
        assert results[0].signature.error_type == "ValueError"
        assert results[0].signature.error_message == "error 1"
        assert results[0].signature.tool_name == "tool1"
        assert results[0].fix_applied == "fix1"
        assert results[0].occurrence_count == 5
        assert results[0].session_id == "sess1"

        assert results[1].failure_id == "fail-2"
        assert results[1].similarity_score == 0.6
        assert results[1].signature.error_type == "TypeError"
        assert results[1].signature.error_message == "error 2"
        assert results[1].signature.tool_name is None
        assert results[1].fix_applied is None
        assert results[1].occurrence_count == 2
        assert results[1].session_id is None

    def test_search_similar_filters_below_threshold(self):
        """Test search_similar filters out matches below threshold."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return matches with low similarities
        vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2"],
            "distances": [0.6, 0.8],  # Similarities: 0.4, 0.2
            "metadatas": [
                {"error_type": "ValueError", "error_message": "error 1", "tool_name": None, "session_id": None},
                {"error_type": "TypeError", "error_message": "error 2", "tool_name": None, "session_id": None},
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Search with high threshold 0.5
        results = memory.search_similar(error_event, threshold=0.5)

        # Should return 0 matches (both similarities < 0.5)
        assert len(results) == 0

    def test_search_similar_handles_empty_results(self):
        """Test search_similar handles empty database results."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return empty results
        vector_db.query.return_value = {
            "ids": [],
            "distances": [],
            "metadatas": [],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Search
        results = memory.search_similar(error_event)

        # Should return empty list
        assert results == []

    def test_search_similar_handles_errors_gracefully(self):
        """Test search_similar returns empty list on errors."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.side_effect = RuntimeError("database error")

        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Search should return empty list on error
        results = memory.search_similar(error_event)

        assert results == []

    def test_search_similar_handles_none_metadata(self):
        """Test search_similar skips entries with None metadata."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        # Return one valid and one None metadata
        vector_db.query.return_value = {
            "ids": ["fail-1", "fail-2"],
            "distances": [0.1, 0.2],  # Similarities: 0.9, 0.8
            "metadatas": [
                {"error_type": "ValueError", "error_message": "error 1", "tool_name": None, "session_id": None},
                None,  # Should be skipped
            ],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock error event
        error_event = MagicMock()
        error_event.data = {"error_type": "ValueError", "error_message": "test"}
        error_event.session_id = "session-123"

        # Search
        results = memory.search_similar(error_event)

        # Should return only 1 match (skipping None metadata)
        assert len(results) == 1
        assert results[0].failure_id == "fail-1"


class TestFailureMemoryExtractSignature:
    """Test FailureMemory.extract_signature method."""

    def test_extract_signature_extracts_all_fields(self):
        """Test extract_signature extracts all fields from error_event."""
        # Create mock error event with all fields
        error_event = MagicMock()
        error_event.data = {
            "error_type": "KeyError",
            "error_message": "key not found",
            "tool_name": "data_loader",
            "extra_field": "ignored",
        }
        error_event.session_id = "session-abc"

        # Extract signature
        signature = FailureMemory.extract_signature(error_event)

        assert signature.error_type == "KeyError"
        assert signature.error_message == "key not found"
        assert signature.tool_name == "data_loader"
        assert signature.session_id == "session-abc"

    def test_extract_signature_handles_missing_fields(self):
        """Test extract_signature handles missing fields with defaults."""
        # Create mock error event with missing fields
        error_event = MagicMock()
        error_event.data = {
            "error_type": "AttributeError",
            # Missing error_message, tool_name
        }
        error_event.session_id = "session-xyz"

        # Extract signature
        signature = FailureMemory.extract_signature(error_event)

        assert signature.error_type == "AttributeError"
        assert signature.error_message == ""  # Default empty string
        assert signature.tool_name is None  # Default None
        assert signature.session_id == "session-xyz"

    def test_extract_signature_handles_empty_data(self):
        """Test extract_signature handles empty data dict."""
        # Create mock error event with empty data
        error_event = MagicMock()
        error_event.data = {}
        error_event.session_id = "session-empty"

        # Extract signature
        signature = FailureMemory.extract_signature(error_event)

        assert signature.error_type == "Unknown"  # Default
        assert signature.error_message == ""  # Default
        assert signature.tool_name is None  # Default
        assert signature.session_id == "session-empty"

    def test_extract_signature_handles_none_data(self):
        """Test extract_signature handles None data."""
        # Create mock error event with None data
        error_event = MagicMock()
        error_event.data = None
        error_event.session_id = "session-none"

        # Extract signature
        signature = FailureMemory.extract_signature(error_event)

        assert signature.error_type == "Unknown"  # Default
        assert signature.error_message == ""  # Default
        assert signature.tool_name is None  # Default
        assert signature.session_id == "session-none"


class TestFailureMemoryRememberSessionFailures:
    """Test FailureMemory.remember_session_failures method."""

    def test_remember_session_failures_with_error_events(self):
        """Test remember_session_failures stores all error events."""
        # Setup mocks
        embedding_model = MagicMock()
        embedding_model.encode.return_value = [0.1, 0.2, 0.3]

        vector_db = MagicMock()
        vector_db.query.return_value = {
            "ids": [],
            "distances": [],
            "metadatas": [],
        }

        memory = FailureMemory(embedding_model, vector_db)

        # Mock remember_failure to track calls
        memory.remember_failure = MagicMock(wraps=memory.remember_failure)

        # Create mock session with error events
        error_event1 = MagicMock()
        error_event1.event_type.name = "ERROR"
        error_event1.data = {"error_type": "ValueError", "error_message": "error 1"}
        error_event1.session_id = "session-1"

        error_event2 = MagicMock()
        error_event2.event_type.name = "ERROR"
        error_event2.data = {"error_type": "TypeError", "error_message": "error 2"}
        error_event2.session_id = "session-1"

        # Create a non-error event (should be ignored)
        info_event = MagicMock()
        info_event.event_type.name = "INFO"
        info_event.data = {"message": "info"}
        info_event.session_id = "session-1"

        session = {
            "events": [error_event1, info_event, error_event2],
        }

        # Remember session failures
        result = memory.remember_session_failures(session)

        # Should return True
        assert result is True

        # Verify remember_failure was called twice (once per error event)
        assert memory.remember_failure.call_count == 2

    def test_remember_session_failures_no_error_events(self):
        """Test remember_session_failures returns False when no error events."""
        # Setup mocks
        embedding_model = MagicMock()
        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock session without error events
        info_event = MagicMock()
        info_event.event_type.name = "INFO"
        info_event.data = {"message": "info"}

        session = {
            "events": [info_event],
        }

        # Remember session failures
        result = memory.remember_session_failures(session)

        # Should return False
        assert result is False

        # Verify remember_failure was NOT called
        vector_db.add.assert_not_called()
        vector_db.update.assert_not_called()

    def test_remember_session_failures_empty_events(self):
        """Test remember_session_failures handles empty events list."""
        # Setup mocks
        embedding_model = MagicMock()
        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock session with no events
        session = {
            "events": [],
        }

        # Remember session failures
        result = memory.remember_session_failures(session)

        # Should return False
        assert result is False

    def test_remember_session_failures_no_events_key(self):
        """Test remember_session_failures handles missing events key."""
        # Setup mocks
        embedding_model = MagicMock()
        vector_db = MagicMock()

        memory = FailureMemory(embedding_model, vector_db)

        # Create mock session without events key
        session = {}

        # Remember session failures
        result = memory.remember_session_failures(session)

        # Should return False
        assert result is False
