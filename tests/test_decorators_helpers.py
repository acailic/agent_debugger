"""Focused tests for decorator helpers and standalone decorator flows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_debugger_sdk.core.decorators import _extract_llm_response
from agent_debugger_sdk.core.decorators import _extract_messages
from agent_debugger_sdk.core.decorators import _extract_settings
from agent_debugger_sdk.core.decorators import _extract_tools
from agent_debugger_sdk.core.decorators import _sanitize_arguments
from agent_debugger_sdk.core.decorators import _sanitize_result
from agent_debugger_sdk.core.decorators import _truncate_value
from agent_debugger_sdk.core.decorators import trace_llm
from agent_debugger_sdk.core.decorators import trace_tool
from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer


@pytest.fixture(autouse=True)
def clear_global_buffer():
    buffer = get_event_buffer()
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()
    yield
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()


def test_truncate_value_handles_large_string_list_and_dict():
    long_text = "x" * 1205
    long_list = list(range(150))
    long_dict = {f"k{i}": i for i in range(60)}

    truncated_text = _truncate_value(long_text, max_length=1000)
    truncated_list = _truncate_value(long_list)
    truncated_dict = _truncate_value(long_dict)

    assert truncated_text.endswith("...[truncated]")
    assert len(truncated_list) == 11
    assert truncated_list[-1] == "...[140 more items]"
    assert truncated_dict["__truncated__"] == "40 more keys"


def test_sanitize_arguments_and_result_use_truncation_rules():
    args = ("short", "y" * 1200)
    kwargs = {"payload": {"nested": "z" * 20}}

    sanitized_args = _sanitize_arguments(args, kwargs)
    sanitized_result = _sanitize_result("r" * 6000)

    assert sanitized_args["arg_0"] == "short"
    assert sanitized_args["arg_1"].endswith("...[truncated]")
    assert sanitized_args["payload"]["nested"] == "z" * 20
    assert sanitized_result.endswith("...[truncated]")


def test_extract_messages_tools_and_settings_from_args_and_kwargs():
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"name": "search"}]

    assert _extract_messages((messages,), {}) == messages
    assert _extract_messages((), {"messages": "raw"}) == [{"role": "unknown", "content": "raw"}]
    assert _extract_tools((), {"tools": tools}) == tools
    assert _extract_settings(
        (),
        {"temperature": 0.5, "max_tokens": 100, "ignored": True},
    ) == {"temperature": 0.5, "max_tokens": 100}


def test_extract_llm_response_supports_string_dict_and_object_shapes():
    string_response = _extract_llm_response("hello")
    dict_response = _extract_llm_response(
        {
            "content": "ok",
            "usage": {"input_tokens": 3, "output_tokens": 4},
            "cost_usd": 0.12,
            "tool_calls": [{"name": "lookup"}],
        }
    )

    choice_object = SimpleNamespace(message=SimpleNamespace(content="from choice"))
    usage_object = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(name="search", arguments='{"q":"x"}'),
    )
    object_response = _extract_llm_response(
        SimpleNamespace(
            choices=[choice_object],
            usage=usage_object,
            tool_calls=[tool_call],
        )
    )

    assert string_response == ("hello", {"input_tokens": 0, "output_tokens": 0}, 0.0, [])
    assert dict_response == ("ok", {"input_tokens": 3, "output_tokens": 4}, 0.12, [{"name": "lookup"}])
    assert object_response[0] == "from choice"
    assert object_response[1] == {"input_tokens": 11, "output_tokens": 7}
    assert object_response[3][0]["name"] == "search"


@pytest.mark.asyncio
async def test_trace_tool_standalone_success_emits_call_and_result_events():
    @trace_tool(name="lookup")
    async def lookup(query: str) -> dict[str, str]:
        return {"answer": query.upper()}

    result = await lookup("hello")

    assert result == {"answer": "HELLO"}
    buffer = get_event_buffer()
    session_id = buffer.get_session_ids()[-1]
    events = buffer.get_events(session_id)
    event_types = [event.event_type for event in events]

    assert EventType.AGENT_START in event_types
    assert EventType.TOOL_CALL in event_types
    assert EventType.TOOL_RESULT in event_types
    assert EventType.AGENT_END in event_types


@pytest.mark.asyncio
async def test_trace_llm_standalone_success_records_request_and_response_details():
    @trace_llm(model="gpt-test")
    async def call_llm(messages, tools=None, temperature=None):
        return {
            "content": "done",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "cost_usd": 0.03,
            "tool_calls": [{"name": "search"}],
        }

    result = await call_llm(
        [{"role": "user", "content": "hi"}],
        tools=[{"name": "search"}],
        temperature=0.2,
    )

    assert result["content"] == "done"
    buffer = get_event_buffer()
    session_id = buffer.get_session_ids()[-1]
    events = buffer.get_events(session_id)

    request = next(event for event in events if event.event_type == EventType.LLM_REQUEST)
    response = next(event for event in events if event.event_type == EventType.LLM_RESPONSE)

    assert request.model == "gpt-test"
    assert request.messages == [{"role": "user", "content": "hi"}]
    assert request.tools == [{"name": "search"}]
    assert request.settings == {"temperature": 0.2}
    assert response.content == "done"
    assert response.usage == {"input_tokens": 5, "output_tokens": 2}
    assert response.cost_usd == 0.03
    assert response.tool_calls == [{"name": "search"}]
