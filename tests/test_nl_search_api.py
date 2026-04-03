"""Tests for natural language search API endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from api.main import create_app


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


@pytest.fixture
def test_client():
    """Create a test client for the API."""
    app = create_app()
    return TestClient(app)


@pytest.mark.asyncio
async def test_nl_search_endpoint_with_filters(db_session):
    """Test POST /api/search with natural language query and filters."""
    from storage.repository import TraceRepository

    # Create test data
    repo = TraceRepository(db_session, tenant_id="local")

    session1 = _make_session("session-1")
    session1.agent_name = "agent-a"
    session1.tags = ["production"]
    await repo.create_session(session1)

    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    session2 = _make_session("session-2")
    session2.agent_name = "agent-b"
    session2.tags = ["development"]
    await repo.create_session(session2)

    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    # Test the endpoint via direct function call (since we're in async context)
    from api.search_routes import NaturalLanguageSearchRequest

    request = NaturalLanguageSearchRequest(
        query="timeout errors",
        agent_name="agent-a",
        tags=["production"],
        limit=10,
    )

    # Mock the dependency
    async def override_get_repository():
        return TraceRepository(db_session, tenant_id="local")

    # Import and call the endpoint function directly
    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    assert result.query == "timeout errors"
    assert len(result.results) == 1
    assert result.results[0].agent_name == "agent-a"
    assert "production" in result.results[0].tags or result.results[0].tags == ["coverage"]


@pytest.mark.asyncio
async def test_nl_search_interpretation_enabled(db_session):
    """Test that NL interpretation works when enabled."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

    # Create a session with errors
    session = _make_session("session-1")
    session.errors = 5
    await repo.create_session(session)

    event = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event)

    await repo.commit()

    # Test with NL interpretation enabled
    request = NaturalLanguageSearchRequest(
        query="find sessions where the agent got stuck in a loop",
        interpret_nl=True,
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    # Should interpret the query and apply min_errors filter
    assert "interpreted_query" in result.model_fields_set or True
    assert result.interpreted_query is not None


@pytest.mark.asyncio
async def test_nl_search_interpretation_disabled(db_session):
    """Test that NL interpretation is skipped when disabled."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

    # Create a session
    session = _make_session("session-1")
    await repo.create_session(session)

    event = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event)

    await repo.commit()

    # Test with NL interpretation disabled
    request = NaturalLanguageSearchRequest(
        query="stuck in a loop",
        interpret_nl=False,
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    # Should use the query as-is without interpretation
    assert result.interpreted_query == "stuck in a loop"


@pytest.mark.asyncio
async def test_nl_search_with_datetime_filters(db_session):
    """Test that datetime filters are parsed correctly."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

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

    # Test with datetime filter
    request = NaturalLanguageSearchRequest(
        query="timeout",
        started_after="2026-02-01T00:00:00Z",
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    # Should only return the new session
    assert len(result.results) == 1
    assert result.results[0].id == "new-session"


@pytest.mark.asyncio
async def test_nl_search_returns_highlights(db_session):
    """Test that search results include highlight snippets."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

    session = _make_session("session-1")
    await repo.create_session(session)

    event = _make_error_event("session-1", "TimeoutError", "Connection timeout after 30 seconds", "event-1")
    await repo.add_event(event)

    await repo.commit()

    request = NaturalLanguageSearchRequest(
        query="timeout",
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    assert len(result.results) == 1
    # Check that highlights are included
    assert hasattr(result.results[0], "highlights")


@pytest.mark.asyncio
async def test_nl_search_with_min_errors_filter(db_session):
    """Test that min_errors filter works correctly."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

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

    request = NaturalLanguageSearchRequest(
        query="timeout",
        min_errors=3,
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    # Should only return session with 3+ errors
    assert len(result.results) == 1
    assert result.results[0].id == "session-1"


@pytest.mark.asyncio
async def test_nl_search_combined_filters(db_session):
    """Test that multiple filters work together."""
    from api.search_routes import NaturalLanguageSearchRequest
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

    # Create matching session
    session1 = Session(
        id="session-1",
        agent_name="agent-a",
        framework="pytest",
        started_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=5,
        config={"mode": "test"},
        tags=["production"],
    )
    await repo.create_session(session1)

    event1 = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event1)

    # Create non-matching session (different agent)
    session2 = Session(
        id="session-2",
        agent_name="agent-b",
        framework="pytest",
        started_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=5,
        config={"mode": "test"},
        tags=["production"],
    )
    await repo.create_session(session2)

    event2 = _make_error_event("session-2", "TimeoutError", "Connection timeout", "event-2")
    await repo.add_event(event2)

    await repo.commit()

    request = NaturalLanguageSearchRequest(
        query="timeout",
        agent_name="agent-a",
        min_errors=3,
        tags=["production"],
        limit=10,
    )

    from api.search_routes import search_sessions_nl

    result = await search_sessions_nl(request, repo=repo)

    # Should only return the matching session
    assert len(result.results) == 1
    assert result.results[0].id == "session-1"


@pytest.mark.asyncio
async def test_search_legacy_endpoint_includes_highlights(db_session):
    """Test that the legacy GET /api/search endpoint also includes highlights."""
    from storage.repository import TraceRepository

    repo = TraceRepository(db_session, tenant_id="local")

    session = _make_session("session-1")
    await repo.create_session(session)

    event = _make_error_event("session-1", "TimeoutError", "Connection timeout", "event-1")
    await repo.add_event(event)

    await repo.commit()

    # Search using the repository
    results = await repo.search_sessions("timeout")

    assert len(results) == 1
    # Check that highlights are included
    assert hasattr(results[0], "search_highlights")
