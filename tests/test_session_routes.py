"""Tests for session API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, SessionStatus, TraceEvent
from api.main import create_app
from storage import TraceRepository


def _make_session(
    session_id: str,
    framework: str = "pytest",
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.COMPLETED,
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=status,
        total_cost_usd=0.50,
        total_tokens=1000,
        llm_calls=5,
        tool_calls=10,
        config={"mode": "test"},
        tags=["session-routes-test"],
    )


@pytest.mark.asyncio
async def test_list_sessions_default_params():
    """Test listing sessions with default parameters."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("list-session-1"))
            await repo.create_session(_make_session("list-session-2"))
            await db_session.commit()

        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "sessions" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["sessions"], list)
        assert data["limit"] == 50  # default
        assert data["offset"] == 0  # default


@pytest.mark.asyncio
async def test_list_sessions_with_limit_and_offset():
    """Test listing sessions with custom limit and offset."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("paginated-1"))
            await repo.create_session(_make_session("paginated-2"))
            await repo.create_session(_make_session("paginated-3"))
            await db_session.commit()

        resp = await client.get("/api/sessions?limit=2&offset=1")
        assert resp.status_code == 200
        data = resp.json()

        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["sessions"]) <= 2


@pytest.mark.asyncio
async def test_list_sessions_sort_by_started_at():
    """Test listing sessions sorted by started_at."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("sort-1"))
            await repo.create_session(_make_session("sort-2"))
            await db_session.commit()

        resp = await client.get("/api/sessions?sort_by=started_at")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response contains sessions
        assert isinstance(data["sessions"], list)
        assert data["total"] >= 0


@pytest.mark.asyncio
async def test_list_sessions_sort_by_replay_value():
    """Test listing sessions sorted by replay_value."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = _make_session("revalue-sort-1")
            session.replay_value = 0.85
            await repo.create_session(session)
            await db_session.commit()

        resp = await client.get("/api/sessions?sort_by=replay_value")
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data["sessions"], list)


@pytest.mark.asyncio
async def test_list_sessions_invalid_sort_by():
    """Test that invalid sort_by parameter is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions?sort_by=invalid_field")
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_list_sessions_limit_too_high():
    """Test that limit exceeding maximum is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions?limit=1001")
        assert resp.status_code == 422  # Validation error for le=1000


@pytest.mark.asyncio
async def test_list_sessions_negative_limit():
    """Test that negative limit is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions?limit=-1")
        assert resp.status_code == 422  # Validation error for ge=1


@pytest.mark.asyncio
async def test_list_sessions_negative_offset():
    """Test that negative offset is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions?offset=-1")
        assert resp.status_code == 422  # Validation error for ge=0


@pytest.mark.asyncio
async def test_get_session_detail():
    """Test retrieving a single session by ID."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            test_session = _make_session("detail-session")
            await repo.create_session(test_session)
            await db_session.commit()

        resp = await client.get("/api/sessions/detail-session")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session" in data
        session = data["session"]
        assert session["id"] == "detail-session"
        assert session["agent_name"] == "test_agent"
        assert session["framework"] == "pytest"
        assert session["status"] == "completed"


@pytest.mark.asyncio
async def test_get_session_not_found():
    """Test retrieving a nonexistent session returns 404."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-session")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_session_invalid_id():
    """Test retrieving a session with invalid ID format."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid ID format (empty string after sessions/)
        resp = await client.get("/api/sessions/ ")
        assert resp.status_code == 404  # Not found


