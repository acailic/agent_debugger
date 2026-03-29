"""Tests for storage/search.py - SessionSearchService.

Tests query parsing, result ranking, tenant isolation, empty results,
special characters, and SQL LIKE escaping.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import (
    ErrorEvent,
    EventType,
    LLMRequestEvent,
    Session,
    SessionStatus,
    ToolCallEvent,
)
from storage.converters import event_to_orm
from storage.models import Base
from storage.repository import TraceRepository
from storage.search import SessionSearchService


def _make_session(
    session_id: str,
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.COMPLETED,
) -> Session:
    """Helper to create test sessions."""
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
    """Create in-memory database for isolated testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_sessions_basic_query(db_session: AsyncSession):
    """Test basic session search returns ranked results."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    await repo.create_session(_make_session("session-1", agent_name="weather_agent"))
    await repo.create_session(_make_session("session-2", agent_name="search_agent"))
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("weather")

    assert len(results) > 0
    # Should find weather_agent with higher similarity
    assert any(s.agent_name == "weather_agent" for s in results)
    # All results should have search_similarity attribute
    for result in results:
        assert hasattr(result, "search_similarity")
        assert result.search_similarity > 0.0


@pytest.mark.asyncio
async def test_search_sessions_with_status_filter(db_session: AsyncSession):
    """Test session search with status filter only returns matching sessions."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    await repo.create_session(_make_session("session-error", status=SessionStatus.ERROR))
    await repo.create_session(_make_session("session-completed", status=SessionStatus.COMPLETED))
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("session", status="error")

    assert len(results) == 1
    assert results[0].status == SessionStatus.ERROR
    assert results[0].id == "session-error"


@pytest.mark.asyncio
async def test_search_sessions_empty_query(db_session: AsyncSession):
    """Test that empty or whitespace-only queries return no results."""
    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Empty string
    results = await service.search_sessions("")
    assert results == []

    # Whitespace only
    results = await service.search_sessions("   ")
    assert results == []

    # None query would fail type check, but test empty behavior


@pytest.mark.asyncio
async def test_search_sessions_no_matching_results(db_session: AsyncSession):
    """Test search returns empty list when no sessions match query."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    await repo.create_session(_make_session("session-1", agent_name="weather_agent"))
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("xyznonexistent12345")

    assert results == []


@pytest.mark.asyncio
async def test_search_sessions_tenant_isolation(db_session: AsyncSession):
    """Test that search only returns sessions for the correct tenant."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    await repo_a.create_session(_make_session("session-a", agent_name="agent_a"))
    await repo_b.create_session(_make_session("session-b", agent_name="agent_b"))
    await db_session.commit()

    service_a = SessionSearchService(db_session, tenant_id="tenant-a")
    service_b = SessionSearchService(db_session, tenant_id="tenant-b")

    results_a = await service_a.search_sessions("agent")
    results_b = await service_b.search_sessions("agent")

    # Each tenant should only see their own sessions
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0].id == "session-a"
    assert results_b[0].id == "session-b"


