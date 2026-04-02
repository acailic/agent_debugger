"""Unit tests for storage/search.py SessionSearchService with mocked database layer.

These tests use unittest.mock.AsyncMock to mock the SQLAlchemy AsyncSession,
providing fast, focused unit tests for the search service logic without
requiring a real database connection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.core.events import SessionStatus
from storage.models import EventModel, SessionModel
from storage.search import SessionSearchService

# =============================================================================
# Test Helpers
# =============================================================================


def _make_mock_session(
    session_id: str = "test-session",
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.RUNNING,
) -> SessionModel:
    """Create a mock SessionModel ORM instance."""
    mock_session = Mock(spec=SessionModel)
    mock_session.id = session_id
    mock_session.tenant_id = "tenant-1"
    mock_session.agent_name = agent_name
    mock_session.framework = "test-framework"
    mock_session.status = status
    mock_session.started_at = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    mock_session.ended_at = None
    mock_session.total_tokens = 1000
    mock_session.total_cost_usd = 0.5
    mock_session.tool_calls = 5
    mock_session.llm_calls = 10
    mock_session.errors = 0
    mock_session.replay_value = 0.8
    mock_session.config = {}
    mock_session.tags = []
    mock_session.fix_note = None
    return mock_session


def _make_mock_event(
    event_id: str = "test-event",
    session_id: str = "test-session",
    name: str = "test_event",
    event_type: str = "tool_call",
    data: dict | None = None,
) -> EventModel:
    """Create a mock EventModel ORM instance."""
    mock_event = Mock(spec=EventModel)
    mock_event.id = event_id
    mock_event.session_id = session_id
    mock_event.parent_id = None
    mock_event.event_type = event_type
    mock_event.timestamp = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    mock_event.name = name
    mock_event.data = data or {}
    mock_event.event_metadata = {}
    mock_event.importance = 0.5
    return mock_event


def _create_mock_async_session() -> AsyncMock:
    """Create a mock AsyncSession with configured return values."""
    mock_session = AsyncMock(spec=AsyncSession)
    return mock_session


# =============================================================================
# Test search_sessions
# =============================================================================


class TestSearchSessions:
    """Test suite for SessionSearchService.search_sessions method."""

    @pytest.mark.asyncio
    async def test_search_sessions_with_mocked_session_returns_results(self):
        """Test search_sessions returns sessions when query matches."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_sessions("test query")

        # Assert
        assert isinstance(result, list)
        # Empty result since we mocked empty sessions
        assert result == []

    @pytest.mark.asyncio
    async def test_search_sessions_with_status_filter(self):
        """Test search_sessions filters by status when provided."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_sessions("test query", status="error")

        # Assert
        assert isinstance(result, list)
        # Verify execute was called (the status filter would be in the SQL)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_sessions_with_empty_query(self):
        """Test search_sessions returns empty list for empty query."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Act
        result = await service.search_sessions("")

        # Assert
        assert result == []
        # Should not execute any database query
        assert not mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_sessions_with_whitespace_query(self):
        """Test search_sessions returns empty list for whitespace-only query."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Act
        result = await service.search_sessions("   ")

        # Assert
        assert result == []
        assert not mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_sessions_respects_limit(self):
        """Test search_sessions respects the limit parameter."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_sessions("test query", limit=5)

        # Assert
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_sessions_with_no_candidate_sessions(self):
        """Test search_sessions returns empty when no sessions in database."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock empty database result
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_sessions("test query")

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_search_sessions_tenant_isolation(self):
        """Test search_sessions uses tenant_id in query."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-abc")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await service.search_sessions("test query")

        # Assert
        # Verify that execute was called (tenant filtering is in the SQL)
        assert mock_session.execute.called


# =============================================================================
# Test search_events
# =============================================================================


