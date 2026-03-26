import pytest

from agent_debugger_sdk.config import init
from agent_debugger_sdk.core.context import TraceContext


@pytest.mark.asyncio
async def test_emit_event_does_not_raise_on_persist_failure():
    """If persist hook raises, SDK should log warning, not crash."""

    async def failing_persister(event):
        raise ConnectionError("Collector is down")

    from agent_debugger_sdk.core.context import configure_event_pipeline

    configure_event_pipeline(None, persist_event=failing_persister)

    async with TraceContext(agent_name="test", framework="test") as ctx:
        # This should NOT raise
        event_id = await ctx.record_tool_call("some_tool", {"query": "test"})
        assert event_id is not None


@pytest.mark.asyncio
async def test_disabled_sdk_records_nothing():
    """When SDK is disabled, record methods should be no-ops."""
    init(enabled=False)
    async with TraceContext(agent_name="test", framework="test") as ctx:
        event_id = await ctx.record_tool_call("some_tool", {"query": "test"})
        # Should return an ID but not persist
        assert event_id is not None
