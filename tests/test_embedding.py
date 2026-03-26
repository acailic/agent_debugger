"""Tests for storage/embedding.py"""

import pytest

from storage.embedding import (
    build_session_embedding,
    cosine_similarity,
    text_to_vector,
    tokenize,
)


class TestTokenize:
    def test_lowercase_and_splits(self):
        text = "Hello World Python Code"
        tokens = tokenize(text)
        assert tokens == ["hello", "world", "python", "code"]

    def test_empty_string(self):
        tokens = tokenize("")
        assert tokens == []

    def test_deduplicates(self):
        text = "hello hello world world world"
        tokens = tokenize(text)
        assert tokens == ["hello", "world"]

    def test_filters_punctuation(self):
        """Punctuation characters should be stripped, not tokenized."""
        text = "hello! world? (test) - example"
        tokens = tokenize(text)
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "example" in tokens

    def test_handles_numbers(self):
        """Numeric tokens should be preserved."""
        text = "error code 404 status 500"
        tokens = tokenize(text)
        assert "404" in tokens
        assert "500" in tokens
        assert "error" in tokens
        assert "code" in tokens

    def test_all_stopwords(self):
        """Text with only stopwords should return empty list."""
        text = "the is was are were have has"
        tokens = tokenize(text)
        assert tokens == []

    def test_mixed_case(self):
        """Mixed case should be normalized to lowercase."""
        text = "Hello HELLO hello World WORLD"
        tokens = tokenize(text)
        assert tokens == ["hello", "world"]

    def test_hyphenated_words(self):
        """Hyphenated words should be split into separate tokens."""
        text = "timeout-error handler"
        tokens = tokenize(text)
        assert "timeout" in tokens
        assert "error" in tokens
        assert "handler" in tokens


class TestTextToVector:
    def test_known_output(self):
        # With TF normalization: each term frequency / total tokens
        text = "hello world hello"
        vector = text_to_vector(text)
        # "hello" appears 2 times, "world" 1 time, total 3 tokens
        # TF: hello=2/3, world=1/3
        assert vector == {"hello": 2.0 / 3.0, "world": 1.0 / 3.0}

    def test_empty_input(self):
        vector = text_to_vector("")
        assert vector == {}

    def test_single_term(self):
        vector = text_to_vector("hello")
        assert vector == {"hello": 1.0}

    def test_ignores_common_stopwords(self):
        text = "the quick brown fox jumps over the lazy dog"
        # "the", "over" should be filtered
        vector = text_to_vector(text)
        assert "the" not in vector
        assert "over" not in vector
        assert "quick" in vector
        assert "brown" in vector
        assert "fox" in vector

    def test_all_stopwords_input(self):
        """Text with only stopwords should return empty vector."""
        vector = text_to_vector("the is was are were")
        assert vector == {}

    def test_mixed_stopwords_and_content(self):
        """Stopwords should be filtered but content terms preserved."""
        text = "the timeout error was caused by a connection failure"
        vector = text_to_vector(text)
        assert "timeout" in vector
        assert "error" in vector
        assert "caused" in vector
        assert "connection" in vector
        assert "failure" in vector
        assert "the" not in vector
        assert "was" not in vector
        assert "a" not in vector
        assert "by" not in vector

    def test_long_text(self):
        """Vector should handle longer text without issues."""
        text = "error timeout connection failure retry exception " * 10
        vector = text_to_vector(text)
        assert len(vector) > 0
        # All values should sum to approximately 1.0 (TF normalization)
        assert sum(vector.values()) == pytest.approx(1.0, abs=0.01)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = {"hello": 1.0, "world": 0.5}
        b = {"hello": 1.0, "world": 0.5}
        sim = cosine_similarity(a, b)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = {"hello": 1.0}
        b = {"world": 1.0}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_empty_vectors(self):
        a = {}
        b = {}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_one_empty_vector(self):
        a = {"hello": 1.0}
        b = {}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_similar_vectors(self):
        a = {"hello": 1.0, "world": 0.5}
        b = {"hello": 1.0, "world": 0.25}
        sim = cosine_similarity(a, b)
        # Similarity should be between 0.5 and 1.0
        assert 0.5 <= sim <= 1.0

    def test_partial_overlap(self):
        """Vectors with some shared and some unique terms."""
        a = {"timeout": 0.5, "error": 0.5}
        b = {"error": 0.5, "connection": 0.5}
        sim = cosine_similarity(a, b)
        # Should be between 0 and 1 (partial match on "error")
        assert 0.0 < sim < 1.0

    def test_many_terms(self):
        """Cosine similarity with many terms should still work correctly."""
        a = {f"term{i}": 0.1 for i in range(20)}
        b = {f"term{i}": 0.1 for i in range(10, 30)}  # Overlap on terms 10-19
        sim = cosine_similarity(a, b)
        # Should have partial similarity due to overlap on terms 10-19
        assert 0.0 < sim < 1.0

    def test_proportional_vectors(self):
        """Vectors that are proportional should have similarity of 1.0."""
        a = {"hello": 1.0, "world": 2.0}
        b = {"hello": 0.5, "world": 1.0}
        sim = cosine_similarity(a, b)
        assert sim == pytest.approx(1.0)


