"""Tests for semantic session search functionality."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from storage.models import Base
from storage.repository import TraceRepository


def _make_session(
    session_id: str = "session-1",
    status: SessionStatus = SessionStatus.ERROR,
) -> Session:
    return Session(
        id=session_id,
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        status=status,
        config={"mode": "test"},
        tags=["coverage"],
    )


def _make_error_event(
    session_id: str,
    error_type: str = "TimeoutError",
    error_message: str = "Request timed out after 30 seconds",
    event_id: str = "event-1",
) -> TraceEvent:
    """Create an error event with specific error type and message."""
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="error_occurred",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
        data={
            "error_type": error_type,
            "error_message": error_message,
        },
    )


def _make_tool_event(session_id: str, tool_name: str = "search_api") -> TraceEvent:
    """Create a tool call event."""
    return TraceEvent(
        id="event-2",
        session_id=session_id,
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        data={
            "tool_name": tool_name,
            "model": "gpt-4",
        },
    )


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_finds_similar_sessions(db_session):
    """Test that search finds sessions with semantically similar errors."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create two sessions with timeout errors (use "timeout" in message)
    session1 = _make_session("session-1")
    session2 = _make_session("session-2")
    await repo.create_session(session1)
    await repo.create_session(session2)

    event1 = _make_error_event("session-1", "TimeoutError", "Request timeout after 30 seconds", "event-1")
    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout waiting for response", "event-2")
    await repo.add_event(event1)
    await repo.add_event(event2)

    # Create a session with validation error (different type)
    session3 = _make_session("session-3")
    await repo.create_session(session3)

    event3 = _make_error_event("session-3", "ValidationError", "Invalid input parameter", "event-3")
    await repo.add_event(event3)

    await repo.commit()

    # Search for "timeout error"
    results = await repo.search_sessions("timeout error")

    # Should find the two timeout sessions but not the validation error session
    # Note: All sessions have "error" in event_type, so they all match partially
    # But only sessions 1 and 2 have "timeout" in the error message
    session_ids = [s.id for s in results]
    assert "session-1" in session_ids
    assert "session-2" in session_ids

    # The validation error session should have lower similarity (no "timeout" token)
    session3_result = next((s for s in results if s.id == "session-3"), None)
    if session3_result:
        # session-3 should only match on "error" token, not "timeout"
        assert session3_result.search_similarity is not None
        assert session3_result.search_similarity < 0.4  # Lower similarity without "timeout"


@pytest.mark.asyncio
async def test_search_returns_similarity_score(db_session):
    """Test that search results include similarity scores."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    session = _make_session("session-1")
    await repo.create_session(session)

    event = _make_error_event("session-1", "TimeoutError", "Connection timeout occurred", "event-1")
    await repo.add_event(event)

    await repo.commit()

    # Search for "timeout"
    results = await repo.search_sessions("timeout")

    assert len(results) == 1
    result = results[0]

    # Check that search_similarity is set
    assert result.search_similarity is not None
    assert isinstance(result.search_similarity, float)

    # Similarity should be between 0 and 1
    assert 0.0 <= result.search_similarity <= 1.0

    # For a matching query, similarity should be > 0
    assert result.search_similarity > 0.0


@pytest.mark.asyncio
async def test_search_empty_query(db_session):
    """Test that empty query returns empty list."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create a session
    session = _make_session("session-1")
    await repo.create_session(session)

    await repo.commit()

    # Search with empty query
    results = await repo.search_sessions("")
    assert results == []

    # Search with whitespace-only query
    results = await repo.search_sessions("   ")
    assert results == []


