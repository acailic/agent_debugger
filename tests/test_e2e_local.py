"""End-to-end integration test for local mode."""
import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.config import init
from agent_debugger_sdk.core.context import TraceContext, configure_event_pipeline
from collector.buffer import EventBuffer


@pytest.mark.asyncio
async def test_full_local_flow():
    """SDK records events → API returns them."""
    # Setup - local mode
    init()  # local mode by default
    buffer = EventBuffer()

    # Configure the event pipeline for local mode persistence
    from api.main import _persist_event, _persist_session_start
    configure_event_pipeline(
        buffer,
        persist_event=_persist_event,
        persist_session_start=_persist_session_start,
    )

    # Import app after init
    from api.main import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First create a session via API
        session_resp = await client.post("/api/sessions", json={
            "agent_name": "test_agent",
            "framework": "test",
            "config": {},
            "tags": []
        })
        assert session_resp.status_code == 201
        session_data = session_resp.json()
        session_id = session_data["id"]

        # Record events via SDK with existing session ID
        async with TraceContext(session_id=session_id, agent_name="test_agent", framework="test") as ctx:
            await ctx.record_tool_call("search", {"query": "test"})
            await ctx.record_tool_result("search", {"results": []}, duration_ms=50)

        # Query via API
        resp = await client.get(f"/api/sessions/{session_id}/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("traces", [])) >= 2  # at least tool_call + tool_result


@pytest.mark.asyncio
async def test_health_endpoint_works():
    """Health check should return ok."""
    from api.main import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sessions_list():
    """Sessions list endpoint should work."""
    from api.main import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data or isinstance(data, list)