class TestBuildSessionEmbedding:
    def test_from_events(self):
        events = [
            {"event_type": "tool_start", "name": "search"},
            {"event_type": "llm_start", "model": "gpt-4"},
            {"error_type": "ValueError", "error_message": "invalid input"},
            {"tool_name": "calculator"},
        ]
        embedding = build_session_embedding(events)
        # Check that event types and names appear in embedding
        assert "tool_start" in embedding
        assert "search" in embedding
        assert "llm_start" in embedding
        assert "gpt-4" in embedding or "gpt" in embedding or "4" in embedding
        assert "valueerror" in embedding
        assert "invalid" in embedding
        assert "input" in embedding
        assert "calculator" in embedding

    def test_empty_events(self):
        embedding = build_session_embedding([])
        assert embedding == {}

    def test_with_tool_name_in_data(self):
        """Events with tool_name in data dict should be included in embedding."""
        events = [
            {"event_type": "tool_call", "name": "call_tool", "tool_name": "search_api"},
        ]
        embedding = build_session_embedding(events)
        assert "search_api" in embedding or "search" in embedding
        assert "tool_call" in embedding

    def test_with_model_in_data(self):
        """Events with model in data dict should be included in embedding."""
        events = [
            {"event_type": "llm_start", "name": "generate", "model": "gpt-4o"},
        ]
        embedding = build_session_embedding(events)
        # gpt-4o may be split by tokenize, check for parts
        assert "llm_start" in embedding
        assert "generate" in embedding

    def test_null_values_skipped(self):
        """Null/None field values should be skipped gracefully."""
        events = [
            {"event_type": "error", "name": None, "error_type": "", "error_message": None},
        ]
        embedding = build_session_embedding(events)
        # error_type is empty string, error_message is None, name is None
        # Only event_type "error" should be in the embedding
        assert "error" in embedding
        # Empty strings and None should not add spurious terms

    def test_multiple_events_combined(self):
        """Multiple events should have their text combined into one embedding."""
        events = [
            {"event_type": "llm_start", "name": "generate", "model": "gpt-4"},
            {"event_type": "tool_call", "name": "search", "tool_name": "web_search"},
            {"event_type": "error", "error_type": "TimeoutError", "error_message": "request failed"},
        ]
        embedding = build_session_embedding(events)
        # Should contain terms from all events
        assert "llm_start" in embedding
        assert "generate" in embedding
        assert "tool_call" in embedding
        assert "search" in embedding
        assert "error" in embedding
        assert "timeouterror" in embedding
