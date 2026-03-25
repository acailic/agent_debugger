"""End-to-end integration tests for the LangChain adapter.

These tests call real LLMs via the z.ai endpoint and verify that the
Peaky Peek SDK captures the correct trace events.

Run with:
    python3 -m pytest tests/integration/test_langchain_integration.py -o "addopts=" -v
"""
from __future__ import annotations

import pytest

from agent_debugger_sdk.core.events import EventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_session_id_consistent(events, session_id):
    """All events must belong to the same session."""
    for e in events:
        assert e.session_id == session_id, (
            f"Event {e.name} has session_id={e.session_id}, expected {session_id}"
        )


def _assert_no_errors(events):
    """No unexpected ERROR events should be present."""
    error_events = [e for e in events if e.event_type == EventType.ERROR]
    assert len(error_events) == 0, (
        f"Unexpected error events: {[e.data for e in error_events]}"
    )


def _assert_sequence_non_decreasing(events):
    """Sequence metadata must be monotonically non-decreasing."""
    seqs = [e.metadata.get("sequence", 0) for e in events if hasattr(e, "metadata")]
    for i in range(1, len(seqs)):
        assert seqs[i] >= seqs[i - 1], (
            f"Sequence decreased at position {i}: {seqs[i-1]} -> {seqs[i]}"
        )


def _find_events(events, event_type):
    """Filter events by type."""
    return [e for e in events if e.event_type == event_type]


async def _collect_events(ctx):
    """Non-destructive read of events from context."""
    return [e for e in await ctx.get_events() if hasattr(e, "event_type")]


# ---------------------------------------------------------------------------
# Test 1: Basic LLM call (manual mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_basic_llm_call_manual_mode(zai_chat_model, langchain_session):
    """A single LLM call produces AGENT_START, LLM_REQUEST, LLM_RESPONSE, AGENT_END."""
    from langchain_core.messages import HumanMessage

    ctx = langchain_session.ctx
    handler = langchain_session.handler

    result = await zai_chat_model.ainvoke(
        [HumanMessage(content="Say hello in one word")],
        config={"callbacks": [handler]},
    )

    assert result is not None
    assert len(result.content) > 0

    # Collect events while context is still active (before __aexit__)
    events = await _collect_events(ctx)
    assert len(events) > 0, "No events captured"

    _assert_session_id_consistent(events, events[0].session_id)
    _assert_no_errors(events)
    _assert_sequence_non_decreasing(events)

    # Check event types present (AGENT_END is emitted during __aexit__, so skip it here)
    starts = _find_events(events, EventType.AGENT_START)
    requests = _find_events(events, EventType.LLM_REQUEST)
    responses = _find_events(events, EventType.LLM_RESPONSE)

    assert len(starts) >= 1, "Missing AGENT_START"
    assert len(requests) >= 1, "Missing LLM_REQUEST"
    assert len(responses) >= 1, "Missing LLM_RESPONSE"

    # Verify LLM request fields
    req = requests[0]
    assert req.model, "LLM request missing model"
    assert len(req.messages) > 0, "LLM request missing messages"

    # Verify LLM response fields
    resp = responses[0]
    assert resp.content, "LLM response missing content"
    assert resp.duration_ms > 0, f"LLM response duration_ms should be positive, got {resp.duration_ms}"


