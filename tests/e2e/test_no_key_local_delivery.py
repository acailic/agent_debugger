"""E2E — no-key local delivery: SDK with only an endpoint, collector accepts it.

Complements the authenticated scenarios: the SDK is configured with
``init(endpoint=...)`` and NO API key, delivers over real TCP without an
Authorization header, and the local-mode collector (loopback-only) ingests
and persists the trace. The operator then queries it over plain HTTP.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.transport import HttpTransport

from .conftest import E2EServer, run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.fixture
def e2e_sdk_no_key(e2e_server):
    """Point the in-process SDK at the e2e server WITHOUT an API key."""
    from agent_debugger_sdk import config as cfg_mod

    cfg_mod.init(
        endpoint=e2e_server.base_url,
        enabled=True,
    )
    yield
    cfg_mod._global_config = None


async def test_no_key_sdk_delivers_events_queryable_without_auth(
    e2e_server: E2EServer, e2e_sdk_no_key
):
    session_id = f"e2e-no-key-{uuid.uuid4().hex[:8]}"
    tool_event_ids: list[str] = []

    async def scenario():
        async with TraceContext(
            session_id=session_id, agent_name="no_key_agent", framework="custom"
        ) as ctx:
            assert isinstance(ctx._transport, HttpTransport)
            assert "Authorization" not in ctx._transport._headers
            tool_event_ids.append(await ctx.record_tool_call("search", {"query": "no-key-e2e"}))

    await run_scenario(scenario())

    # Local mode: loopback queries need no credentials either.
    async with httpx.AsyncClient(base_url=e2e_server.base_url, timeout=30.0) as client:
        detail = await client.get(f"/api/sessions/{session_id}")
        assert detail.status_code == 200
        session = detail.json()["session"]
        assert session["agent_name"] == "no_key_agent"

        traces = await client.get(f"/api/sessions/{session_id}/traces")
        assert traces.status_code == 200
        trace_ids = {event["id"] for event in traces.json()["traces"]}
        assert tool_event_ids[0] in trace_ids