@pytest.mark.asyncio
async def test_search_sessions_ranking_by_similarity(db_session: AsyncSession):
    """Test that results are ranked by similarity score in descending order."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    await repo.create_session(_make_session("session-weather", agent_name="weather_service"))
    await repo.create_session(_make_session("session-search", agent_name="search_service"))
    await repo.create_session(_make_session("session-generic", agent_name="generic_agent"))
    await db_session.commit()

    # Add some events to make embeddings more meaningful
    for session_id in ["session-weather", "session-search", "session-generic"]:
        event = ToolCallEvent(
            id=f"event-{session_id}",
            session_id=session_id,
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="tool_call",
            tool_name="weather_api" if "weather" in session_id else "search_api",
            arguments={"query": "test"},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("weather")

    # Results should be sorted by similarity (highest first)
    if len(results) > 1:
        similarities = [r.search_similarity for r in results]
        assert similarities == sorted(similarities, reverse=True)


@pytest.mark.asyncio
async def test_search_sessions_respects_limit(db_session: AsyncSession):
    """Test that search results respect the limit parameter."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    for i in range(10):
        await repo.create_session(_make_session(f"session-{i}", agent_name=f"agent_{i}"))
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("agent", limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_search_sessions_with_events(db_session: AsyncSession):
    """Test that search uses event data for building embeddings."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-events", agent_name="test_agent")
    await repo.create_session(session)

    # Add events with searchable content
    event1 = ToolCallEvent(
        id="event-1",
        session_id="session-events",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="search_api",
        tool_name="web_search",
        arguments={"query": "python tutorials"},
        upstream_event_ids=["root"],
    )
    event2 = ErrorEvent(
        id="event-2",
        session_id="session-events",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="api_error",
        error_type="ConnectionError",
        error_message="Failed to connect to search service",
    )
    await repo.add_event(event1)
    await repo.add_event(event2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Search for term from events
    results = await service.search_sessions("python")
    assert len(results) > 0
    assert results[0].id == "session-events"

    # Search for error type
    results = await service.search_sessions("ConnectionError")
    assert len(results) > 0
    assert results[0].id == "session-events"


@pytest.mark.asyncio
async def test_search_events_basic_query(db_session: AsyncSession):
    """Test basic event search by name."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event1 = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="search_weather",
        tool_name="weather_api",
        arguments={"location": "London"},
        upstream_event_ids=["root"],
    )
    event2 = ToolCallEvent(
        id="event-2",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="calculate_sum",
        tool_name="calculator",
        arguments={"a": 1, "b": 2},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event1)
    await repo.add_event(event2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_events("weather")

    assert len(results) == 1
    assert results[0].id == "event-1"
    assert results[0].name == "search_weather"


@pytest.mark.asyncio
async def test_search_events_with_session_filter(db_session: AsyncSession):
    """Test event search filtered by session_id."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session1 = _make_session("session-1")
    session2 = _make_session("session-2")
    await repo.create_session(session1)
    await repo.create_session(session2)

    event1 = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="search",
        tool_name="api",
        arguments={"q": "test"},
        upstream_event_ids=["root"],
    )
    event2 = ToolCallEvent(
        id="event-2",
        session_id="session-2",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="search",
        tool_name="api",
        arguments={"q": "test"},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event1)
    await repo.add_event(event2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_events("search", session_id="session-1")

    assert len(results) == 1
    assert results[0].session_id == "session-1"


@pytest.mark.asyncio
async def test_search_events_with_event_type_filter(db_session: AsyncSession):
    """Test event search filtered by event_type."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event1 = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="tool_start",
        tool_name="search",
        arguments={},
        upstream_event_ids=["root"],
    )
    event2 = LLMRequestEvent(
        id="event-2",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        model="gpt-4",
        messages=[{"role": "user", "content": "test"}],
        tools=[],
        settings={},
    )
    await repo.add_event(event1)
    await repo.add_event(event2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Search for "start" without type filter - should find both
    all_results = await service.search_events("start")
    assert len(all_results) >= 1

    # Search with event_type filter
    tool_results = await service.search_events("start", event_type="tool_call")
    assert len(tool_results) == 1
    assert tool_results[0].id == "event-1"


@pytest.mark.asyncio
async def test_search_events_special_characters_escaped(db_session: AsyncSession):
    """Test that special SQL LIKE characters are properly escaped."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    # Create events with special characters
    event1 = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="test_with_underscore",
        tool_name="api",
        arguments={"pattern": "test_value"},
        upstream_event_ids=["root"],
    )
    event2 = ToolCallEvent(
        id="event-2",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="test_with_percent",
        tool_name="api",
        arguments={"pattern": "100%"},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event1)
    await repo.add_event(event2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Search for underscore - should only match events with literal underscore
    results = await service.search_events("test_with_underscore")
    assert len(results) == 1
    assert results[0].id == "event-1"

    # Search for percent - should only match events with literal percent
    results = await service.search_events("100%")
    assert len(results) == 1
    assert results[0].id == "event-2"


@pytest.mark.asyncio
async def test_search_events_tenant_isolation(db_session: AsyncSession):
    """Test that event search respects tenant isolation."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    session_a = _make_session("session-a")
    session_b = _make_session("session-b")
    await repo_a.create_session(session_a)
    await repo_b.create_session(session_b)

    event_a = ToolCallEvent(
        id="event-a",
        session_id="session-a",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="search",
        tool_name="api",
        arguments={},
        upstream_event_ids=["root"],
    )
    event_b = ToolCallEvent(
        id="event-b",
        session_id="session-b",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="search",
        tool_name="api",
        arguments={},
        upstream_event_ids=["root"],
    )

    await repo_a.add_event(event_a)
    await repo_b.add_event(event_b)
    await db_session.commit()

    service_a = SessionSearchService(db_session, tenant_id="tenant-a")
    service_b = SessionSearchService(db_session, tenant_id="tenant-b")

    results_a = await service_a.search_events("search")
    results_b = await service_b.search_events("search")

    # Each tenant should only see their own events
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0].id == "event-a"
    assert results_b[0].id == "event-b"


@pytest.mark.asyncio
async def test_search_events_empty_results(db_session: AsyncSession):
    """Test that event search returns empty list when no matches found."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="weather_api_call",
        tool_name="weather",
        arguments={},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_events("xyznonexistent12345")

    assert results == []


@pytest.mark.asyncio
async def test_search_events_respects_limit(db_session: AsyncSession):
    """Test that event search respects the limit parameter."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    for i in range(10):
        event = ToolCallEvent(
            id=f"event-{i}",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
            name="search_api",
            tool_name="api",
            arguments={"index": i},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_events("search", limit=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_events_searches_data_field(db_session: AsyncSession):
    """Test that event search searches within the data JSON field."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="api_call",
        tool_name="weather_service",
        arguments={"location": "Paris", "units": "metric"},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Should find the event by searching for content in the data field
    results = await service.search_events("Paris")
    assert len(results) == 1
    assert results[0].id == "event-1"

    results = await service.search_events("metric")
    assert len(results) == 1
    assert results[0].id == "event-1"


@pytest.mark.asyncio
async def test_search_events_returns_most_recent_first(db_session: AsyncSession):
    """Test that event search returns results ordered by timestamp descending."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    for i in range(5):
        event = ToolCallEvent(
            id=f"event-{i}",
            session_id="session-1",
            timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
            name="search_api",
            tool_name="api",
            arguments={"index": i},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_events("search")

    # Results should be ordered by timestamp descending
    timestamps = [r.timestamp for r in results]
    assert timestamps == sorted(timestamps, reverse=True)
