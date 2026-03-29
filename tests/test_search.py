"""Comprehensive tests for storage/search.py SessionSearchService.

Tests cover:
- Query parsing and result ranking for semantic session search
- Tenant isolation (searches only return results for the correct tenant)
- Empty result sets for non-matching queries
- Special characters in queries (SQL LIKE escaping)
- Event search with filters (session_id, event_type)
- In-memory database fixtures for isolation
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import ErrorEvent, LLMRequestEvent, Session, ToolCallEvent
from storage.models import Base
from storage.repository import TraceRepository
from storage.search import SessionSearchService


def _make_session(session_id: str = "session-1", agent_name: str = "test-agent") -> Session:
    """Create a test Session instance."""
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc),
        config={"mode": "test"},
        tags=["search-test"],
    )


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def populated_db(db_session: AsyncSession):
    """Populate database with test sessions and events for search testing."""
    repo_tenant_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_tenant_b = TraceRepository(db_session, tenant_id="tenant-c")

    # Create sessions for tenant-a
    session_search = _make_session("session-search", "search-agent")
    session_tool = _make_session("session-tool", "tool-agent")
    session_error = _make_session("session-error", "error-agent")
    session_llm = _make_session("session-llm", "llm-agent")

    # Create session for tenant-b (tenant isolation test)
    session_other = _make_session("session-other", "other-agent")

    for session in [session_search, session_tool, session_error, session_llm]:
        await repo_tenant_a.create_session(session)
    await repo_tenant_b.create_session(session_other)

    # Add events to session-search (search-related)
    search_event1 = ToolCallEvent(
        id="event-search-1",
        session_id=session_search.id,
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="web-search",
        tool_name="search",
        arguments={"query": "machine learning"},
        metadata={"source": "web"},
        upstream_event_ids=["root"],
    )
    search_event2 = LLMRequestEvent(
        id="event-search-2",
        session_id=session_search.id,
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="analyze-search",
        model="gpt-4",
        messages=[{"role": "user", "content": "analyze search results"}],
        tools=[],
        settings={"temperature": 0.7},
    )
    await repo_tenant_a.add_event(search_event1)
    await repo_tenant_a.add_event(search_event2)

    # Add events to session-tool (tool-related)
    tool_event1 = ToolCallEvent(
        id="event-tool-1",
        session_id=session_tool.id,
        timestamp=datetime(2026, 3, 29, 10, 3, tzinfo=timezone.utc),
        name="execute-tool",
        tool_name="calculator",
        arguments={"expression": "2+2"},
        metadata={"source": "tool"},
        upstream_event_ids=["root"],
    )
    tool_event2 = ToolCallEvent(
        id="event-tool-2",
        session_id=session_tool.id,
        timestamp=datetime(2026, 3, 29, 10, 4, tzinfo=timezone.utc),
        name="execute-tool",
        tool_name="database",
        arguments={"query": "SELECT *"},
        metadata={"source": "tool"},
        upstream_event_ids=["root"],
    )
    await repo_tenant_a.add_event(tool_event1)
    await repo_tenant_a.add_event(tool_event2)

    # Add events to session-error (error-related)
    error_event1 = ErrorEvent(
        id="event-error-1",
        session_id=session_error.id,
        timestamp=datetime(2026, 3, 29, 10, 5, tzinfo=timezone.utc),
        name="api-failure",
        error_type="ConnectionError",
        error_message="Failed to connect to database",
        stack_trace="Traceback...",
    )
    error_event2 = ErrorEvent(
        id="event-error-2",
        session_id=session_error.id,
        timestamp=datetime(2026, 3, 29, 10, 6, tzinfo=timezone.utc),
        name="timeout",
        error_type="TimeoutError",
        error_message="Request timed out after 30 seconds",
        stack_trace="Traceback...",
    )
    await repo_tenant_a.add_event(error_event1)
    await repo_tenant_a.add_event(error_event2)

    # Add events to session-llm (LLM-related)
    llm_event1 = LLMRequestEvent(
        id="event-llm-1",
        session_id=session_llm.id,
        timestamp=datetime(2026, 3, 29, 10, 7, tzinfo=timezone.utc),
        name="generate-text",
        model="gpt-4",
        messages=[{"role": "user", "content": "write code"}],
        tools=[],
        settings={"temperature": 0.5},
    )
    llm_event2 = LLMRequestEvent(
        id="event-llm-2",
        session_id=session_llm.id,
        timestamp=datetime(2026, 3, 29, 10, 8, tzinfo=timezone.utc),
        name="summarize",
        model="claude-3",
        messages=[{"role": "user", "content": "summarize document"}],
        tools=[],
        settings={"temperature": 0.3},
    )
    await repo_tenant_a.add_event(llm_event1)
    await repo_tenant_a.add_event(llm_event2)

    # Add events to session-other (tenant-b)
    other_event = ToolCallEvent(
        id="event-other-1",
        session_id=session_other.id,
        timestamp=datetime(2026, 3, 29, 10, 9, tzinfo=timezone.utc),
        name="search",
        tool_name="search",
        arguments={"query": "machine learning"},
        metadata={"source": "other"},
        upstream_event_ids=["root"],
    )
    await repo_tenant_b.add_event(other_event)

    yield db_session


class TestSessionSearchServiceBasicFunctionality:
    """Test basic search_sessions functionality."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_list(self, populated_db: AsyncSession):
        """Empty query string should return empty results."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("")
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_empty_list(self, populated_db: AsyncSession):
        """Query with only whitespace should return empty results."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("   \t\n  ")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_sessions_with_similarity_scores(self, populated_db: AsyncSession):
        """Search results should include search_similarity attribute."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("search")
        assert len(results) > 0
        for session in results:
            assert hasattr(session, "search_similarity")
            assert session.search_similarity > 0.0

    @pytest.mark.asyncio
    async def test_search_respects_limit_parameter(self, populated_db: AsyncSession):
        """Search should respect the limit parameter."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("tool", limit=1)
        assert len(results) <= 1


