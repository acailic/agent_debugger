"""Shared fixtures for No-Brainer Features tests.

Provides factory fixtures for creating events and sessions, plus mock fixtures
for external dependencies (embedding models, vector databases, LLM clients).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Event Factory Fixtures
# =============================================================================

@pytest.fixture
def make_error_event():
    """Factory for creating ErrorEvent instances with sensible defaults."""
    def _make(
        id: str,
        error_type: str = "ValueError",
        message: str = "Test error",
        **kwargs,
    ):
        from agent_debugger_sdk.core.events import ErrorEvent

        return ErrorEvent(
            id=id,
            session_id=kwargs.get("session_id", "test-session"),
            error_type=error_type,
            error_message=message,
            timestamp=kwargs.get("timestamp", datetime.now(timezone.utc)),
            parent_id=kwargs.get("parent_id"),
            stack_trace=kwargs.get("stack_trace"),
        )

    return _make


@pytest.fixture
def make_decision_event():
    """Factory for creating DecisionEvent instances with sensible defaults."""
    def _make(
        id: str,
        action: str = "proceed",
        confidence: float = 0.9,
        **kwargs,
    ):
        from agent_debugger_sdk.core.events import DecisionEvent

        return DecisionEvent(
            id=id,
            session_id=kwargs.get("session_id", "test-session"),
            chosen_action=action,
            confidence=confidence,
            evidence=kwargs.get("evidence", []),
            reasoning=kwargs.get("reasoning", ""),
            alternatives=kwargs.get("alternatives", []),
            parent_id=kwargs.get("parent_id"),
            evidence_event_ids=kwargs.get("evidence_event_ids", []),
        )

    return _make


@pytest.fixture
def make_session():
    """Factory for creating Session instances with a list of events."""
    def _make(events, session_id: str = "test-session", **kwargs):
        from agent_debugger_sdk.core.events import Session

        return Session(
            id=session_id,
            agent_name=kwargs.get("agent_name", "test-agent"),
            framework=kwargs.get("framework", "test"),
            started_at=kwargs.get("started_at", datetime.now(timezone.utc)),
            ended_at=kwargs.get("ended_at"),
            status=kwargs.get("status"),
            total_tokens=kwargs.get("total_tokens", 0),
            total_cost_usd=kwargs.get("total_cost_usd", 0.0),
            tool_calls=kwargs.get("tool_calls", 0),
            llm_calls=kwargs.get("llm_calls", 0),
            errors=kwargs.get("errors", 0),
            config=kwargs.get("config", {}),
            tags=kwargs.get("tags", []),
        )

    return _make


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_embedding_model():
    """Mock sentence-transformers.SentenceTransformer.

    Returns a MagicMock with encode() returning a dummy 384-dimensional embedding.
    """
    with patch("sentence_transformers.SentenceTransformer") as mock:
        instance = MagicMock()
        instance.encode.return_value = [0.1] * 384
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_vector_db():
    """Mock chromadb.Client.

    Returns a MagicMock with query() returning dummy search results.
    """
    with patch("chromadb.Client") as mock:
        instance = MagicMock()
        instance.query.return_value = {
            "ids": [["id1"]],
            "distances": [[0.1]],
        }
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_llm_client():
    """Mock LLM API client.

    Returns an AsyncMock with generate() returning a test response.
    """
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value="Test LLM response")
    return mock
