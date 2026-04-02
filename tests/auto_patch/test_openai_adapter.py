"""Tests for OpenAIAdapter.

``openai`` is not installed in this environment, so all tests mock the entire
``openai`` module hierarchy via ``sys.modules`` before calling any adapter
method that does ``import openai``.

The tests verify:
1. Non-streaming calls emit LLMRequestEvent + LLMResponseEvent.
2. Tool calls produce individual ToolCallEvents.
3. Streaming calls are passed through with no events emitted.
4. Graceful handling when the Peaky Peek server is unreachable.
5. Async paths mirror sync behaviour.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.openai_adapter import OpenAIAdapter
from agent_debugger_sdk.auto_patch.registry import PatchConfig

# How long to wait for the background transport thread to flush events (seconds)
_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers: fake OpenAI SDK structures
# ---------------------------------------------------------------------------


def _make_fake_response(
    *,
    model: str = "gpt-4o",
    content: str = "Hello!",
    finish_reason: str = "stop",
    tool_calls=None,
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(finish_reason=finish_reason, message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(model=model, choices=[choice], usage=usage)


def _make_fake_tool_call(
    tc_id: str = "call_abc",
    name: str = "get_weather",
    arguments: dict | None = None,
) -> SimpleNamespace:
    if arguments is None:
        arguments = {"location": "London"}
    return SimpleNamespace(
        id=tc_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _build_fake_openai_module() -> types.ModuleType:
    """Return a fake ``openai`` module with *separate* class hierarchies.

    Important: ``FakeOpenAI`` and ``FakeAsyncOpenAI`` must each have their own
    ``chat.completions`` SimpleNamespace so that patching one does not
    accidentally overwrite the other's ``create`` reference.
    """
    fake_openai = types.ModuleType("openai")

    sync_completions = SimpleNamespace(create=MagicMock(name="sync_create"))
    sync_chat = SimpleNamespace(completions=sync_completions)

    async_completions = SimpleNamespace(create=MagicMock(name="async_create"))
    async_chat = SimpleNamespace(completions=async_completions)

    class FakeOpenAI:
        chat = sync_chat

    class FakeAsyncOpenAI:
        chat = async_chat

    fake_openai.OpenAI = FakeOpenAI
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    return fake_openai


def _flush(adapter: OpenAIAdapter) -> None:
    """Block until the adapter's background transport thread has drained its queue."""
    transport = adapter._transport
    # Send sentinel to drain; the worker will exit after processing all pending items.
    transport._queue.put(transport_module._SENTINEL)
    transport._thread.join(timeout=_FLUSH_TIMEOUT)


def _get_trace_events(mock_httpx) -> list[dict]:
    """Extract the JSON bodies of all /api/traces POST calls."""
    events = []
    for c in mock_httpx.post.call_args_list:
        # httpx client.post(url, json=payload)
        url = c.args[0] if c.args else c.kwargs.get("url", "")
        if "/api/traces" in str(url):
            payload = c.kwargs.get("json") or (c.args[1] if len(c.args) > 1 else None)
            if isinstance(payload, dict):
                events.append(payload)
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_session():
    """Reset shared session state between tests."""
    original = transport_module._session_state._id
    yield
    transport_module._session_state._id = original


