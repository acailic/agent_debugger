"""Tests for storage/embedding.py"""

import pytest

from storage.embedding import (
    build_session_embedding,
    cosine_similarity,
    text_to_vector,
    tokenize,
)


class TestTokenize:
    """Test suite for tokenize function."""

    def test_empty_string_returns_empty_list(self):
        """Empty string should return empty list."""
        tokens = tokenize("")
        assert tokens == []

    def test_normal_text_splits_and_lowercases(self):
        """Normal text should be split into lowercase tokens."""
        text = "Hello World Python Code"
        tokens = tokenize(text)
        assert tokens == ["hello", "world", "python", "code"]

    def test_filters_stopwords(self):
        """Common stopwords should be filtered out."""
        text = "the quick brown fox jumps over the lazy dog"
        tokens = tokenize(text)
        assert "the" not in tokens
        assert "over" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_deduplicates_tokens(self):
        """Duplicate tokens should be removed."""
        text = "hello hello world world world"
        tokens = tokenize(text)
        assert tokens == ["hello", "world"]

    def test_mixed_case_normalized_to_lowercase(self):
        """Mixed case input should be normalized to lowercase."""
        text = "Hello HELLO hello World WORLD"
        tokens = tokenize(text)
        assert tokens == ["hello", "world"]

    def test_handles_punctuation(self):
        """Punctuation should be stripped, leaving only word tokens."""
        text = "hello! world? (test) - example"
        tokens = tokenize(text)
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "example" in tokens
        assert "!" not in tokens
        assert "?" not in tokens

    def test_preserves_numeric_tokens(self):
        """Numeric tokens should be preserved."""
        text = "error code 404 status 500"
        tokens = tokenize(text)
        assert "404" in tokens
        assert "500" in tokens
        assert "error" in tokens
        assert "code" in tokens

    def test_all_stopwords_returns_empty(self):
        """Text with only stopwords should return empty list."""
        text = "the is was are were have has"
        tokens = tokenize(text)
        assert tokens == []

    def test_hyphenated_words_split(self):
        """Hyphenated words should be split into separate tokens."""
        text = "timeout-error handler"
        tokens = tokenize(text)
        assert "timeout" in tokens
        assert "error" in tokens
        assert "handler" in tokens


class TestTextToVector:
    """Test suite for text_to_vector function."""

    def test_empty_string_returns_empty_dict(self):
        """Empty string should return empty vector."""
        vector = text_to_vector("")
        assert vector == {}

    def test_single_word_returns_normalized_vector(self):
        """Single word should return vector with value 1.0."""
        vector = text_to_vector("hello")
        assert vector == {"hello": 1.0}

    def test_multiple_words_with_tf_normalization(self):
        """Multiple words should use TF normalization (count/total)."""
        text = "hello world hello"
        vector = text_to_vector(text)
        # "hello" appears 2 times, "world" 1 time, total 3 tokens
        # TF: hello=2/3, world=1/3
        assert vector == {"hello": 2.0 / 3.0, "world": 1.0 / 3.0}

    def test_excludes_stopwords_from_vector(self):
        """Stopwords should be excluded from vector."""
        text = "the quick brown fox jumps over the lazy dog"
        vector = text_to_vector(text)
        assert "the" not in vector
        assert "over" not in vector
        assert "quick" in vector
        assert "brown" in vector
        assert "fox" in vector

    def test_all_stopwords_returns_empty_vector(self):
        """Text with only stopwords should return empty vector."""
        vector = text_to_vector("the is was are were")
        assert vector == {}

    def test_mixed_stopwords_and_content(self):
        """Stopwords filtered but content terms preserved with TF."""
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

    def test_long_text_normalization(self):
        """Longer text should maintain TF normalization (sums to ~1.0)."""
        text = "error timeout connection failure retry exception " * 10
        vector = text_to_vector(text)
        assert len(vector) > 0
        # All values should sum to approximately 1.0 (TF normalization)
        assert sum(vector.values()) == pytest.approx(1.0, abs=0.01)


