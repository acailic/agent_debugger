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
