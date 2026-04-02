"""Tests for trace API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
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
        tags=["trace-test"],
    )


def _make_event(
    session_id: str,
    event_type: EventType,
    name: str = "test_event",
    **kwargs,
) -> TraceEvent:
    """Factory for creating test events."""
    data = kwargs.pop("data", {})
    metadata = kwargs.pop("metadata", {})
    return TraceEvent(
        session_id=session_id,
        parent_id=kwargs.pop("parent_id", None),
        event_type=event_type,
        name=name,
        data=data,
        metadata=metadata,
        importance=kwargs.pop("importance", 0.5),
        upstream_event_ids=kwargs.pop("upstream_event_ids", []),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_get_trace_bundle():
    """Test retrieving a trace bundle for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("trace-bundle-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/trace-bundle-session/trace")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session" in data
        assert "events" in data
        assert "checkpoints" in data
        assert "tree" in data
        assert "analysis" in data

        # Verify session data
        assert data["session"]["id"] == "trace-bundle-session"

        # Verify events and checkpoints are lists
        assert isinstance(data["events"], list)
        assert isinstance(data["checkpoints"], list)

        # Verify tree structure (may be None if no events)
        assert data["tree"] is None or isinstance(data["tree"], list)


@pytest.mark.asyncio
async def test_get_trace_bundle_not_found():
    """Test retrieving trace bundle for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-trace-bundle/trace")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_session_analysis():
    """Test retrieving session analysis."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("analysis-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/analysis-session/analysis")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session_id" in data
        assert "analysis" in data
        assert data["session_id"] == "analysis-session"
        assert isinstance(data["analysis"], dict)


@pytest.mark.asyncio
async def test_get_session_analysis_not_found():
    """Test retrieving analysis for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-analysis/analysis")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_session_live_summary():
    """Test retrieving live summary for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("live-summary-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/live-summary-session/live")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session_id" in data
        assert "live_summary" in data
        assert data["session_id"] == "live-summary-session"
        assert isinstance(data["live_summary"], dict)


@pytest.mark.asyncio
async def test_get_session_live_summary_not_found():
    """Test retrieving live summary for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-live/live")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_search_traces_default_params():
    """Test searching traces with default parameters."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("search-session"))
            await repo.add_event(
                _make_event("search-session", EventType.TOOL_CALL, name="search_tool", data={"query": "test"})
            )
            await db_session.commit()

        resp = await client.get("/api/traces/search?query=test")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "query" in data
        assert "total" in data
        assert "results" in data
        assert data["query"] == "test"
        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_search_traces_with_session_filter():
    """Test searching traces filtered by session ID."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("trace-search-session-1"))
            await repo.add_event(
                _make_event("trace-search-session-1", EventType.TOOL_CALL, name="tool_1", data={"action": "search"})
            )
            await repo.create_session(_make_session("trace-search-session-2"))
            await repo.add_event(
                _make_event("trace-search-session-2", EventType.TOOL_CALL, name="tool_2", data={"action": "search"})
            )
            await db_session.commit()

        resp = await client.get("/api/traces/search?query=search&session_id=trace-search-session-1")
        assert resp.status_code == 200
        data = resp.json()

        assert data["session_id"] == "trace-search-session-1"
        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_search_traces_with_event_type_filter():
    """Test searching traces filtered by event type."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("type-filter-session"))
            await repo.add_event(_make_event("type-filter-session", EventType.TOOL_CALL, name="tool_event"))
            await db_session.commit()

        resp = await client.get("/api/traces/search?query=tool&event_type=TOOL_CALL")
        assert resp.status_code == 200
        data = resp.json()

        assert data["event_type"] == "TOOL_CALL"
        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_search_traces_with_limit():
    """Test searching traces with custom limit."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/traces/search?query=test&limit=10")
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_search_traces_empty_query():
    """Test that empty query is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/traces/search?query=")
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_search_traces_limit_too_high():
    """Test that limit exceeding maximum is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/traces/search?query=test&limit=1001")
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_agent_baseline_no_sessions():
    """Test getting agent baseline when no sessions exist."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/nonexistent-agent/baseline")
        assert resp.status_code == 200
        data = resp.json()

        assert "agent_name" in data
        assert "session_count" in data
        assert data["agent_name"] == "nonexistent-agent"
        assert data["session_count"] == 0


