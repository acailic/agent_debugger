"""Cross-feature integration tests for Phase 2: Failure Memory + Cost Dashboard.

Tests the complete workflow:
1. Create sessions with events
2. Add fix notes
3. Search for similar sessions
4. Verify cost aggregation includes all data
"""

from __future__ import annotations

from datetime import datetime, timezone

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
    framework: str = "pydantic-ai",
    agent_name: str = "test_agent",
    status: SessionStatus = SessionStatus.ERROR,
    total_cost_usd: float = 0.50,
    total_tokens: int = 1000,
    llm_calls: int = 5,
    tool_calls: int = 10,
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=status,
        total_cost_usd=total_cost_usd,
        total_tokens=total_tokens,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
        config={"mode": "test"},
        tags=["integration"],
    )


def _make_error_event(
    session_id: str,
    error_type: str = "TimeoutError",
    error_message: str = "Connection timeout",
    event_id: str = "event-1",
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="error_occurred",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 26, 10, 1, tzinfo=timezone.utc),
        data={
            "error_type": error_type,
            "error_message": error_message,
        },
    )


def _make_tool_event(
    session_id: str,
    tool_name: str = "search_api",
    event_id: str = "tool-1",
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        data={"tool_name": tool_name},
    )


@pytest.mark.asyncio
async def test_full_workflow_search_annotate_and_cost():
    """End-to-end: create sessions -> add events -> search -> annotate -> verify cost."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Step 1: Create sessions with events
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)

            # Session 1: Timeout error with search_api tool
            s1 = _make_session("wf-session-1", agent_name="weather_agent")
            await repo.create_session(s1)
            await repo.add_event(
                _make_error_event("wf-session-1", "TimeoutError", "Search API timeout after 30s", "wf-e1")
            )
            await repo.add_event(_make_tool_event("wf-session-1", "search_api", "wf-e2"))
            await repo.commit()

            # Session 2: Similar timeout error (different tool)
            s2 = _make_session("wf-session-2", agent_name="data_agent", total_cost_usd=0.75)
            await repo.create_session(s2)
            await repo.add_event(_make_error_event("wf-session-2", "TimeoutError", "Database query timeout", "wf-e3"))
            await repo.add_event(_make_tool_event("wf-session-2", "db_query", "wf-e4"))
            await repo.commit()

            # Session 3: Different error type
            s3 = _make_session(
                "wf-session-3", agent_name="auth_agent", status=SessionStatus.COMPLETED, total_cost_usd=0.25
            )
            await repo.create_session(s3)
            await repo.commit()

        # Step 2: Search for "timeout"
        resp = await client.get("/api/search?q=timeout&limit=10")
        assert resp.status_code == 200
        search_data = resp.json()
        assert search_data["total"] >= 2  # At least sessions 1 and 2

        # Verify timeout sessions are ranked higher than non-timeout
        session_ids = [r["session_id"] for r in search_data["results"]]
        if "wf-session-1" in session_ids and "wf-session-3" in session_ids:
            idx1 = session_ids.index("wf-session-1")
            idx3 = session_ids.index("wf-session-3")
            assert idx1 < idx3, "Timeout session should rank higher than non-timeout session"

        # Step 3: Add fix note to session 1
        resp = await client.post(
            "/api/sessions/wf-session-1/fix-note",
            json={"note": "Fixed by adding retry with exponential backoff"},
        )
        assert resp.status_code == 200
        assert resp.json()["fix_note"] == "Fixed by adding retry with exponential backoff"

        # Step 4: Search again - fix note should be included in results
        resp = await client.get("/api/search?q=timeout&limit=10")
        assert resp.status_code == 200
        search_data = resp.json()
        session1_result = next((r for r in search_data["results"] if r["session_id"] == "wf-session-1"), None)
        assert session1_result is not None
        assert session1_result["fix_note"] == "Fixed by adding retry with exponential backoff"

        # Step 5: Verify cost summary includes all sessions
        resp = await client.get("/api/cost/summary")
        assert resp.status_code == 200
        cost_data = resp.json()
        # The summary should include sessions from this test
        assert cost_data["session_count"] >= 3

        # Step 6: Verify individual session cost
        resp = await client.get("/api/cost/sessions/wf-session-1")
        assert resp.status_code == 200
        assert resp.json()["total_cost_usd"] == 0.50

        resp = await client.get("/api/cost/sessions/wf-session-2")
        assert resp.status_code == 200
        assert resp.json()["total_cost_usd"] == 0.75

        # Step 7: Verify session detail includes fix note
        resp = await client.get("/api/sessions/wf-session-1")
        assert resp.status_code == 200
        assert resp.json()["session"]["fix_note"] == "Fixed by adding retry with exponential backoff"


@pytest.mark.asyncio
async def test_cross_tenant_isolation():
    """Verify that Phase 2 features respect tenant isolation."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test"):
        from api import app_context

        # Create sessions in different tenants via repository
        async with app_context.require_session_maker()() as db_session:
            repo_a = TraceRepository(db_session, tenant_id="integration-tenant-a")
            repo_b = TraceRepository(db_session, tenant_id="integration-tenant-b")

            await repo_a.create_session(_make_session("tenant-a-session", total_cost_usd=1.00))
            await repo_a.add_event(
                _make_error_event("tenant-a-session", "ValueError", "test_agent encountered a value error", "ta-e1")
            )
            await repo_a.commit()

            await repo_b.create_session(_make_session("tenant-b-session", total_cost_usd=2.00))
            await repo_b.add_event(
                _make_error_event("tenant-b-session", "KeyError", "test_agent encountered a key error", "tb-e1")
            )
            await repo_b.commit()

        # Search within tenant A should only see tenant A sessions
        async with app_context.require_session_maker()() as db_session:
            repo_a = TraceRepository(db_session, tenant_id="integration-tenant-a")
            results = await repo_a.search_sessions("test_agent")
            assert len(results) == 1
            assert results[0].id == "tenant-a-session"

            # Cost summary for tenant A
            summary = await repo_a.get_cost_summary()
            assert summary["session_count"] == 1
            assert summary["total_cost_usd"] == 1.00

        # Search within tenant B should only see tenant B sessions
        async with app_context.require_session_maker()() as db_session:
            repo_b = TraceRepository(db_session, tenant_id="integration-tenant-b")
            results = await repo_b.search_sessions("test_agent")
            assert len(results) == 1
            assert results[0].id == "tenant-b-session"

            summary = await repo_b.get_cost_summary()
            assert summary["session_count"] == 1
            assert summary["total_cost_usd"] == 2.00
