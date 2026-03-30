"""Tests for AnthropicAdapter.

``anthropic`` is not installed in this environment, so all tests mock the
entire ``anthropic`` module hierarchy via ``sys.modules`` before calling any
adapter method that does ``import anthropic``.

The tests verify:
1. Non-streaming calls emit LLMRequestEvent + LLMResponseEvent.
2. Tool-use blocks produce individual ToolCallEvents.
3. Streaming calls are passed through with no events emitted.
4. Graceful handling when the Peaky Peek server is unreachable.
5. Async paths mirror sync behaviour.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.anthropic_adapter import AnthropicAdapter
from agent_debugger_sdk.auto_patch.registry import PatchConfig

# How long to wait for the background transport thread to flush events (seconds)
_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers: fake Anthropic SDK structures
# ---------------------------------------------------------------------------


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(
    tool_id: str = "toolu_01",
    name: str = "get_weather",
    input_data: dict | None = None,
) -> SimpleNamespace:
    if input_data is None:
        input_data = {"location": "Paris"}
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=input_data)


def _make_fake_response(
    *,
    model: str = "claude-3-5-sonnet-20241022",
    content_blocks=None,
    stop_reason: str = "end_turn",
    input_tokens: int = 15,
    output_tokens: int = 25,
) -> SimpleNamespace:
    if content_blocks is None:
        content_blocks = [_text_block("Hello, I can help!")]
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(
        model=model,
        content=content_blocks,
        stop_reason=stop_reason,
        usage=usage,
    )


def _build_fake_anthropic_module() -> types.ModuleType:
    """Return a fake ``anthropic`` module with *separate* class hierarchies.

    ``FakeAnthropic`` and ``FakeAsyncAnthropic`` each own their own
    ``messages`` SimpleNamespace so patching one does not affect the other.
    """
    fake_anthropic = types.ModuleType("anthropic")

    sync_messages = SimpleNamespace(create=MagicMock(name="sync_create"))
    async_messages = SimpleNamespace(create=MagicMock(name="async_create"))

    class FakeAnthropic:
        messages = sync_messages

    class FakeAsyncAnthropic:
        messages = async_messages

    fake_anthropic.Anthropic = FakeAnthropic
    fake_anthropic.AsyncAnthropic = FakeAsyncAnthropic
    return fake_anthropic


def _flush(adapter: AnthropicAdapter) -> None:
    """Block until the adapter's background transport thread has drained its queue."""
    transport = adapter._transport
    transport._queue.put(transport_module._SENTINEL)
    transport._thread.join(timeout=_FLUSH_TIMEOUT)


def _get_trace_events(mock_httpx) -> list[dict]:
    """Extract the JSON bodies of all /api/traces POST calls."""
    events = []
    for c in mock_httpx.post.call_args_list:
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
    original = transport_module._current_session_id
    yield
    transport_module._current_session_id = original


