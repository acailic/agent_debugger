"""Tests for collector/failure_memory.py - failure memory storage and search."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from collector.failure_memory import (
    EmbeddingGenerationError,
    FailureMemory,
    FailureSignature,
    SimilarFailureMatch,
)


def make_error_event(
    error_type: str = "ValueError",
    error_message: str = "test error",
    tool_name: str | None = None,
    session_id: str | None = "session-1",
) -> MagicMock:
    event = MagicMock()
    event.session_id = session_id
    event.data = {
        "error_type": error_type,
        "error_message": error_message,
        "tool_name": tool_name,
    }
    return event


def make_failure_memory() -> tuple[FailureMemory, MagicMock, MagicMock]:
    embedding_model = MagicMock()
    embedding_model.encode.return_value = [0.1, 0.2, 0.3]
    vector_db = MagicMock()
    vector_db.query.return_value = {"ids": [], "distances": [], "metadatas": []}
    return FailureMemory(embedding_model, vector_db), embedding_model, vector_db


class TestFailureSignature:
    """Tests for FailureSignature dataclass."""

    def test_to_text_basic(self):
        sig = FailureSignature(error_type="ValueError", error_message="bad value")
        text = sig.to_text()
        assert "Error: ValueError" in text
        assert "Message: bad value" in text

    def test_to_text_includes_tool_name(self):
        sig = FailureSignature(error_type="IOError", error_message="file not found", tool_name="read_file")
        assert "Tool: read_file" in sig.to_text()

    def test_to_text_omits_tool_name_when_none(self):
        sig = FailureSignature(error_type="ValueError", error_message="bad", tool_name=None)
        assert "Tool:" not in sig.to_text()


class TestExtractSignature:
    """Tests for FailureMemory.extract_signature static method."""

    def test_extracts_all_fields(self):
        event = make_error_event(error_type="KeyError", error_message="key missing", tool_name="lookup", session_id="s1")
        sig = FailureMemory.extract_signature(event)
        assert sig.error_type == "KeyError"
        assert sig.error_message == "key missing"
        assert sig.tool_name == "lookup"
        assert sig.session_id == "s1"

    def test_defaults_for_empty_data(self):
        event = MagicMock()
        event.session_id = None
        event.data = {}
        sig = FailureMemory.extract_signature(event)
        assert sig.error_type == "Unknown"
        assert sig.error_message == ""
        assert sig.tool_name is None


class TestRememberFailure:
    """Tests for FailureMemory.remember_failure."""

    def test_adds_new_failure_when_none_similar(self):
        fm, _, vector_db = make_failure_memory()
        fm.remember_failure(make_error_event())
        vector_db.add.assert_called_once()
        kwargs = vector_db.add.call_args[1]
        assert kwargs["metadatas"][0]["error_type"] == "ValueError"
        assert kwargs["metadatas"][0]["error_message"] == "test error"

    def test_add_stores_fix_applied(self):
        fm, _, vector_db = make_failure_memory()
        fm.remember_failure(make_error_event(), fix_applied="retry with backoff")
        kwargs = vector_db.add.call_args[1]
        assert kwargs["metadatas"][0]["fix_applied"] == "retry with backoff"

    def test_add_sets_occurrence_count_to_one(self):
        fm, _, vector_db = make_failure_memory()
        fm.remember_failure(make_error_event())
        kwargs = vector_db.add.call_args[1]
        assert kwargs["metadatas"][0]["occurrence_count"] == 1

    def test_updates_existing_when_similar_found(self):
        fm, _, vector_db = make_failure_memory()
        existing_metadata = {
            "error_type": "ValueError",
            "error_message": "test error",
            "tool_name": None,
            "session_id": "session-1",
            "fix_applied": None,
            "occurrence_count": 1,
        }
        vector_db.query.return_value = {
            "ids": ["existing-id"],
            "distances": [0.05],
            "metadatas": [existing_metadata],
        }
        fm.remember_failure(make_error_event())
        vector_db.update.assert_called_once()
        kwargs = vector_db.update.call_args[1]
        assert kwargs["metadatas"][0]["occurrence_count"] == 2
        vector_db.add.assert_not_called()

    def test_update_sets_fix_applied(self):
        fm, _, vector_db = make_failure_memory()
        existing_metadata = {
            "error_type": "ValueError",
            "error_message": "test error",
            "tool_name": None,
            "session_id": "session-1",
            "fix_applied": None,
            "occurrence_count": 2,
        }
        vector_db.query.return_value = {
            "ids": ["existing-id"],
            "distances": [0.05],
            "metadatas": [existing_metadata],
        }
        fm.remember_failure(make_error_event(), fix_applied="increase timeout")
        kwargs = vector_db.update.call_args[1]
        assert kwargs["metadatas"][0]["fix_applied"] == "increase timeout"

    def test_adds_new_when_distance_at_or_above_threshold(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["existing-id"],
            "distances": [0.2],
            "metadatas": [{}],
        }
        fm.remember_failure(make_error_event())
        vector_db.add.assert_called_once()
        vector_db.update.assert_not_called()

    def test_raises_embedding_error_on_encode_failure(self):
        fm, embedding_model, _ = make_failure_memory()
        embedding_model.encode.side_effect = RuntimeError("model unavailable")
        with pytest.raises(EmbeddingGenerationError):
            fm.remember_failure(make_error_event())


class TestSearchSimilar:
    """Tests for FailureMemory.search_similar."""

    def test_returns_matches_above_threshold(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["id-1"],
            "distances": [0.2],  # similarity = 0.8
            "metadatas": [
                {
                    "error_type": "ValueError",
                    "error_message": "bad value",
                    "tool_name": None,
                    "session_id": "s1",
                    "fix_applied": "handle edge case",
                    "occurrence_count": 3,
                }
            ],
        }
        matches = fm.search_similar(make_error_event())
        assert len(matches) == 1
        assert isinstance(matches[0], SimilarFailureMatch)
        assert matches[0].failure_id == "id-1"
        assert matches[0].similarity_score == pytest.approx(0.8)
        assert matches[0].fix_applied == "handle edge case"
        assert matches[0].occurrence_count == 3

    def test_filters_matches_below_threshold(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["id-1"],
            "distances": [0.7],  # similarity = 0.3, below default 0.5
            "metadatas": [{"error_type": "ValueError", "error_message": "bad"}],
        }
        assert fm.search_similar(make_error_event()) == []

    def test_returns_empty_on_encode_error(self):
        fm, embedding_model, _ = make_failure_memory()
        embedding_model.encode.side_effect = Exception("broken")
        assert fm.search_similar(make_error_event()) == []

    def test_sorts_by_similarity_descending(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["id-1", "id-2"],
            "distances": [0.3, 0.1],  # similarities: 0.7, 0.9
            "metadatas": [
                {"error_type": "A", "error_message": "a", "tool_name": None, "session_id": None, "fix_applied": None, "occurrence_count": 1},
                {"error_type": "B", "error_message": "b", "tool_name": None, "session_id": None, "fix_applied": None, "occurrence_count": 1},
            ],
        }
        matches = fm.search_similar(make_error_event())
        assert len(matches) == 2
        assert matches[0].similarity_score > matches[1].similarity_score

    def test_custom_threshold(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["id-1"],
            "distances": [0.3],  # similarity = 0.7
            "metadatas": [
                {"error_type": "E", "error_message": "msg", "tool_name": None, "session_id": None, "fix_applied": None, "occurrence_count": 1}
            ],
        }
        assert fm.search_similar(make_error_event(), threshold=0.8) == []
        assert len(fm.search_similar(make_error_event(), threshold=0.6)) == 1

    def test_skips_none_metadata(self):
        fm, _, vector_db = make_failure_memory()
        vector_db.query.return_value = {
            "ids": ["id-1"],
            "distances": [0.1],  # similarity = 0.9
            "metadatas": [None],
        }
        assert fm.search_similar(make_error_event()) == []


class TestRememberSessionFailures:
    """Tests for FailureMemory.remember_session_failures."""

    def test_returns_false_for_empty_events(self):
        fm, _, _ = make_failure_memory()
        assert fm.remember_session_failures({"events": []}) is False

    def test_returns_false_when_no_error_events(self):
        fm, _, _ = make_failure_memory()
        event = MagicMock()
        event.event_type.name = "TOOL_CALL"
        assert fm.remember_session_failures({"events": [event]}) is False

    def test_processes_error_events_and_returns_true(self):
        fm, _, vector_db = make_failure_memory()
        error_event = MagicMock()
        error_event.event_type.name = "ERROR"
        error_event.session_id = "s1"
        error_event.data = {"error_type": "RuntimeError", "error_message": "crash"}
        result = fm.remember_session_failures({"events": [error_event]})
        assert result is True
        vector_db.add.assert_called_once()

    def test_processes_multiple_error_events(self):
        fm, _, vector_db = make_failure_memory()
        events = []
        for i in range(3):
            e = MagicMock()
            e.event_type.name = "ERROR"
            e.session_id = "s1"
            e.data = {"error_type": "E", "error_message": f"error {i}"}
            events.append(e)
        fm.remember_session_failures({"events": events})
        assert vector_db.add.call_count == 3