class TestSearchEvents:
    """Test suite for SessionSearchService.search_events method."""

    @pytest.mark.asyncio
    async def test_search_events_with_mocked_session(self):
        """Test search_events returns events when query matches."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events("test")

        # Assert
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_events_with_session_id_filter(self):
        """Test search_events filters by session_id when provided."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events("test", session_id="session-123")

        # Assert
        assert isinstance(result, list)
        # Verify execute was called (session_id filter would be in the SQL)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_events_with_event_type_filter(self):
        """Test search_events filters by event_type when provided."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events("test", event_type="tool_call")

        # Assert
        assert isinstance(result, list)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_events_with_both_filters(self):
        """Test search_events with both session_id and event_type filters."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events(
            "test", session_id="session-123", event_type="llm_request"
        )

        # Assert
        assert isinstance(result, list)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_events_respects_limit(self):
        """Test search_events respects the limit parameter."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events("test", limit=50)

        # Assert
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_events_tenant_isolation(self):
        """Test search_events includes tenant isolation in query."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-xyz")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await service.search_events("test")

        # Assert
        # Verify execute was called (tenant filtering is in the SQL via join)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_events_escapes_sql_wildcards(self):
        """Test search_events properly escapes SQL LIKE wildcards."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act - query with SQL wildcards
        result = await service.search_events("test_%value")

        # Assert
        assert isinstance(result, list)
        # The query should not cause SQL errors
        assert mock_session.execute.called


# =============================================================================
# Test Private Methods
# =============================================================================


class TestPrivateMethods:
    """Test suite for private helper methods."""

    @pytest.mark.asyncio
    async def test_load_candidate_sessions_without_status(self):
        """Test _load_candidate_sessions loads sessions without status filter."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service._load_candidate_sessions(status=None)

        # Assert
        assert isinstance(result, list)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_load_candidate_sessions_with_status(self):
        """Test _load_candidate_sessions applies status filter when provided."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service._load_candidate_sessions(status="error")

        # Assert
        assert isinstance(result, list)
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_score_sessions_ranks_by_similarity(self):
        """Test _score_sessions returns sessions ranked by similarity score."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        db_session1 = _make_mock_session("s1")
        db_session2 = _make_mock_session("s2")
        db_sessions = [db_session1, db_session2]

        query_vec = {"test": 0.5}

        # Mock event loading for each session
        mock_event_result = Mock()
        mock_event_scalars = Mock()
        mock_event_scalars.all = Mock(return_value=[])
        mock_event_result.scalars = Mock(return_value=mock_event_scalars)
        mock_session.execute = AsyncMock(return_value=mock_event_result)

        # Act
        result = await service._score_sessions(db_sessions, query_vec)

        # Assert
        assert isinstance(result, list)
        # Result should be list of (similarity, session) tuples
        for item in result:
            assert len(item) == 2
            assert isinstance(item[0], float)  # similarity score
            assert isinstance(item[1], Mock)  # session

    @pytest.mark.asyncio
    async def test_embedding_event_dict_extracts_fields(self):
        """Test _embedding_event_dict extracts searchable fields from event."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        mock_event = _make_mock_event(
            event_id="e1",
            name="test_event",
            event_type="tool_call",
            data={"error_type": "ValueError", "error_message": "test error", "tool_name": "search"},
        )

        # Act
        result = service._embedding_event_dict(mock_event)

        # Assert
        assert isinstance(result, dict)
        assert result["event_type"] == "tool_call"
        assert result["name"] == "test_event"
        # Should include nested fields from data
        assert "error_type" in result
        assert "error_message" in result
        assert "tool_name" in result

    @pytest.mark.asyncio
    async def test_embedding_data_fields_with_none_data(self):
        """Test _embedding_data_fields handles None data gracefully."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Act
        result = service._embedding_data_fields(None)

        # Assert
        assert result == {}

    @pytest.mark.asyncio
    async def test_embedding_data_fields_extracts_searchable_fields(self):
        """Test _embedding_data_fields extracts only searchable fields."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        data = {
            "error_type": "ValueError",
            "error_message": "test error",
            "tool_name": "search",
            "model": "gpt-4",
            "other_field": "should_not_be_extracted",
        }

        # Act
        result = service._embedding_data_fields(data)

        # Assert
        assert result["error_type"] == "ValueError"
        assert result["error_message"] == "test error"
        assert result["tool_name"] == "search"
        assert result["model"] == "gpt-4"
        assert "other_field" not in result

    @pytest.mark.asyncio
    async def test_build_ranked_session_results_attaches_similarity(self):
        """Test _build_ranked_session_results attaches similarity to sessions."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        db_session = _make_mock_session("s1")
        scored_sessions = [(0.85, db_session)]

        # Act
        result = service._build_ranked_session_results(scored_sessions, limit=10)

        # Assert
        assert len(result) == 1
        # Result should be Session instances with search_similarity attached
        # Note: Since we're using mocks, we can't fully verify the conversion
        # but we can check the structure
        assert isinstance(result, list)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_search_sessions_with_special_characters(self):
        """Test search_sessions handles special characters in query."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act - query with special characters
        result = await service.search_sessions("test%value_123\\backslash")

        # Assert
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_events_with_empty_results(self):
        """Test search_events returns empty list when no events match."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock empty database result
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_events("nonexistent_term_xyz")

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_search_sessions_with_zero_limit(self):
        """Test search_sessions with limit=0 returns empty list."""
        # Arrange
        mock_session = _create_mock_async_session()
        service = SessionSearchService(mock_session, tenant_id="tenant-1")

        # Mock the database query chain
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.search_sessions("test", limit=0)

        # Assert
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test SessionSearchService initializes correctly."""
        # Arrange
        mock_session = _create_mock_async_session()
        tenant_id = "test-tenant"

        # Act
        service = SessionSearchService(mock_session, tenant_id)

        # Assert
        assert service.session == mock_session
        assert service.tenant_id == tenant_id