@pytest.mark.asyncio
async def test_search_no_sessions(db_session):
    """Test that search returns empty list when no sessions exist."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Search without any sessions
    results = await repo.search_sessions("timeout")
    assert results == []


@pytest.mark.asyncio
async def test_search_respects_limit(db_session):
    """Test that search respects the limit parameter."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create 5 sessions with timeout errors
    for i in range(5):
        session = _make_session(f"session-{i}")
        await repo.create_session(session)

        event = _make_error_event(f"session-{i}", "TimeoutError", f"Connection timeout {i}", f"event-{i}")
        await repo.add_event(event)

    await repo.commit()

    # Search with limit=2
    results = await repo.search_sessions("timeout", limit=2)

    # Should return at most 2 results
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_search_filters_by_status(db_session):
    """Test that search can filter by session status."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create error session
    error_session = _make_session("session-1", status=SessionStatus.ERROR)
    await repo.create_session(error_session)
    error_event = _make_error_event("session-1", "TimeoutError", "Connection timeout occurred", "event-1")
    await repo.add_event(error_event)

    # Create completed session with similar content
    completed_session = _make_session("session-2", status=SessionStatus.COMPLETED)
    await repo.create_session(completed_session)
    completed_event = _make_error_event("session-2", "TimeoutError", "Connection timeout occurred", "event-2")
    await repo.add_event(completed_event)

    await repo.commit()

    # Search filtering by error status
    results = await repo.search_sessions("timeout", status=str(SessionStatus.ERROR))

    # Should only return the error session
    assert len(results) == 1
    assert results[0].id == "session-1"
    assert results[0].status == SessionStatus.ERROR

    # Search filtering by completed status
    results = await repo.search_sessions("timeout", status=str(SessionStatus.COMPLETED))

    # Should only return the completed session
    assert len(results) == 1
    assert results[0].id == "session-2"
    assert results[0].status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_search_ranks_by_similarity(db_session):
    """Test that search results are ranked by similarity score."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create session with exact match (both "timeout" and "error")
    session1 = _make_session("session-1")
    await repo.create_session(session1)
    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout error occurred", "event-1")
    await repo.add_event(event1)

    # Create session with partial match (only "error")
    session2 = _make_session("session-2")
    await repo.create_session(session2)
    event2 = _make_error_event("session-2", "NetworkError", "network connection failed", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    # Search for "timeout error"
    results = await repo.search_sessions("timeout error")

    # Both should match but session-1 should have higher similarity
    assert len(results) >= 1
    if len(results) >= 2:
        # First result should have higher or equal similarity
        assert results[0].search_similarity >= results[1].search_similarity

    # Verify session-1 has higher similarity because it matches both "timeout" and "error"
    session1_result = next((s for s in results if s.id == "session-1"), None)
    session2_result = next((s for s in results if s.id == "session-2"), None)

    if session1_result and session2_result:
        assert session1_result.search_similarity > session2_result.search_similarity


@pytest.mark.asyncio
async def test_search_scoped_to_tenant(db_session):
    """Test that search is scoped to tenant_id."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    # Create session for tenant-a
    session_a = _make_session("session-a")
    await repo_a.create_session(session_a)
    event_a = _make_error_event("session-a", "TimeoutError", "Connection timeout", "event-a")
    await repo_a.add_event(event_a)
    await repo_a.commit()

    # Create session for tenant-b
    session_b = _make_session("session-b")
    await repo_b.create_session(session_b)
    event_b = _make_error_event("session-b", "TimeoutError", "Connection timeout", "event-b")
    await repo_b.add_event(event_b)
    await repo_b.commit()

    # Search from tenant-a should only see tenant-a sessions
    results_a = await repo_a.search_sessions("timeout")
    assert len(results_a) == 1
    assert results_a[0].id == "session-a"

    # Search from tenant-b should only see tenant-b sessions
    results_b = await repo_b.search_sessions("timeout")
    assert len(results_b) == 1
    assert results_b[0].id == "session-b"


@pytest.mark.asyncio
async def test_search_with_no_events(db_session):
    """Test that sessions with no events return empty embedding."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")

    # Create session without events
    session = _make_session("session-1")
    await repo.create_session(session)
    await repo.commit()

    # Search should not return sessions with no events
    results = await repo.search_sessions("timeout")
    assert len(results) == 0
