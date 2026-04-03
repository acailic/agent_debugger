"""Tests for natural language search enhancements."""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
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


def _make_tool_event(session_id: str, tool_name: str = "search_api", event_id: str = "event-2") -> TraceEvent:
    """Create a tool call event."""
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        data={
            "tool_name": tool_name,
            "model": "gpt-4",
        },
    )


# =============================================================================
# Advanced Filter Tests
# =============================================================================


@pytest.mark.asyncio
async def test_search_filters_by_agent_name(db_session):
    """Test that search can filter by agent name."""
    repo = TraceRepository(db_session, tenant_id="tenant-agent")

    # Create sessions for different agents
    session1 = _make_session("session-1")
    session1.agent_name = "agent-a"
    await repo.create_session(session1)
    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    session2 = _make_session("session-2")
    session2.agent_name = "agent-b"
    await repo.create_session(session2)
    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    # Search filtering by agent name
    results = await repo.search_sessions("timeout", agent_name="agent-a")

    # Should only return agent-a sessions
    assert len(results) == 1
    assert results[0].agent_name == "agent-a"


@pytest.mark.asyncio
async def test_search_filters_by_tags(db_session):
    """Test that search can filter by tags."""
    repo = TraceRepository(db_session, tenant_id="tenant-tags")

    # Create sessions with different tags
    session1 = _make_session("session-1")
    session1.tags = ["production", "api"]
    await repo.create_session(session1)
    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    session2 = _make_session("session-2")
    session2.tags = ["development", "api"]
    await repo.create_session(session2)
    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    # Search filtering by production tag
    results = await repo.search_sessions("timeout", tags=["production"])

    # Should only return sessions with production tag
    assert len(results) == 1
    assert "production" in results[0].tags


@pytest.mark.asyncio
async def test_search_filters_by_min_errors(db_session):
    """Test that search can filter by minimum error count."""
    repo = TraceRepository(db_session, tenant_id="tenant-errors")

    # Create sessions with different error counts
    session1 = _make_session("session-1")
    session1.errors = 5
    await repo.create_session(session1)
    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    session2 = _make_session("session-2")
    session2.errors = 1
    await repo.create_session(session2)
    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    # Search filtering by minimum errors
    results = await repo.search_sessions("timeout", min_errors=3)

    # Should only return sessions with 3+ errors
    assert len(results) == 1
    assert results[0].errors >= 3