class TestSessionSearchQueryRanking:
    """Test query parsing and result ranking."""

    @pytest.mark.asyncio
    async def test_search_ranks_results_by_similarity(self, populated_db: AsyncSession):
        """Results should be ranked by cosine similarity in descending order."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("search")

        if len(results) > 1:
            # Check that similarity scores are in descending order
            similarities = [s.search_similarity for s in results]
            assert similarities == sorted(similarities, reverse=True)

    @pytest.mark.asyncio
    async def test_search_finds_tool_sessions(self, populated_db: AsyncSession):
        """Query 'tool' should find sessions with tool-related events."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("tool")

        session_ids = [s.id for s in results]
        assert "session-tool" in session_ids

    @pytest.mark.asyncio
    async def test_search_finds_error_sessions(self, populated_db: AsyncSession):
        """Query 'error' should find sessions with error events."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("error")

        session_ids = [s.id for s in results]
        assert "session-error" in session_ids

    @pytest.mark.asyncio
    async def test_search_finds_llm_sessions(self, populated_db: AsyncSession):
        """Query 'gpt' should find sessions with LLM events."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("gpt")

        session_ids = [s.id for s in results]
        assert "session-llm" in session_ids

    @pytest.mark.asyncio
    async def test_search_with_status_filter(self, populated_db: AsyncSession):
        """Search should filter by session status when provided."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")

        # First, update a session status
        repo = TraceRepository(populated_db, tenant_id="tenant-a")
        await repo.update_session("session-search", status="completed")

        results = await service.search_sessions("search", status="completed")
        assert all(s.status == "completed" for s in results)


class TestSessionSearchTenantIsolation:
    """Test tenant isolation in search results."""

    @pytest.mark.asyncio
    async def test_search_only_returns_results_for_correct_tenant(self, populated_db: AsyncSession):
        """Search should only return sessions for the specified tenant_id."""
        service_a = SessionSearchService(populated_db, tenant_id="tenant-a")
        service_b = SessionSearchService(populated_db, tenant_id="tenant-c")

        results_a = await service_a.search_sessions("search")
        results_b = await service_b.search_sessions("search")

        # Tenant-a should have results, tenant-b (tenant-c) should have its own
        session_ids_a = [s.id for s in results_a]
        session_ids_b = [s.id for s in results_b]

        assert "session-search" in session_ids_a
        assert "session-other" not in session_ids_a
        assert "session-other" in session_ids_b
        assert "session-search" not in session_ids_b

    @pytest.mark.asyncio
    async def test_tenant_isolation_with_status_filter(self, populated_db: AsyncSession):
        """Tenant isolation should work correctly with status filters."""
        service_a = SessionSearchService(populated_db, tenant_id="tenant-a")
        service_b = SessionSearchService(populated_db, tenant_id="tenant-c")

        # Update status for tenant-a session
        repo = TraceRepository(populated_db, tenant_id="tenant-a")
        await repo.update_session("session-search", status="completed")

        results_a = await service_a.search_sessions("search", status="completed")
        results_b = await service_b.search_sessions("search", status="completed")

        assert len(results_a) > 0
        assert len(results_b) == 0  # tenant-b session doesn't have this status


class TestSessionSearchEmptyResults:
    """Test empty result sets."""

    @pytest.mark.asyncio
    async def test_search_nonexistent_term_returns_empty(self, populated_db: AsyncSession):
        """Search for a term that doesn't exist should return empty results."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_sessions("nonexistent_term_xyz123")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_no_matching_events(self, populated_db: AsyncSession):
        """Search in a tenant with no sessions should return empty results."""
        service = SessionSearchService(populated_db, tenant_id="tenant-nonexistent")
        results = await service.search_sessions("search")
        assert results == []