@pytest.fixture()
def mock_httpx():
    """Patch httpx.Client so SyncTransport never touches the network."""
    with patch("httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.get.side_effect = Exception("no server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "session-anthropic-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_anthropic(mock_httpx):
    """Inject a fake ``anthropic`` module into sys.modules for the test duration."""
    mod = _build_fake_anthropic_module()
    with patch.dict(sys.modules, {"anthropic": mod}):
        yield mod


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestAnthropicAdapterIsAvailable:
    def test_returns_true_when_anthropic_present(self) -> None:
        fake_mod = types.ModuleType("anthropic")
        with patch.dict(sys.modules, {"anthropic": fake_mod}):
            adapter = AnthropicAdapter()
            assert adapter.is_available() is True

    def test_returns_false_when_anthropic_absent(self) -> None:
        with patch.dict(sys.modules, {"anthropic": None}):
            adapter = AnthropicAdapter()
            assert adapter.is_available() is False


# ---------------------------------------------------------------------------
# Sync path
# ---------------------------------------------------------------------------


class TestAnthropicAdapterSyncPatch:
    def test_patch_replaces_create_method(self, fake_anthropic, mock_httpx) -> None:
        original_create = fake_anthropic.Anthropic.messages.create

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_anthropic.Anthropic.messages.create is not original_create

    def test_unpatch_restores_original(self, fake_anthropic, mock_httpx) -> None:
        original_sync = fake_anthropic.Anthropic.messages.create
        original_async = fake_anthropic.AsyncAnthropic.messages.create

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_anthropic.Anthropic.messages.create is original_sync
        assert fake_anthropic.AsyncAnthropic.messages.create is original_async

    def test_unpatch_logs_restore_failures(self, fake_anthropic, mock_httpx, caplog) -> None:
        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        with patch.dict(sys.modules, {"anthropic": None}):
            with caplog.at_level(logging.WARNING, logger="agent_debugger.auto_patch"):
                adapter.unpatch()

        assert "AnthropicAdapter: failed to restore original client methods" in caplog.text

    def test_non_streaming_emits_request_and_response(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(content_blocks=[_text_block("Sure!")])
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_
        assert "llm_response" in types_

    def test_tool_use_emits_tool_call_events(self, fake_anthropic, mock_httpx) -> None:
        block = _tool_use_block(name="search_docs", input_data={"query": "openai"})
        fake_response = _make_fake_response(content_blocks=[block], stop_reason="tool_use")
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "tool_call" in types_

        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "search_docs"
        assert tool_event["arguments"] == {"query": "openai"}

    def test_streaming_passthrough_no_events(self, fake_anthropic, mock_httpx) -> None:
        stream_resp = MagicMock()
        original_create = MagicMock(return_value=stream_resp)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[], stream=True)
        _flush(adapter)
        assert result is stream_resp
        assert _get_trace_events(mock_httpx) == []

    def test_server_unreachable_does_not_raise(self, fake_anthropic, mock_httpx) -> None:
        mock_httpx.post.side_effect = Exception("connection refused")
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])
        assert result is fake_response

    def test_capture_content_false_omits_messages_and_text(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(content_blocks=[_text_block("secret")])
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=False)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(
            MagicMock(),
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "private"}],
        )

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["messages"] == []
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["content"] == ""

    def test_mixed_blocks_text_and_tool_use(self, fake_anthropic, mock_httpx) -> None:
        blocks = [
            _text_block("I'll look that up for you."),
            _tool_use_block(name="fetch_data", input_data={"id": 42}),
        ]
        fake_response = _make_fake_response(content_blocks=blocks, stop_reason="tool_use")
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert "I'll look that up" in resp["content"]
        assert resp["tool_calls"]

    def test_response_is_returned_unchanged(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        result = wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])
        assert result is fake_response

    def test_request_event_contains_model_and_settings(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(
            MagicMock(),
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
            max_tokens=2000,
        )

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["model"] == "claude-3-5-sonnet-20241022"
        assert req["settings"]["temperature"] == 0.5
        assert req["settings"]["max_tokens"] == 2000

    def test_response_event_contains_usage_tokens(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(input_tokens=123, output_tokens=456)
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["usage"]["input_tokens"] == 123
        assert resp["usage"]["output_tokens"] == 456

    def test_response_event_has_duration_ms(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response()
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["duration_ms"] > 0

    def test_no_tool_calls_when_stop_reason_is_end_turn(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(stop_reason="end_turn")
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        tool_events = [e for e in sent if e["event_type"] == "tool_call"]
        assert len(tool_events) == 0

    def test_tool_call_event_has_correct_name(self, fake_anthropic, mock_httpx) -> None:
        block = _tool_use_block(tool_id="toolu_abc123", name="get_weather", input_data={"city": "Tokyo"})
        fake_response = _make_fake_response(content_blocks=[block], stop_reason="tool_use")
        original_create = MagicMock(return_value=fake_response)

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_sync_wrapper(original_create)
        wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "get_weather"
        assert tool_event["arguments"] == {"city": "Tokyo"}


# ---------------------------------------------------------------------------
# Async path
# ---------------------------------------------------------------------------


class TestAnthropicAdapterAsyncPatch:
    def test_async_emits_request_and_response(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(content_blocks=[_text_block("async response")])

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_
        assert "llm_response" in types_

    def test_async_streaming_passthrough_no_events(self, fake_anthropic, mock_httpx) -> None:
        stream_resp = MagicMock()

        async def async_original(self_client, *args, **kwargs):
            return stream_resp

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        result = asyncio.run(wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[], stream=True))
        assert result is stream_resp
        assert _get_trace_events(mock_httpx) == []

    def test_async_tool_use_emits_tool_call_events(self, fake_anthropic, mock_httpx) -> None:
        block = _tool_use_block(name="run_code", input_data={"code": "print('hi')"})
        fake_response = _make_fake_response(content_blocks=[block], stop_reason="tool_use")

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "tool_call" in types_
        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "run_code"

    def test_async_server_unreachable_does_not_raise(self, fake_anthropic, mock_httpx) -> None:
        mock_httpx.post.side_effect = Exception("connection refused")
        fake_response = _make_fake_response()

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        result = asyncio.run(wrapper(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[]))
        assert result is fake_response

    def test_async_response_contains_model_and_usage(self, fake_anthropic, mock_httpx) -> None:
        fake_response = _make_fake_response(
            model="claude-3-5-haiku-20241022", input_tokens=99, output_tokens=88
        )

        async def async_original(self_client, *args, **kwargs):
            return fake_response

        adapter = AnthropicAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        wrapper = adapter._make_async_wrapper(async_original)
        asyncio.run(wrapper(MagicMock(), model="claude-3-5-haiku-20241022", messages=[]))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert resp["model"] == "claude-3-5-haiku-20241022"
        assert resp["usage"]["input_tokens"] == 99
        assert resp["usage"]["output_tokens"] == 88