@pytest.mark.asyncio
async def test_search_filters_by_time_range(db_session):
    """Test that search can filter by time range."""
    repo = TraceRepository(db_session, tenant_id="tenant-time")

    # Create sessions at different times
    old_session = Session(
        id="old-session",
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        config={"mode": "test"},
        tags=["coverage"],
    )
    await repo.create_session(old_session)
    old_event = _make_error_event("old-session", "TimeoutError", "Connection timeout", "old-event")
    await repo.add_event(old_event)

    new_session = Session(
        id="new-session",
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        config={"mode": "test"},
        tags=["coverage"],
    )
    await repo.create_session(new_session)
    new_event = _make_error_event("new-session", "TimeoutError", "Connection timeout", "new-event")
    await repo.add_event(new_event)

    await repo.commit()

    # Search filtering by started_after
    results = await repo.search_sessions(
        "timeout",
        started_after=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    # Should only return sessions started after Feb 1
    assert len(results) == 1
    assert results[0].id == "new-session"


@pytest.mark.asyncio
async def test_search_filters_by_event_type(db_session):
    """Test that search can filter by event type."""
    repo = TraceRepository(db_session, tenant_id="tenant-event-type")

    # Create session with tool event
    session = _make_session("session-1")
    await repo.create_session(session)

    # Create tool event with tool_name that will match our search
    tool_event = TraceEvent(
        id="event-tool-1",
        session_id="session-1",
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        data={
            "tool_name": "database_query",
            "model": "gpt-4",
        },
    )
    await repo.add_event(tool_event)

    await repo.commit()

    # Search for "database_query" (the full token, not just "query")
    results = await repo.search_sessions("database_query")
    assert len(results) > 0, f"Expected to find session with 'database_query', got {len(results)} results"

    # Now test filtering by event_type
    results = await repo.search_sessions("database_query", event_type="tool_call")

    # Should return sessions with tool_call events
    assert len(results) >= 1
    assert results[0].id == "session-1"


@pytest.mark.asyncio
async def test_search_returns_highlights(db_session):
    """Test that search returns highlight snippets for matches."""
    repo = TraceRepository(db_session, tenant_id="tenant-highlights")

    session = _make_session("session-1")
    await repo.create_session(session)
    event = _make_error_event("session-1", "TimeoutError", "Connection timeout after 30 seconds", "event-1")
    await repo.add_event(event)

    await repo.commit()

    # Search for "timeout"
    results = await repo.search_sessions("timeout")

    assert len(results) == 1
    result = results[0]

    # Check that highlights are returned
    assert hasattr(result, "search_highlights")
    highlights = result.search_highlights
    assert isinstance(highlights, list)


@pytest.mark.asyncio
async def test_search_with_combined_filters(db_session):
    """Test that search works with multiple filters combined."""
    repo = TraceRepository(db_session, tenant_id="tenant-combined")

    # Create matching session
    session1 = Session(
        id="session-1",
        agent_name="agent-a",
        framework="pytest",
        started_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=5,
        config={"mode": "test"},
        tags=["production", "critical"],
    )
    await repo.create_session(session1)
    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    # Create non-matching sessions
    session2 = Session(
        id="session-2",
        agent_name="agent-b",  # Different agent
        framework="pytest",
        started_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=5,
        config={"mode": "test"},
        tags=["production", "critical"],
    )
    await repo.create_session(session2)
    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    session3 = Session(
        id="session-3",
        agent_name="agent-a",
        framework="pytest",
        started_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=1,  # Too few errors
        config={"mode": "test"},
        tags=["production", "critical"],
    )
    await repo.create_session(session3)
    event3 = _make_error_event("session-3", "TimeoutError", "Connection timeout", "event-3")
    await repo.add_event(event3)

    await repo.commit()

    # Search with multiple filters
    results = await repo.search_sessions(
        "timeout",
        agent_name="agent-a",
        min_errors=3,
        tags=["production"],
    )

    # Should only return session-1 (matches all filters)
    assert len(results) == 1
    assert results[0].id == "session-1"


# =============================================================================
# Natural Language Interpretation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_nl_query_interpretation_stuck_in_loop(db_session):
    """Test that NL query interpretation detects 'stuck in a loop' pattern."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    # Test interpretation
    params = service.interpret_nl_query("find sessions where the agent got stuck in a loop")

    assert "min_errors" in params
    assert params["min_errors"] == 1
    assert "loop" in params["query"] or "repeat" in params["query"]
    assert "agent_name" not in params


@pytest.mark.asyncio
async def test_nl_query_interpretation_tool_failures(db_session):
    """Test that NL query interpretation detects 'tool failures' pattern."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    # Test interpretation
    params = service.interpret_nl_query("show me sessions with tool execution failures")

    assert "event_type" in params
    assert "error" in params["event_type"] or "tool" in params["event_type"]


@pytest.mark.asyncio
async def test_nl_query_interpretation_agent_name(db_session):
    """Test that NL query interpretation extracts agent name."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    # Test interpretation with agent name
    params = service.interpret_nl_query("agent my-agent has timeout errors")

    assert "agent_name" in params
    assert params["agent_name"] == "my-agent"


@pytest.mark.asyncio
async def test_nl_query_interpretation_ignores_generic_agent_phrase(db_session):
    """Test that generic references to 'the agent' do not create a name filter."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    params = service.interpret_nl_query("show me sessions where the agent got stuck in a loop")

    assert "agent_name" not in params


@pytest.mark.asyncio
async def test_nl_query_interpretation_tags(db_session):
    """Test that NL query interpretation extracts tags."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    # Test interpretation with tags
    params = service.interpret_nl_query("find sessions with tag:production or tag:critical")

    assert "tags" in params
    assert "production" in params["tags"]
    assert "critical" in params["tags"]


@pytest.mark.asyncio
async def test_nl_query_interpretation_status_filters(db_session):
    """Test that NL query interpretation detects status patterns."""
    from storage.search import SessionSearchService

    service = SessionSearchService(db_session, "tenant-nl")

    # Test failed status
    params = service.interpret_nl_query("show me failed sessions")
    assert "status" in params
    assert params["status"] == "error"

    # Test completed status
    params = service.interpret_nl_query("find completed sessions")
    assert "status" in params
    assert params["status"] == "completed"

    # Timeout should enrich the query but not force an invalid session status
    params = service.interpret_nl_query("sessions with timeout")
    assert "status" not in params
    assert "timeout" in params["query"]