@pytest.fixture()
def mock_httpx():
    """Patch httpx.Client so SyncTransport never touches the network."""
    with patch("httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.get.side_effect = Exception("no server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "session-openai-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_openai(mock_httpx):
    """Inject a fake ``openai`` module into sys.modules for the test duration."""
    mod = _build_fake_openai_module()
    with patch.dict(sys.modules, {"openai": mod}):
        yield mod


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestOpenAIAdapterIsAvailable:
    def test_returns_true_when_openai_present(self) -> None:
        fake_mod = types.ModuleType("openai")
        with patch.dict(sys.modules, {"openai": fake_mod}):
            adapter = OpenAIAdapter()
            assert adapter.is_available() is True

    def test_returns_false_when_openai_absent(self) -> None:
        with patch.dict(sys.modules, {"openai": None}):
            adapter = OpenAIAdapter()
            assert adapter.is_available() is False


# ---------------------------------------------------------------------------
# Sync path
# ---------------------------------------------------------------------------


class TestOpenAIAdapterSyncPatch:
    def test_patch_replaces_create_method(self, fake_openai, mock_httpx) -> None:
        original_create = fake_openai.OpenAI.chat.completions.create

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_openai.OpenAI.chat.completions.create is not original_create

    def test_unpatch_restores_original(self, fake_openai, mock_httpx) -> None:
        original_sync = fake_openai.OpenAI.chat.completions.create
        original_async = fake_openai.AsyncOpenAI.chat.completions.create

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_openai.OpenAI.chat.completions.create is original_sync
        assert fake_openai.AsyncOpenAI.chat.completions.create is original_async

    def test_unpatch_logs_restore_failures(self, fake_openai, mock_httpx, caplog) -> None:
        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        with patch.dict(sys.modules, {"openai": None}):
            with caplog.at_level(logging.WARNING, logger="agent_debugger.auto_patch"):
                adapter.unpatch()

        assert "OpenAIAdapter: failed to restore original client methods" in caplog.text

    def test_non_streaming_emits_request_and_response(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response(content="Hi!")
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[{"role": "user", "content": "Hello"}])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_
        assert "llm_response" in types_

    def test_tool_calls_emit_tool_call_events(self, fake_openai, mock_httpx) -> None:
        tc = _make_fake_tool_call()
        fake_response = _make_fake_response(finish_reason="tool_calls", tool_calls=[tc])
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "tool_call" in types_

        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "get_weather"
        assert tool_event["arguments"] == {"location": "London"}

    def test_streaming_passthrough_no_events(self, fake_openai, mock_httpx) -> None:
        stream_resp = MagicMock()
        original_create = MagicMock(return_value=stream_resp)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="gpt-4o", messages=[], stream=True)

        _flush(adapter)
        assert result is stream_resp
        assert _get_trace_events(mock_httpx) == []

    def test_server_unreachable_does_not_raise(self, fake_openai, mock_httpx) -> None:
        mock_httpx.post.side_effect = Exception("connection refused")
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="gpt-4o", messages=[])
        assert result is fake_response

    def test_capture_content_false_omits_messages_and_response_text(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response(content="secret")
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=False)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[{"role": "user", "content": "private"}])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["messages"] == []
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["content"] == ""

    def test_response_is_returned_unchanged(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="gpt-4o", messages=[])
        assert result is fake_response

    def test_request_event_contains_model_and_settings(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(
            MagicMock(),
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=1000,
        )

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["model"] == "gpt-4o"
        assert req["settings"]["temperature"] == 0.7
        assert req["settings"]["max_tokens"] == 1000

    def test_response_event_contains_usage_tokens(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response(prompt_tokens=42, completion_tokens=58)
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["usage"]["input_tokens"] == 42
        assert resp["usage"]["output_tokens"] == 58

    def test_response_event_has_duration_ms(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["duration_ms"] > 0

    def test_no_tool_calls_when_finish_reason_is_stop(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response(finish_reason="stop")
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        tool_events = [e for e in sent if e["event_type"] == "tool_call"]
        assert len(tool_events) == 0

    def test_multiple_tool_calls_emit_separate_events(self, fake_openai, mock_httpx) -> None:
        tc1 = _make_fake_tool_call(tc_id="call_1", name="get_weather", arguments={"city": "Paris"})
        tc2 = _make_fake_tool_call(tc_id="call_2", name="get_time", arguments={"timezone": "UTC"})
        fake_response = _make_fake_response(finish_reason="tool_calls", tool_calls=[tc1, tc2])
        original_create = MagicMock(return_value=fake_response)

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="gpt-4o", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        tool_events = [e for e in sent if e["event_type"] == "tool_call"]
        assert len(tool_events) == 2
        tool_names = {e["tool_name"] for e in tool_events}
        assert tool_names == {"get_weather", "get_time"}


# ---------------------------------------------------------------------------
# Async path
# ---------------------------------------------------------------------------


class TestOpenAIAdapterAsyncPatch:
    def test_async_emits_request_and_response(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response(content="async hello")

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="gpt-4o", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_
        assert "llm_response" in types_

    def test_async_streaming_passthrough_no_events(self, fake_openai, mock_httpx) -> None:
        stream_resp = MagicMock()

        async def async_original(self_client, *args, **kwargs):
            return stream_resp

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        result = asyncio.run(wrapper(MagicMock(), model="gpt-4o", messages=[], stream=True))
        assert result is stream_resp
        assert _get_trace_events(mock_httpx) == []

    def test_async_tool_calls_emit_tool_call_events(self, fake_openai, mock_httpx) -> None:
        tc = _make_fake_tool_call(name="search_web", arguments={"query": "python"})
        fake_response = _make_fake_response(finish_reason="tool_calls", tool_calls=[tc])

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="gpt-4o", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "tool_call" in types_
        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "search_web"

    def test_async_server_unreachable_does_not_raise(self, fake_openai, mock_httpx) -> None:
        mock_httpx.post.side_effect = Exception("connection refused")
        fake_response = _make_fake_response()

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        result = asyncio.run(wrapper(MagicMock(), model="gpt-4o", messages=[]))
        assert result is fake_response

    def test_async_request_event_contains_model(self, fake_openai, mock_httpx) -> None:
        fake_response = _make_fake_response()

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = OpenAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="gpt-4o-mini", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["model"] == "gpt-4o-mini"
