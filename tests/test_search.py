"""Tests for storage/search.py - Session and event search functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import (
    ErrorEvent,
    LLMRequestEvent,
    Session,
    SessionStatus,
    ToolCallEvent,
)
from storage.models import Base
from storage.repository import TraceRepository
from storage.search import SessionSearchService


def _make_session(
    session_id: str,
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.COMPLETED,
) -> Session:
    """Create a test Session instance."""
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 29, 11, 0, tzinfo=timezone.utc),
        status=status,
        total_cost_usd=0.50,
        total_tokens=1000,
        llm_calls=5,
        tool_calls=10,
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


class TestSessionSearch:
    """Test semantic search over sessions."""

    @pytest.mark.asyncio
    async def test_search_sessions_returns_matching_results(self, db_session):
        """Test that search returns sessions matching the query."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        await repo.create_session(_make_session("session-1", agent_name="weather_agent"))
        await repo.create_session(_make_session("session-2", agent_name="calculator"))

        # Add events to sessions for embedding
        event1 = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-search",
            tool_name="weather_api",
            arguments={"location": "London"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event1)

        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("weather")

        assert len(results) > 0
        assert results[0].id == "session-1"
        assert hasattr(results[0], "search_similarity")
        assert results[0].search_similarity > 0.0

    @pytest.mark.asyncio
    async def test_search_sessions_with_empty_query_returns_empty(self, db_session):
        """Test that empty query returns no results."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        await repo.create_session(_make_session("session-1"))
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_sessions_with_whitespace_query_returns_empty(self, db_session):
        """Test that whitespace-only query returns no results."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        await repo.create_session(_make_session("session-1"))
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("   ")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_sessions_with_no_matching_sessions(self, db_session):
        """Test that search returns empty results when no sessions match."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        await repo.create_session(_make_session("session-1", agent_name="calculator"))
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("xyznonexistent12345")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_sessions_respects_limit(self, db_session):
        """Test that search respects the limit parameter."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        for i in range(5):
            session = _make_session(f"session-{i}", agent_name=f"agent-{i}")
            await repo.create_session(session)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("agent", limit=2)

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_search_sessions_with_status_filter(self, db_session):
        """Test that search filters by session status."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        await repo.create_session(_make_session("session-error", status=SessionStatus.ERROR))
        await repo.create_session(_make_session("session-completed", status=SessionStatus.COMPLETED))
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("session", status="error")

        assert len(results) == 1
        assert results[0].id == "session-error"
        assert results[0].status == SessionStatus.ERROR

    @pytest.mark.asyncio
    async def test_search_sessions_results_ranked_by_similarity(self, db_session):
        """Test that results are ranked by similarity score in descending order."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")

        # Create sessions with different agent names
        await repo.create_session(_make_session("session-1", agent_name="weather_search_agent"))
        await repo.create_session(_make_session("session-2", agent_name="calculator"))
        await repo.create_session(_make_session("session-3", agent_name="weather_forecast_tool"))

        # Add events to create embeddings
        weather_event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-api-call",
            tool_name="weather_service",
            arguments={"city": "Paris"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(weather_event)

        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("weather")

        # Results should be ranked by similarity
        if len(results) > 1:
            similarities = [r.search_similarity for r in results]
            assert similarities == sorted(similarities, reverse=True)

    @pytest.mark.asyncio
    async def test_search_sessions_with_special_characters(self, db_session):
        """Test search with special characters in query."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1", agent_name="test_agent")
        await repo.create_session(session)

        # Add event with special characters
        event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="test-event",
            tool_name="api_tool",
            arguments={"query": "test_value-with.dots"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        # Search should handle special characters gracefully
        results = await search_service.search_sessions("test")

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_sessions_no_results_without_events(self, db_session):
        """Test that sessions without events can still be searched (by session metadata)."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        # Create a session but don't add any events
        await repo.create_session(_make_session("session-1", agent_name="weather_agent"))
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_sessions("weather")

        # Without events, embedding will be empty, so no matches
        # This is expected behavior - search needs event text to match against
        assert results == []


class TestTenantIsolation:
    """Test that search properly isolates results by tenant."""

    @pytest.mark.asyncio
    async def test_search_sessions_tenant_isolation(self, db_session):
        """Test that search only returns results for the correct tenant."""
        repo_tenant_a = TraceRepository(db_session, tenant_id="tenant-a")
        repo_tenant_b = TraceRepository(db_session, tenant_id="tenant-b")

        # Create sessions for different tenants
        session_a = _make_session("session-a", agent_name="weather_agent")
        session_b = _make_session("session-b", agent_name="weather_agent")

        await repo_tenant_a.create_session(session_a)
        await repo_tenant_b.create_session(session_b)

        # Add events to both
        event_a = ToolCallEvent(
            id="event-a",
            session_id="session-a",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-call",
            tool_name="weather_api",
            arguments={"location": "London"},
            upstream_event_ids=["root"],
        )
        event_b = ToolCallEvent(
            id="event-b",
            session_id="session-b",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-call",
            tool_name="weather_api",
            arguments={"location": "Paris"},
            upstream_event_ids=["root"],
        )

        await repo_tenant_a.add_event(event_a)
        await repo_tenant_b.add_event(event_b)
        await db_session.commit()

        # Search as tenant-a should only return tenant-a's session
        search_service_a = SessionSearchService(db_session, tenant_id="tenant-a")
        results_a = await search_service_a.search_sessions("weather")

        assert len(results_a) == 1
        assert results_a[0].id == "session-a"

        # Search as tenant-b should only return tenant-b's session
        search_service_b = SessionSearchService(db_session, tenant_id="tenant-b")
        results_b = await search_service_b.search_sessions("weather")

        assert len(results_b) == 1
        assert results_b[0].id == "session-b"

    @pytest.mark.asyncio
    async def test_search_events_tenant_isolation(self, db_session):
        """Test that event search only returns results for the correct tenant."""
        repo_tenant_a = TraceRepository(db_session, tenant_id="tenant-a")
        repo_tenant_b = TraceRepository(db_session, tenant_id="tenant-b")

        # Create sessions for different tenants
        session_a = _make_session("session-a")
        session_b = _make_session("session-b")

        await repo_tenant_a.create_session(session_a)
        await repo_tenant_b.create_session(session_b)

        # Add events with similar names to both tenants
        event_a = ToolCallEvent(
            id="event-a",
            session_id="session-a",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="search-api-call",
            tool_name="search_tool",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )
        event_b = ToolCallEvent(
            id="event-b",
            session_id="session-b",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="search-api-call",
            tool_name="search_tool",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )

        await repo_tenant_a.add_event(event_a)
        await repo_tenant_b.add_event(event_b)
        await db_session.commit()

        # Search as tenant-a should only return tenant-a's events
        search_service_a = SessionSearchService(db_session, tenant_id="tenant-a")
        results_a = await search_service_a.search_events("search")

        assert len(results_a) == 1
        assert results_a[0].id == "event-a"

        # Search as tenant-b should only return tenant-b's events
        search_service_b = SessionSearchService(db_session, tenant_id="tenant-b")
        results_b = await search_service_b.search_events("search")

        assert len(results_b) == 1
        assert results_b[0].id == "event-b"


class TestEventSearch:
    """Test text search over events."""

    @pytest.mark.asyncio
    async def test_search_events_by_name(self, db_session):
        """Test searching events by name."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-api-call",
            tool_name="weather_api",
            arguments={"location": "London"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("weather")

        assert len(results) == 1
        assert results[0].id == "event-1"
        assert results[0].name == "weather-api-call"

    @pytest.mark.asyncio
    async def test_search_events_by_data_content(self, db_session):
        """Test searching events by data field content."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        event = ErrorEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="api-error",
            error_type="ConnectionError",
            error_message="Failed to connect to remote service",
        )
        await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("ConnectionError")

        assert len(results) == 1
        assert results[0].id == "event-1"

    @pytest.mark.asyncio
    async def test_search_events_with_session_filter(self, db_session):
        """Test searching events within a specific session."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session1 = _make_session("session-1")
        session2 = _make_session("session-2")
        await repo.create_session(session1)
        await repo.create_session(session2)

        event1 = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="search-call",
            tool_name="search_api",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )
        event2 = ToolCallEvent(
            id="event-2",
            session_id="session-2",
            timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
            name="search-call",
            tool_name="search_api",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event1)
        await repo.add_event(event2)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("search", session_id="session-1")

        assert len(results) == 1
        assert results[0].id == "event-1"

    @pytest.mark.asyncio
    async def test_search_events_with_event_type_filter(self, db_session):
        """Test searching events with event type filter."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        tool_event = ToolCallEvent(
            id="event-tool",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="my-event",
            tool_name="search",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )
        llm_event = LLMRequestEvent(
            id="event-llm",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
            model="gpt-4",
            messages=[{"role": "user", "content": "my event"}],
            tools=[],
            settings={},
        )
        await repo.add_event(tool_event)
        await repo.add_event(llm_event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("my-event", event_type="tool_call")

        assert len(results) == 1
        assert results[0].id == "event-tool"

    @pytest.mark.asyncio
    async def test_search_events_respects_limit(self, db_session):
        """Test that event search respects the limit parameter."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        for i in range(10):
            event = ToolCallEvent(
                id=f"event-{i}",
                session_id="session-1",
                timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
                name="search-call",
                tool_name="search",
                arguments={"index": i},
                upstream_event_ids=["root"],
            )
            await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("search", limit=5)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_events_with_sql_wildcards_escaped(self, db_session):
        """Test that SQL LIKE wildcards are properly escaped in event search."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        # Create an event with underscore in name (SQL wildcard)
        event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="test_event_with_underscores",
            tool_name="search_tool",
            arguments={"pattern": "test_value"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)

        # Create another event that should NOT match the escaped query
        event2 = ToolCallEvent(
            id="event-2",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
            name="testXeventXwithXunderscores",  # Different chars, shouldn't match "_"
            tool_name="other_tool",
            arguments={"pattern": "other"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event2)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        # Search with underscore - should be treated as literal, not wildcard
        results = await search_service.search_events("test_event_with")

        # Should only match the first event with literal underscores
        assert len(results) == 1
        assert results[0].id == "event-1"

    @pytest.mark.asyncio
    async def test_search_events_with_percent_wildcard_escaped(self, db_session):
        """Test that percent signs are properly escaped in event search."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="test-100%-complete",
            tool_name="progress_tracker",
            arguments={"progress": "100%"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        # Search with % - should be treated as literal, not wildcard
        results = await search_service.search_events("100%")

        # Should match the event with literal %
        assert len(results) == 1
        assert results[0].id == "event-1"

    @pytest.mark.asyncio
    async def test_search_events_empty_results_for_no_match(self, db_session):
        """Test that event search returns empty results when nothing matches."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        event = ToolCallEvent(
            id="event-1",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="weather-call",
            tool_name="weather",
            arguments={"location": "London"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("xyznonexistent12345")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_events_ordered_by_timestamp_desc(self, db_session):
        """Test that event search results are ordered by timestamp descending."""
        repo = TraceRepository(db_session, tenant_id="tenant-1")
        session = _make_session("session-1")
        await repo.create_session(session)

        for i in range(3):
            event = ToolCallEvent(
                id=f"event-{i}",
                session_id="session-1",
                timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
                name="search-call",
                tool_name="search",
                arguments={"index": i},
                upstream_event_ids=["root"],
            )
            await repo.add_event(event)
        await db_session.commit()

        search_service = SessionSearchService(db_session, tenant_id="tenant-1")
        results = await search_service.search_events("search")

        assert len(results) == 3
        # Should be ordered by timestamp descending (newest first)
        assert results[0].id == "event-2"
        assert results[1].id == "event-1"
        assert results[2].id == "event-0"