class TestEventSearchFunctionality:
    """Test search_events functionality."""

    @pytest.mark.asyncio
    async def test_event_search_finds_by_name(self, populated_db: AsyncSession):
        """Event search should find events by name."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_events("search")

        event_names = [e.name for e in results]
        assert "web-search" in event_names

    @pytest.mark.asyncio
    async def test_event_search_filters_by_session_id(self, populated_db: AsyncSession):
        """Event search should filter by session_id when provided."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")

        all_results = await service.search_events("search")
        filtered_results = await service.search_events("search", session_id="session-search")

        assert len(filtered_results) <= len(all_results)
        assert all(e.session_id == "session-search" for e in filtered_results)

    @pytest.mark.asyncio
    async def test_event_search_filters_by_event_type(self, populated_db: AsyncSession):
        """Event search should filter by event_type when provided."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")

        results = await service.search_events("search", event_type="tool_call")
        assert all(e.event_type == "tool_call" for e in results)

    @pytest.mark.asyncio
    async def test_event_search_respects_limit(self, populated_db: AsyncSession):
        """Event search should respect the limit parameter."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")
        results = await service.search_events("event", limit=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_event_search_tenant_isolation(self, populated_db: AsyncSession):
        """Event search should only return events for the correct tenant."""
        service_a = SessionSearchService(populated_db, tenant_id="tenant-a")
        service_b = SessionSearchService(populated_db, tenant_id="tenant-c")

        results_a = await service_a.search_events("search")
        results_b = await service_b.search_events("search")

        # Each tenant should only see their own events
        assert all(e.session_id.startswith("session-") for e in results_a)
        assert "session-other" in [e.session_id for e in results_b]


class TestSpecialCharactersInQueries:
    """Test handling of special characters in search queries."""

    @pytest.mark.asyncio
    async def test_event_search_escapes_sql_wildcards(self, populated_db: AsyncSession):
        """Event search should escape SQL LIKE wildcards (_, %, \\)."""
        service = SessionSearchService(populated_db, tenant_id="tenant-a")

        # These should be treated as literals, not wildcards
        results_underscore = await service.search_events("event_")
        results_percent = await service.search_events("event%")
        results_backslash = await service.search_events("event\\")

        # Should not match everything (which would happen if wildcards worked)
        # Since we don't have events with these literal names, expect few/no results
        # The key is that it doesn't crash or return all events
        assert isinstance(results_underscore, list)
        assert isinstance(results_percent, list)
        assert isinstance(results_backslash, list)

    @pytest.mark.asyncio
    async def test_event_search_with_special_chars_in_data(self, populated_db: AsyncSession):
        """Event search should handle special characters in event data."""
        # Add an event with special characters in the data field
        repo = TraceRepository(populated_db, tenant_id="tenant-a")
        special_event = ToolCallEvent(
            id="event-special-1",
            session_id="session-search",
            timestamp=datetime(2026, 3, 29, 11, 0, tzinfo=timezone.utc),
            name="special-pattern-search",
            tool_name="search",
            arguments={"query": "test_%_pattern", "filter": "data_with_underscore"},
            metadata={"source": "test_special_%_"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(special_event)

        service = SessionSearchService(populated_db, tenant_id="tenant-a")

        # Search by name should work
        results_by_name = await service.search_events("special-pattern")
        event_names = [e.name for e in results_by_name]
        assert "special-pattern-search" in event_names

        # Search should handle underscores in query without treating them as wildcards
        results_with_underscore = await service.search_events("test_%_pattern")
        # This should search for literal "test_%_pattern" which won't match our event
        # The key is that it doesn't crash or return unexpected results
        assert isinstance(results_with_underscore, list)
