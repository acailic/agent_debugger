"""End-to-end integration tests for the PydanticAI adapter.

These tests call the real z.ai endpoint through PydanticAI and verify that the
SDK captures trace events from instrumented agent runs.

Run with:
    python3 -m pytest tests/integration/test_pydantic_ai_integration.py -o "addopts=" -v
"""

from __future__ import annotations

import uuid

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer


def _find_events(events, event_type):
    """Filter events by type."""
    return [event for event in events if event.event_type == event_type]


def _assert_session_id_consistent(events, session_id):
    """All events must belong to the same session."""
    for event in events:
        assert event.session_id == session_id, (
            f"Event {event.name} has session_id={event.session_id}, expected {session_id}"
        )


@pytest.mark.asyncio
async def test_basic_pydantic_ai_run_emits_trace_events(zai_pydantic_model):
    """A single instrumented PydanticAI run emits request/response trace events."""
    from pydantic_ai import Agent

    from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

    session_id = f"pai-integ-{uuid.uuid4().hex[:12]}"
    agent = Agent(zai_pydantic_model)
    adapter = PydanticAIAdapter(
        agent,
        session_id=session_id,
        agent_name="pydantic-basic-integration",
    )
    instrumented = adapter.instrument()

    result = await instrumented.run("Say hello in one word")
    assert result.output, "Expected non-empty model output"

    events = await get_event_buffer().get_events(session_id)
    assert len(events) >= 4, "Expected AGENT_START, LLM_REQUEST, LLM_RESPONSE, AGENT_END"

    _assert_session_id_consistent(events, session_id)

    starts = _find_events(events, EventType.AGENT_START)
    requests = _find_events(events, EventType.LLM_REQUEST)
    responses = _find_events(events, EventType.LLM_RESPONSE)
    ends = _find_events(events, EventType.AGENT_END)

    assert len(starts) >= 1, "Missing AGENT_START"
    assert len(requests) >= 1, "Missing LLM_REQUEST"
    assert len(responses) >= 1, "Missing LLM_RESPONSE"
    assert len(ends) >= 1, "Missing AGENT_END"

    request_event = requests[0]
    assert request_event.model == "glm-4.6", "Expected request to capture the live model name"
    assert request_event.messages == [{"role": "user", "content": "Say hello in one word"}]

    response_event = responses[-1]
    assert response_event.model == "glm-4.6", "Expected response to capture the live model name"
    assert response_event.content == result.output, "Expected traced response content to match run output"
    assert response_event.duration_ms > 0, "Expected positive response duration"
    assert response_event.usage.get("input_tokens", 0) > 0, "Expected non-zero input tokens"
    assert response_event.usage.get("output_tokens", 0) > 0, "Expected non-zero output tokens"


@pytest.mark.asyncio
async def test_pydantic_ai_tool_run_emits_tool_and_multi_step_events(zai_pydantic_model):
    """A tool-using agent emits tool-call, tool-result, and multiple LLM events."""
    from pydantic_ai import Agent

    from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

    session_id = f"pai-tools-{uuid.uuid4().hex[:12]}"
    agent = Agent(
        zai_pydantic_model,
        instructions="Use the provided tools for arithmetic and do not compute results mentally.",
    )

    @agent.tool_plain
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    adapter = PydanticAIAdapter(
        agent,
        session_id=session_id,
        agent_name="pydantic-tool-integration",
    )
    instrumented = adapter.instrument()

    result = await instrumented.run("What is 2 + 3? Use the add tool and answer briefly.")
    assert "5" in result.output, f"Expected final output to mention 5, got: {result.output!r}"

    events = await get_event_buffer().get_events(session_id)
    assert len(events) > 0, "Expected traced events for tool-using run"

    _assert_session_id_consistent(events, session_id)

    requests = _find_events(events, EventType.LLM_REQUEST)
    responses = _find_events(events, EventType.LLM_RESPONSE)
    tool_calls = _find_events(events, EventType.TOOL_CALL)
    tool_results = _find_events(events, EventType.TOOL_RESULT)

    assert len(requests) >= 2, "Expected multiple LLM requests for a tool-using run"
    assert len(responses) >= 2, "Expected multiple LLM responses for a tool-using run"
    assert len(tool_calls) >= 1, "Expected at least one TOOL_CALL"
    assert len(tool_results) >= 1, "Expected at least one TOOL_RESULT"

    tool_call = tool_calls[0]
    assert tool_call.tool_name == "add", f"Expected add tool call, got: {tool_call.tool_name}"
    assert tool_call.arguments == {"a": 2, "b": 3}, f"Expected add tool arguments, got: {tool_call.arguments}"

    tool_result = tool_results[0]
    assert tool_result.tool_name == "add", f"Expected add tool result, got: {tool_result.tool_name}"
    assert tool_result.result == 5, f"Expected tool result to be 5, got: {tool_result.result!r}"

    tool_response = next(
        (response for response in responses if response.tool_calls),
        None,
    )
    assert tool_response is not None, "Expected an LLM response with tool_calls"
    assert tool_response.tool_calls[0]["name"] == "add", f"Expected add in tool_calls, got: {tool_response.tool_calls}"

    follow_up_request = next(
        (request for request in requests if request.messages and request.messages[-1]["role"] == "tool"),
    )
    assert follow_up_request.messages[-1]["name"] == "add", (
        f"Expected tool follow-up request, got: {follow_up_request.messages}"
    )
