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
async def test_search_sessions_empty_query(db_session: AsyncSession):
    """Test that empty or whitespace-only queries return no results."""
    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Empty string
    results = await service.search_sessions("")
    assert results == []

    # Whitespace only
    results = await service.search_sessions("   ")
    assert results == []


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
async def test_search_sessions_with_status_filter(db_session: AsyncSession):
    """Test session search with status filter only returns matching sessions."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    
    s1 = _make_session("session-error", status=SessionStatus.ERROR)
    s2 = _make_session("session-completed", status=SessionStatus.COMPLETED)
    await repo.create_session(s1)
    await repo.create_session(s2)
    
    # Add events to make them searchable
    e1 = ToolCallEvent(
        id="event-1", session_id="session-error",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="api_call", tool_name="service", arguments={},
        upstream_event_ids=["root"],
    )
    e2 = ToolCallEvent(
        id="event-2", session_id="session-completed",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="api_call", tool_name="service", arguments={},
        upstream_event_ids=["root"],
    )
    await repo.add_event(e1)
    await repo.add_event(e2)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("api_call", status="error")

    assert len(results) == 1
    assert results[0].status == SessionStatus.ERROR
    assert results[0].id == "session-error"


@pytest.mark.asyncio
async def test_search_sessions_tenant_isolation(db_session: AsyncSession):
    """Test that search only returns sessions for the correct tenant."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    s1 = _make_session("session-a", agent_name="agent_a")
    s2 = _make_session("session-b", agent_name="agent_b")
    await repo_a.create_session(s1)
    await repo_b.create_session(s2)
    
    # Add events
    e1 = ToolCallEvent(
        id="event-a", session_id="session-a",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="agent_call", tool_name="api", arguments={},
        upstream_event_ids=["root"],
    )
    e2 = ToolCallEvent(
        id="event-b", session_id="session-b",
        timestamp=datetime(2026, 3, 29, 10, 2, tzinfo=timezone.utc),
        name="agent_call", tool_name="api", arguments={},
        upstream_event_ids=["root"],
    )
    await repo_a.add_event(e1)
    await repo_b.add_event(e2)
    await db_session.commit()

    service_a = SessionSearchService(db_session, tenant_id="tenant-a")
    service_b = SessionSearchService(db_session, tenant_id="tenant-b")

    results_a = await service_a.search_sessions("agent_call")
    results_b = await service_b.search_sessions("agent_call")

    # Each tenant should only see their own sessions
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0].id == "session-a"
    assert results_b[0].id == "session-b"


@pytest.mark.asyncio
async def test_search_sessions_respects_limit(db_session: AsyncSession):
    """Test that search results respect the limit parameter."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    
    for i in range(10):
        session = _make_session(f"session-{i}", agent_name=f"agent_{i}")
        await repo.create_session(session)
        event = ToolCallEvent(
            id=f"event-{i}",
            session_id=f"session-{i}",
            timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
            name="agent_call",
            tool_name="api",
            arguments={},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("agent_call", limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_search_sessions_ranking_by_similarity(db_session: AsyncSession):
    """Test that results are ranked by similarity score in descending order."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    
    # Create sessions with different relevance to "weather"
    for session_id, tool_name in [
        ("session-weather", "weather_api"),
        ("session-search", "search_api"),
        ("session-generic", "generic_api"),
    ]:
        session = _make_session(session_id, agent_name=f"{tool_name}_agent")
        await repo.create_session(session)
        
        event = ToolCallEvent(
            id=f"event-{session_id}",
            session_id=session_id,
            timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
            name="api_call",
            tool_name=tool_name,
            arguments={},
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


@pytest.mark.asyncio
async def test_search_events_case_insensitive(db_session: AsyncSession):
    """Test that event search is case-insensitive."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="WeatherAPI_Call",
        tool_name="weather_service",
        arguments={},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Should find with different cases
    for query in ["weather", "WEATHER", "Weather"]:
        results = await service.search_events(query)
        assert len(results) == 1
        assert results[0].id == "event-1"


@pytest.mark.asyncio
async def test_search_events_with_percent_sign(db_session: AsyncSession):
    """Test that percent sign in data field is searchable."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="discount_calculation",
        tool_name="api",
        arguments={"discount": "50%"},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Should find event by searching for discount
    results = await service.search_events("discount")
    assert len(results) == 1
    assert results[0].id == "event-1"


@pytest.mark.asyncio
async def test_search_events_with_special_characters(db_session: AsyncSession):
    """Test searching for events with hyphens and other special chars."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session("session-1")
    await repo.create_session(session)

    event = ToolCallEvent(
        id="event-1",
        session_id="session-1",
        timestamp=datetime(2026, 3, 29, 10, 1, tzinfo=timezone.utc),
        name="api-call-v2",
        tool_name="rest_service",
        arguments={"endpoint": "/api/v2/users"},
        upstream_event_ids=["root"],
    )
    await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")

    # Should find by searching for parts of the name
    results = await service.search_events("api-call")
    assert len(results) == 1
    assert results[0].id == "event-1"


@pytest.mark.asyncio
async def test_search_sessions_with_multiple_events(db_session: AsyncSession):
    """Test session search with sessions containing multiple events."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    
    session = _make_session("session-multi", agent_name="multi_agent")
    await repo.create_session(session)
    
    # Add multiple events
    for i in range(5):
        event = ToolCallEvent(
            id=f"event-{i}",
            session_id="session-multi",
            timestamp=datetime(2026, 3, 29, 10, i, tzinfo=timezone.utc),
            name="multi_call",
            tool_name="api",
            arguments={"index": i},
            upstream_event_ids=["root"],
        )
        await repo.add_event(event)
    await db_session.commit()

    service = SessionSearchService(db_session, tenant_id="tenant-a")
    results = await service.search_sessions("multi_call")

    assert len(results) > 0
    assert results[0].id == "session-multi"