@pytest.mark.asyncio
async def test_get_agent_drift_no_sessions():
    """Test getting agent drift when no sessions exist."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/nonexistent-agent/drift")
        assert resp.status_code == 200
        data = resp.json()

        assert "agent_name" in data
        assert "alerts" in data
        assert data["agent_name"] == "nonexistent-agent"
        assert isinstance(data["alerts"], list)


@pytest.mark.asyncio
async def test_get_session_alerts():
    """Test retrieving alerts for a session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("alerts-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/alerts-session/alerts")
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "session_id" in data
        assert "alerts" in data
        assert "total" in data
        assert data["session_id"] == "alerts-session"
        assert isinstance(data["alerts"], list)
        assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_get_session_alerts_not_found():
    """Test retrieving alerts for nonexistent session."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions/nonexistent-alerts/alerts")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_session_alerts_with_limit():
    """Test retrieving alerts with custom limit."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("alerts-limit-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/alerts-limit-session/alerts?limit=10")
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data["alerts"], list)
        assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_get_alert_by_id_not_found():
    """Test retrieving a single alert that doesn't exist."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/alerts/nonexistent-alert-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trace_bundle_response_schema():
    """Test trace bundle response conforms to schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-trace-session"))
            await db_session.commit()

        resp = await client.get("/api/sessions/schema-trace-session/trace")
        assert resp.status_code == 200
        data = resp.json()

        # Verify all top-level fields
        expected_keys = {"session", "events", "checkpoints", "tree", "analysis"}
        assert set(data.keys()) == expected_keys

        # Verify session structure
        session = data["session"]
        required_session_fields = [
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
        ]
        for field in required_session_fields:
            assert field in session


@pytest.mark.asyncio
async def test_search_response_schema():
    """Test search response conforms to schema."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session("schema-search-session"))
            await db_session.commit()

        resp = await client.get("/api/traces/search?query=test")
        assert resp.status_code == 200
        data = resp.json()

        # Verify all expected fields
        expected_keys = {"query", "session_id", "event_type", "total", "results"}
        assert set(data.keys()) == expected_keys

        # Verify types
        assert isinstance(data["query"], str)
        assert isinstance(data["total"], int)
        assert isinstance(data["results"], list)


@pytest.mark.asyncio
async def test_get_trace_bundle_rollback_on_analysis_error():
    """Test that get_trace_bundle rolls back transaction when analyze_session raises an exception."""
    from api import app_context

    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session("rollback-trace-session"))
        await db_session.commit()

        # Mock analyze_session to raise an exception and track rollback calls
        rollback_called = False
        original_rollback = repo.rollback

        async def mock_rollback():
            nonlocal rollback_called
            rollback_called = True
            await original_rollback()

        repo.rollback = mock_rollback

        # Mock analyze_session to raise an exception
        with patch("api.trace_routes.analyze_session", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.side_effect = RuntimeError("Analysis failed")

            # Make the request
            from api.trace_routes import get_trace_bundle

            with pytest.raises(RuntimeError, match="Analysis failed"):
                await get_trace_bundle("rollback-trace-session", repo)

            # Verify rollback was called
            assert rollback_called, "rollback() should have been called when analyze_session failed"


@pytest.mark.asyncio
async def test_get_session_analysis_rollback_on_analysis_error():
    """Test that get_session_analysis rolls back transaction when analyze_session raises an exception."""
    from api import app_context

    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session("rollback-analysis-session"))
        await db_session.commit()

        # Track rollback calls
        rollback_called = False
        original_rollback = repo.rollback

        async def mock_rollback():
            nonlocal rollback_called
            rollback_called = True
            await original_rollback()

        repo.rollback = mock_rollback

        # Mock analyze_session to raise an exception
        with patch("api.trace_routes.analyze_session", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.side_effect = ValueError("Analysis error")

            # Make the request
            from api.trace_routes import get_session_analysis

            with pytest.raises(ValueError, match="Analysis error"):
                await get_session_analysis("rollback-analysis-session", repo)

            # Verify rollback was called
            assert rollback_called, "rollback() should have been called when analyze_session failed"


@pytest.mark.asyncio
async def test_get_trace_bundle_commits_on_success():
    """Test that get_trace_bundle commits transaction when analyze_session succeeds."""
    from api import app_context

    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session("commit-trace-session"))
        await db_session.commit()

        # Track commit calls
        commit_called = False
        original_commit = repo.commit

        async def mock_commit():
            nonlocal commit_called
            commit_called = True
            await original_commit()

        repo.commit = mock_commit

        # Make the request - should succeed
        from api.trace_routes import get_trace_bundle

        result = await get_trace_bundle("commit-trace-session", repo)

        # Verify commit was called
        assert commit_called, "commit() should have been called when analyze_session succeeded"
        assert result is not None


@pytest.mark.asyncio
async def test_get_session_analysis_commits_on_success():
    """Test that get_session_analysis commits transaction when analyze_session succeeds."""
    from api import app_context

    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(_make_session("commit-analysis-session"))
        await db_session.commit()

        # Track commit calls
        commit_called = False
        original_commit = repo.commit

        async def mock_commit():
            nonlocal commit_called
            commit_called = True
            await original_commit()

        repo.commit = mock_commit

        # Make the request - should succeed
        from api.trace_routes import get_session_analysis

        result = await get_session_analysis("commit-analysis-session", repo)

        # Verify commit was called
        assert commit_called, "commit() should have been called when analyze_session succeeded"
        assert result is not None