# ---------------------------------------------------------------------------
# Test 2: LLM with tool calling (manual mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_with_tool_calling_manual_mode(zai_chat_model, langchain_session):
    """An LLM bound with tools preserves model-returned tool_calls in the trace."""
    from langchain_core.tools import tool

    @tool
    def add_numbers(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b

    ctx = langchain_session.ctx
    handler = langchain_session.handler

    llm_with_tools = zai_chat_model.bind_tools([add_numbers])

    result = await llm_with_tools.ainvoke(
        "What is 2 + 3?",
        config={"callbacks": [handler]},
    )

    assert result is not None
    # When the model decides to call a tool, content may be empty
    has_tool_calls = len(result.tool_calls) > 0
    if not has_tool_calls:
        assert len(result.content) > 0, "Expected content when no tool calls"

    events = await _collect_events(ctx)
    assert len(events) > 0, "No events captured"

    _assert_session_id_consistent(events, events[0].session_id)
    _assert_no_errors(events)
    _assert_sequence_non_decreasing(events)

    # At minimum we should have LLM request/response
    requests = _find_events(events, EventType.LLM_REQUEST)
    responses = _find_events(events, EventType.LLM_RESPONSE)
    assert len(requests) >= 1, "Missing LLM_REQUEST"
    assert len(responses) >= 1, "Missing LLM_RESPONSE"

    response_event = responses[-1]
    # If the model returned tool calls, verify the LLM response captured them.
    # Note: TOOL_CALL events only fire when tools are actually executed (on_tool_start).
    # With bind_tools + ainvoke, the LLM returns tool_calls in its response but
    # the tools are not executed, so we check the LLM response event instead.
    if has_tool_calls:
        assert response_event.tool_calls, "Expected captured tool_calls when model returns them"
        returned_tool_names = {tc["name"] for tc in result.tool_calls}
        captured_tool_names = {tc["name"] for tc in response_event.tool_calls}
        assert "add_numbers" in returned_tool_names, (
            f"Expected add_numbers in model tool calls, got: {returned_tool_names}"
        )
        assert returned_tool_names <= captured_tool_names, (
            f"Captured tool_calls missing names: model={returned_tool_names}, captured={captured_tool_names}"
        )
    else:
        assert response_event.tool_calls == [], "Expected no captured tool_calls when model returned none"


# ---------------------------------------------------------------------------
# Test 3: Multi-step agent chain (manual mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_step_agent_chain_manual_mode(zai_chat_model, langchain_session):
    """An agent with tools produces multiple LLM + tool events via langgraph."""
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool

    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    ctx = langchain_session.ctx
    handler = langchain_session.handler

    agent = create_agent(zai_chat_model, [add, multiply])

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="Add 2 and 3, then multiply the result by 4")]},
        config={"callbacks": [handler]},
    )

    assert result is not None
    messages = result.get("messages", [])
    assert len(messages) > 0

    events = await _collect_events(ctx)
    assert len(events) > 0, "No events captured"

    _assert_session_id_consistent(events, events[0].session_id)
    _assert_no_errors(events)
    _assert_sequence_non_decreasing(events)

    # Should have multiple LLM calls (agent loops)
    requests = _find_events(events, EventType.LLM_REQUEST)
    responses = _find_events(events, EventType.LLM_RESPONSE)
    assert len(requests) >= 2, (
        f"Expected multiple LLM requests for multi-step agent, got {len(requests)}"
    )
    assert len(responses) >= 2, (
        f"Expected multiple LLM responses for multi-step agent, got {len(responses)}"
    )

    # Should have tool calls
    tool_calls = _find_events(events, EventType.TOOL_CALL)
    tool_results = _find_events(events, EventType.TOOL_RESULT)
    assert len(tool_calls) >= 1, "Expected at least one TOOL_CALL"
    assert len(tool_results) >= 1, "Expected at least one TOOL_RESULT"

    # Verify tool names
    tool_names = {tc.tool_name for tc in tool_calls}
    assert tool_names & {"add", "multiply"}, (
        f"Expected add/multiply tools, got: {tool_names}"
    )

    # Note: langgraph may not set parent_run_id on tool callbacks,
    # so parent_id can be None. We just verify tool events exist with correct names.


# ---------------------------------------------------------------------------
# Test 4: Sync callback interop (auto-patch callback primitive)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_handler_interops_with_real_langchain_callbacks(zai_chat_model):
    """The sync callback handler captures events when LangChain invokes it directly."""
    from unittest.mock import MagicMock

    from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import (
        _SyncTracingCallbackHandler,
    )

    captured: list[dict] = []

    fake_transport = MagicMock()
    fake_transport.send_event = lambda d: captured.append(d)

    handler = _SyncTracingCallbackHandler(
        session_id="auto-integ-test",
        transport=fake_transport,
        capture_content=True,
    )

    from langchain_core.messages import HumanMessage

    result = await zai_chat_model.ainvoke(
        [HumanMessage(content="Say hello")],
        config={"callbacks": [handler]},
    )
    assert result is not None and result.content, "Real LLM call should return content"

    event_types = [e.get("event_type") for e in captured]
    assert "llm_request" in event_types, (
        f"Expected llm_request, got: {event_types}"
    )
    assert "llm_response" in event_types, (
        f"Expected llm_response, got: {event_types}"
    )

    # Verify request payload
    request_event = next(e for e in captured if e.get("event_type") == "llm_request")
    assert request_event.get("model") == "glm-4.6", "Request missing model"
    assert request_event.get("session_id") == "auto-integ-test", "Request missing session_id"
    assert request_event.get("messages"), "Request missing messages (capture_content=True)"
    assert request_event.get("settings", {}).get("temperature") == 0, "Request missing temperature"
    assert request_event.get("settings", {}).get("max_tokens") == 500, "Request missing max_tokens"

    # Verify response payload
    response_event = next(e for e in captured if e.get("event_type") == "llm_response")
    assert response_event.get("model") == "glm-4.6", "Response missing model"
    assert response_event.get("content") == result.content, "Response content mismatch"
    assert response_event.get("duration_ms", 0) > 0, "Response should have positive duration_ms"
    assert response_event.get("usage", {}).get("input_tokens", 0) > 0, "Response missing input_tokens"
    assert response_event.get("usage", {}).get("output_tokens", 0) > 0, "Response missing output_tokens"
