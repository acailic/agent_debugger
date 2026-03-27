"""Bag-of-words text embedding utility with cosine similarity for session search."""

import re
from typing import Any

# Common English stopwords to filter
STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "was",
    "are",
    "were",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "and",
    "but",
    "or",
    "if",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "he",
    "she",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "our",
    "their",
    "what",
    "which",
    "who",
    "whom",
}


def tokenize(text: str) -> list[str]:
    """
    Split text into lowercase tokens, filter stopwords, deduplicate.

    Args:
        text: Input text to tokenize

    Returns:
        List of unique, lowercase, non-stopword tokens
    """
    if not text:
        return []

    # Split on whitespace and punctuation-like characters
    # Simple approach: split on non-alphanumeric boundaries
    words = re.findall(r"\w+", text.lower())

    # Filter stopwords and deduplicate
    seen = set()
    tokens = []
    for word in words:
        if word not in STOPWORDS and word not in seen:
            seen.add(word)
            tokens.append(word)

    return tokens


def text_to_vector(text: str) -> dict[str, float]:
    """
    Convert text to bag-of-words vector with TF normalization.

    Args:
        text: Input text

    Returns:
        Dictionary mapping terms to their term frequency (normalized by total token count)
    """
    tokens = tokenize(text)

    if not tokens:
        return {}

    # Count token occurrences (even though tokenize deduplicates, we need counts)
    # So we tokenize again without deduplication for counting
    words = re.findall(r"\w+", text.lower())
    words = [w for w in words if w not in STOPWORDS]

    if not words:
        return {}

    # Calculate term frequencies
    total = len(words)
    vector = {}
    for word in words:
        if word not in vector:
            vector[word] = 1.0 / total
        else:
            vector[word] += 1.0 / total

    return vector


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """
    Calculate cosine similarity between two sparse vectors.

    Args:
        a: First sparse vector (term -> weight)
        b: Second sparse vector (term -> weight)

    Returns:
        Cosine similarity between 0.0 and 1.0
    """
    if not a or not b:
        return 0.0

    # Get all unique terms
    all_terms = set(a.keys()) | set(b.keys())

    if not all_terms:
        return 0.0

    # Calculate dot product and magnitudes
    dot_product = 0.0
    magnitude_a = 0.0
    magnitude_b = 0.0

    for term in all_terms:
        val_a = a.get(term, 0.0)
        val_b = b.get(term, 0.0)

        dot_product += val_a * val_b
        magnitude_a += val_a * val_a
        magnitude_b += val_b * val_b

    magnitude_a = magnitude_a**0.5
    magnitude_b = magnitude_b**0.5

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def build_session_embedding(events: list[dict[str, Any]]) -> dict[str, float]:
    """
    Build embedding from event dicts for session search.

    Concatenates event_type, name, error_type, error_message, tool_name, model
    from each event into a single text representation.

    Args:
        events: List of event dictionaries

    Returns:
        Bag-of-words vector representing the session
    """
    if not events:
        return {}

    # Extract relevant fields from events
    text_parts = []
    for event in events:
        for field in ["event_type", "name", "error_type", "error_message", "tool_name", "model"]:
            if field in event and event[field]:
                text_parts.append(str(event[field]))

    # Combine all text parts
    combined_text = " ".join(text_parts)

    return text_to_vector(combined_text)