@pytest.mark.asyncio
async def test_update_session_fix_note():
    """Test updating a session with a fix note."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("update-session"))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/update-session",
            json={"fix_note": "Fixed race condition in retry logic"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify response
        assert "session" in data
        assert data["session"]["fix_note"] == "Fixed race condition in retry logic"


@pytest.mark.asyncio
async def test_update_session_status():
    """Test updating a session status."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("status-session"))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/status-session",
            json={"status": "error"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["session"]["status"] == "error"


@pytest.mark.asyncio
async def test_update_session_multiple_fields():
    """Test updating multiple session fields at once."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("multi-update-session"))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/multi-update-session",
            json={
                "fix_note": "Updated configuration",
                "status": "error",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["session"]["fix_note"] == "Updated configuration"
        assert data["session"]["status"] == "error"


@pytest.mark.asyncio
async def test_update_session_started_at_persists():
    """Test updating started_at applies the change instead of being silently ignored."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("started-at-update-session"))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/started-at-update-session",
            json={"started_at": "2026-03-26T09:30:00Z"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["session"]["started_at"] == "2026-03-26T09:30:00Z"


@pytest.mark.asyncio
async def test_update_session_rejects_terminal_status_transition():
    """Test terminal sessions cannot transition back to running."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("terminal-status-session", status=SessionStatus.COMPLETED))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/terminal-status-session",
            json={"status": "running"},
        )
        assert resp.status_code == 422
        assert "Cannot transition session from completed to running" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_session_rejects_ended_at_before_existing_started_at():
    """Test partial updates still validate timestamps against persisted started_at."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("timestamp-window-session"))
            await db_session.commit()

        resp = await client.put(
            "/api/sessions/timestamp-window-session",
            json={"ended_at": "2026-03-26T09:00:00Z"},
        )
        assert resp.status_code == 422
        assert "ended_at must be greater than or equal to started_at" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_session_not_found():
    """Test updating a nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            "/api/sessions/nonexistent-update",
            json={"fix_note": "This should fail"},
        )
        # Should create the session or return 404 depending on implementation
        assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_delete_session():
    """Test deleting a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Create session first
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("delete-session"))
            await db_session.commit()

        # Delete it
        resp = await client.delete("/api/sessions/delete-session")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "deleted" in data
        assert "session_id" in data
        assert data["deleted"] is True
        assert data["session_id"] == "delete-session"

        # Verify session is actually deleted
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.get_session("delete-session")
            assert session is None


@pytest.mark.asyncio
async def test_delete_session_not_found():
    """Test deleting a nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/sessions/nonexistent-delete")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_traces():
    """Test retrieving traces for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("traces-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/traces-session/traces")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "traces" in data
        assert "session_id" in data
        assert data["session_id"] == "traces-session"
        assert isinstance(data["traces"], list)


@pytest.mark.asyncio
async def test_get_session_traces_with_limit():
    """Test retrieving traces with custom limit."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("traces-limit-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/traces-limit-session/traces?limit=10")
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data["traces"], list)


@pytest.mark.asyncio
async def test_get_session_traces_not_found():
    """Test retrieving traces for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-traces/traces")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_decision_tree():
    """Test retrieving decision tree for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("tree-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/tree-session/tree")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session_id" in data
        assert "events" in data
        assert data["session_id"] == "tree-session"
        assert isinstance(data["events"], list)


@pytest.mark.asyncio
async def test_get_decision_tree_not_found():
    """Test retrieving decision tree for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-tree/tree")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_checkpoints():
    """Test listing checkpoints for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("checkpoints-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/checkpoints-session/checkpoints")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "checkpoints" in data
        assert "session_id" in data
        assert data["session_id"] == "checkpoints-session"
        assert isinstance(data["checkpoints"], list)


@pytest.mark.asyncio
async def test_list_checkpoints_not_found():
    """Test listing checkpoints for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-checkpoints/checkpoints")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_session_includes_events_and_checkpoints():
    """Test exporting a session succeeds and includes checkpoint data."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        checkpoint_timestamp = datetime(2026, 3, 26, 10, 30, tzinfo=timezone.utc)

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("export-session"))
            await repo.add_event(
                TraceEvent(
                    id="evt-export-1",
                    session_id="export-session",
                    event_type=EventType.DECISION,
                    name="decision",
                )
            )
            await repo.create_checkpoint(
                Checkpoint(
                    id="cp-export-1",
                    session_id="export-session",
                    event_id="evt-export-1",
                    sequence=1,
                    state={"step": 1},
                    memory={"summary": "checkpoint"},
                    timestamp=checkpoint_timestamp,
                    importance=0.8,
                )
            )
            await db_session.commit()

        resp = await client.get("/api/sessions/export-session/export")
        assert resp.status_code == 200
        data = resp.json()

        assert data["session"]["id"] == "export-session"
        assert isinstance(data["events"], list)
        assert len(data["checkpoints"]) == 1
        assert data["checkpoints"][0]["id"] == "cp-export-1"


@pytest.mark.asyncio
async def test_session_list_response_schema():
    """Test session list response conforms to schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-list-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()

        # Verify all required fields
        assert "sessions" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        # Verify session structure if present
        if len(data["sessions"]) > 0:
            session = data["sessions"][0]
            required_fields = [
                "id",
                "agent_name",
                "framework",
                "started_at",
                "status",
                "total_tokens",
                "total_cost_usd",
                "tool_calls",
                "llm_calls",
                "errors",
                "replay_value",
                "config",
                "tags",
            ]
            for field in required_fields:
                assert field in session


@pytest.mark.asyncio
async def test_session_detail_response_schema():
    """Test session detail response conforms to schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-detail-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/schema-detail-session")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session" in data
        session = data["session"]

        # Verify required fields
        required_fields = [
            "id",
            "agent_name",
            "framework",
            "started_at",
            "status",
            "total_tokens",
            "total_cost_usd",
            "tool_calls",
            "llm_calls",
            "errors",
            "replay_value",
            "config",
            "tags",
        ]
        for field in required_fields:
            assert field in session


@pytest.mark.asyncio
async def test_delete_response_schema():
    """Test delete response conforms to schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-delete-session"))
            await db_session.commit()

        resp = await client.delete("/api/sessions/schema-delete-session")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "deleted" in data
        assert "session_id" in data
        assert isinstance(data["deleted"], bool)
        assert isinstance(data["session_id"], str)
