"""Tests for search API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import Session, SessionStatus
from api.main import create_app
from storage import TraceRepository


def _make_session(
    session_id: str,
    framework: str = "pytest",
    agent_name: str = "test_agent",
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_cost_usd=0.50,
        total_tokens=1000,
        llm_calls=5,
        tool_calls=10,
        config={"mode": "test"},
        tags=["search-test"],
    )


@pytest.mark.asyncio
async def test_search_sessions():
    """Test session search endpoint."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed database with test sessions
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("search-session-1", agent_name="weather_agent"))
            await repo.create_session(_make_session("search-session-2", agent_name="search_agent"))
            await db_session.commit()

        # Search for sessions
        resp = await client.get("/api/search?q=weather&limit=10")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "query" in data
        assert "total" in data
        assert "results" in data
        assert data["query"] == "weather"
        assert isinstance(data["results"], list)

        # Verify result structure
        if len(data["results"]) > 0:
            result = data["results"][0]
            assert "session_id" in result
            assert "agent_name" in result
            assert "framework" in result
            assert "status" in result
            assert "similarity" in result


@pytest.mark.asyncio
async def test_add_fix_note():
    """Test adding a fix note to a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed database with a test session
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("fix-note-session"))
            await db_session.commit()

        # Add a fix note
        resp = await client.post(
            "/api/sessions/fix-note-session/fix-note",
            json={"note": "Fixed by updating the configuration"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify response
        assert data["session_id"] == "fix-note-session"
        assert data["fix_note"] == "Fixed by updating the configuration"

        # Verify the note was persisted
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.get_session("fix-note-session")
            assert session is not None
            assert session.fix_note == "Fixed by updating the configuration"


@pytest.mark.asyncio
async def test_add_fix_note_not_found():
    """Test adding a fix note to a nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to add a fix note to a nonexistent session
        resp = await client.post(
            "/api/sessions/nonexistent-session/fix-note",
            json={"note": "This should fail"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_session_detail_includes_fix_note():
    """Test that session detail responses include persisted fix notes."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = _make_session("session-with-fix-note")
            session.fix_note = "Fixed by updating retry backoff"
            await repo.create_session(session)
            await db_session.commit()

        resp = await client.get("/api/sessions/session-with-fix-note")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["fix_note"] == "Fixed by updating retry backoff"


@pytest.mark.asyncio
async def test_search_sessions_with_status_filter():
    """Test session search with status filter."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed database with sessions of different statuses
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(
                Session(
                    id="error-session-1",
                    agent_name="error_agent",
                    framework="pytest",
                    started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
                    status=SessionStatus.ERROR,
                    total_cost_usd=0.50,
                    config={},
                    tags=[],
                )
            )
            await db_session.commit()

        # Search for sessions with error status
        resp = await client.get("/api/search?q=error&status=error&limit=10")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert data["query"] == "error"
        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_search_no_matching_sessions():
    """Test search returns empty results when no sessions match the query."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/search?q=xyznonexistentterm12345&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []


@pytest.mark.asyncio
async def test_search_query_too_short():
    """Test search rejects queries shorter than minimum length."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Single character query (below min_length=2)
        resp = await client.get("/api/search?q=x&limit=10")
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_fix_note_empty_body():
    """Test that empty fix note is rejected by validation."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty string note
        resp = await client.post(
            "/api/sessions/some-session/fix-note",
            json={"note": ""},
        )
        assert resp.status_code == 422  # Validation error for min_length=1


@pytest.mark.asyncio
async def test_fix_note_too_long():
    """Test that fix note exceeding max length is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Note exceeding 2000 chars
        long_note = "x" * 2001
        resp = await client.post(
            "/api/sessions/some-session/fix-note",
            json={"note": long_note},
        )
        assert resp.status_code == 422  # Validation error for max_length=2000


@pytest.mark.asyncio
async def test_fix_note_update_via_api():
    """Test that updating a fix note overwrites the previous one."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("update-fix-session"))
            await db_session.commit()

        # Add first note
        resp1 = await client.post(
            "/api/sessions/update-fix-session/fix-note",
            json={"note": "First fix attempt"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["fix_note"] == "First fix attempt"

        # Update with second note
        resp2 = await client.post(
            "/api/sessions/update-fix-session/fix-note",
            json={"note": "Updated fix that actually worked"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["fix_note"] == "Updated fix that actually worked"

        # Verify persisted
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.get_session("update-fix-session")
            assert session.fix_note == "Updated fix that actually worked"