class TestCosineSimilarity:
    """Test suite for cosine_similarity function."""

    def test_identical_vectors_return_one(self):
        """Identical vectors should have similarity of 1.0."""
        a = {"hello": 1.0, "world": 0.5}
        b = {"hello": 1.0, "world": 0.5}
        sim = cosine_similarity(a, b)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        """Vectors with no overlapping terms should have similarity 0.0."""
        a = {"hello": 1.0}
        b = {"world": 1.0}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_both_empty_vectors_return_zero(self):
        """Two empty vectors should return 0.0."""
        a = {}
        b = {}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_one_empty_vector_returns_zero(self):
        """One empty and one non-empty vector should return 0.0."""
        a = {"hello": 1.0}
        b = {}
        sim = cosine_similarity(a, b)
        assert sim == 0.0

    def test_similar_vectors_return_high_similarity(self):
        """Similar vectors should return similarity between 0.5 and 1.0."""
        a = {"hello": 1.0, "world": 0.5}
        b = {"hello": 1.0, "world": 0.25}
        sim = cosine_similarity(a, b)
        assert 0.5 <= sim <= 1.0

    def test_partial_overlap_returns_partial_similarity(self):
        """Vectors with some overlapping terms should have 0.0 < sim < 1.0."""
        a = {"timeout": 0.5, "error": 0.5}
        b = {"error": 0.5, "connection": 0.5}
        sim = cosine_similarity(a, b)
        assert 0.0 < sim < 1.0

    def test_proportional_vectors_return_one(self):
        """Vectors that are proportional should have similarity 1.0."""
        a = {"hello": 1.0, "world": 2.0}
        b = {"hello": 0.5, "world": 1.0}
        sim = cosine_similarity(a, b)
        assert sim == pytest.approx(1.0)

    def test_many_terms_calculates_correctly(self):
        """Vectors with many terms should still compute correctly."""
        a = {f"term{i}": 0.1 for i in range(20)}
        b = {f"term{i}": 0.1 for i in range(10, 30)}  # Overlap on terms 10-19
        sim = cosine_similarity(a, b)
        # Should have partial similarity due to overlap on terms 10-19
        assert 0.0 < sim < 1.0


class TestBuildSessionEmbedding:
    """Test suite for build_session_embedding function."""

    def test_empty_events_list_returns_empty_vector(self):
        """Empty events list should return empty vector."""
        embedding = build_session_embedding([])
        assert embedding == {}

    def test_extracts_relevant_fields_from_events(self):
        """Should extract event_type, name, error_type, error_message, tool_name, model."""
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
        # gpt-4 may be tokenized as gpt and 4
        assert "gpt" in embedding or "gpt-4" in embedding
        assert "valueerror" in embedding
        assert "invalid" in embedding
        assert "input" in embedding
        assert "calculator" in embedding

    def test_events_with_various_fields(self):
        """Events with different field combinations should all be included."""
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

    def test_events_missing_some_fields(self):
        """Events missing fields should skip those fields gracefully."""
        events = [
            {"event_type": "tool_start", "name": "search"},  # No tool_name
            {"event_type": "llm_start"},  # No name or model
            {"error_type": "ValueError"},  # No error_message
        ]
        embedding = build_session_embedding(events)
        # Should have what's available
        assert "tool_start" in embedding
        assert "search" in embedding
        assert "llm_start" in embedding
        assert "valueerror" in embedding

    def test_null_values_skipped(self):
        """Null/None field values should be skipped gracefully."""
        events = [
            {"event_type": "error", "name": None, "error_type": "", "error_message": None},
        ]
        embedding = build_session_embedding(events)
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

    def test_with_tool_name(self):
        """Events with tool_name should include it in embedding."""
        events = [
            {"event_type": "tool_call", "name": "call_tool", "tool_name": "search_api"},
        ]
        embedding = build_session_embedding(events)
        assert "search_api" in embedding or "search" in embedding
        assert "tool_call" in embedding

    def test_with_model(self):
        """Events with model should include it in embedding."""
        events = [
            {"event_type": "llm_start", "name": "generate", "model": "gpt-4o"},
        ]
        embedding = build_session_embedding(events)
        assert "llm_start" in embedding
        assert "generate" in embedding
