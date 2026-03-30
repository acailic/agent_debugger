"""Tests for PydanticAIAdapter.

``pydantic_ai`` is not installed in this environment, so all tests mock the
module via ``sys.modules`` before calling any adapter method that does
``import pydantic_ai``.

The tests verify:
1. ``is_available()`` returns False when pydantic_ai is not installed.
2. ``is_available()`` returns True when pydantic_ai is present.
3. ``patch()`` monkey-patches ``Agent.run`` at the class level.
4. ``unpatch()`` restores the original ``Agent.run`` method.
5. The patched ``run`` emits LLMRequestEvent + LLMResponseEvent.
6. Double-patching is guarded against.
7. Server unreachability does not raise.
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
from agent_debugger_sdk.auto_patch.adapters.pydanticai_adapter import (
    PydanticAIAdapter,
    _extract_usage,
    _get_model_name,
)
from agent_debugger_sdk.auto_patch.registry import PatchConfig

_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fake_pydantic_ai() -> types.ModuleType:
    """Return a fake ``pydantic_ai`` module with a minimal Agent class."""
    fake_pai = types.ModuleType("pydantic_ai")

    class FakeAgent:
        model = "openai:gpt-4o"

        async def run(self, user_prompt=None, **kwargs):  # noqa: ANN001
            return SimpleNamespace(data="result", usage=lambda: SimpleNamespace(request_tokens=5, response_tokens=10))

    fake_pai.Agent = FakeAgent
    return fake_pai


def _flush(adapter: PydanticAIAdapter) -> None:
    """Drain the background transport thread queue."""
    assert adapter._transport is not None
    transport = adapter._transport
    transport._queue.put(transport_module._SENTINEL)
    transport._thread.join(timeout=_FLUSH_TIMEOUT)


def _get_trace_events(mock_httpx: MagicMock) -> list[dict]:
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
        mock_response.json.return_value = {"id": "session-pydanticai-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_pydantic_ai(mock_httpx):
    """Inject a fake ``pydantic_ai`` module into sys.modules."""
    mod = _build_fake_pydantic_ai()
    with patch.dict(sys.modules, {"pydantic_ai": mod}):
        yield mod


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestPydanticAIAdapterIsAvailable:
    def test_returns_false_when_pydantic_ai_absent(self) -> None:
        with patch.dict(sys.modules, {"pydantic_ai": None}):
            adapter = PydanticAIAdapter()
            assert adapter.is_available() is False

    def test_returns_true_when_pydantic_ai_present(self) -> None:
        fake_mod = types.ModuleType("pydantic_ai")
        fake_mod.Agent = object  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"pydantic_ai": fake_mod}):
            adapter = PydanticAIAdapter()
            assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# patch / unpatch
# ---------------------------------------------------------------------------


class TestPydanticAIAdapterPatchUnpatch:
    def test_patch_replaces_agent_run(self, fake_pydantic_ai, mock_httpx) -> None:
        """patch() should replace Agent.run with a traced wrapper."""
        original_run = fake_pydantic_ai.Agent.run

        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_pydantic_ai.Agent.run is not original_run
        assert getattr(fake_pydantic_ai.Agent.run, "_peaky_peek_patched", False) is True

    def test_unpatch_restores_original_run(self, fake_pydantic_ai, mock_httpx) -> None:
        """unpatch() should restore the original Agent.run."""
        original_run = fake_pydantic_ai.Agent.run

        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_pydantic_ai.Agent.run is original_run

    def test_unpatch_without_patch_does_not_raise(self) -> None:
        """Calling unpatch() before patch() should be a no-op."""
        adapter = PydanticAIAdapter()
        adapter.unpatch()  # should not raise

    def test_double_patch_is_guarded(self, fake_pydantic_ai, mock_httpx) -> None:
        """Calling patch() twice should not double-wrap Agent.run."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        first_run = fake_pydantic_ai.Agent.run

        adapter.patch(config)  # second patch — should be a no-op
        assert fake_pydantic_ai.Agent.run is first_run

        adapter.unpatch()


class TestPydanticAIAdapterHelpers:
    def test_extract_usage_logs_failures(self, caplog) -> None:
        result = SimpleNamespace(usage=MagicMock(side_effect=RuntimeError("broken usage")))

        with caplog.at_level(logging.WARNING, logger="agent_debugger.auto_patch"):
            usage = _extract_usage(result)

        assert usage == {"input_tokens": 0, "output_tokens": 0}
        assert "PydanticAIAdapter: failed to extract usage from result.usage()" in caplog.text


# ---------------------------------------------------------------------------
# Event emission via patched run
# ---------------------------------------------------------------------------


class TestPydanticAIAdapterEventEmission:
    def test_patched_run_emits_request_and_response(self, fake_pydantic_ai, mock_httpx) -> None:
        """The traced run wrapper should emit llm_request and llm_response events."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "Hello"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_
        assert "llm_response" in types_

        adapter.unpatch()

    def test_patched_run_returns_original_result(self, fake_pydantic_ai, mock_httpx) -> None:
        """The traced run should return the same result as the original."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        result = asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "Hello"))
        assert result.data == "result"

        adapter.unpatch()

    def test_capture_content_false_omits_messages(self, fake_pydantic_ai, mock_httpx) -> None:
        """When capture_content=False, messages list in request event should be empty."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=False)
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "secret"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["messages"] == []

        adapter.unpatch()

    def test_capture_content_true_includes_prompt(self, fake_pydantic_ai, mock_httpx) -> None:
        """When capture_content=True, the user prompt appears in the request event."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999", capture_content=True)
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "visible prompt"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert any("visible prompt" in str(m.get("content", "")) for m in req["messages"])

        adapter.unpatch()

    def test_server_unreachable_does_not_raise(self, fake_pydantic_ai, mock_httpx) -> None:
        """Even if the server is unreachable, the agent run should complete."""
        mock_httpx.post.side_effect = Exception("connection refused")

        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        result = asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "Hi"))
        assert result.data == "result"

        adapter.unpatch()

    def test_request_event_contains_model_name(self, fake_pydantic_ai, mock_httpx) -> None:
        """Verify model field in the request event matches the agent's model."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "Hello"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["model"] == "openai:gpt-4o"

        adapter.unpatch()

    def test_response_event_contains_usage(self, fake_pydantic_ai, mock_httpx) -> None:
        """Verify the response event has usage with non-zero tokens."""
        adapter = PydanticAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_pydantic_ai.Agent()
        asyncio.run(fake_pydantic_ai.Agent.run(agent_instance, "Hello"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        resp = next(e for e in sent if e["event_type"] == "llm_response")
        assert "usage" in resp
        assert resp["usage"]["input_tokens"] == 5
        assert resp["usage"]["output_tokens"] == 10

        adapter.unpatch()


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestGetModelName:
    def test_string_model_attribute(self) -> None:
        obj = SimpleNamespace(model="gpt-4o")
        assert _get_model_name(obj) == "gpt-4o"

    def test_model_object_with_model_name(self) -> None:
        model_obj = SimpleNamespace(model_name="claude-3-5-sonnet")
        obj = SimpleNamespace(model=model_obj)
        assert _get_model_name(obj) == "claude-3-5-sonnet"

    def test_fallback_when_no_model(self) -> None:
        obj = SimpleNamespace()
        assert _get_model_name(obj) == "unknown"

    def test_model_attribute_from_model_object_with_name(self) -> None:
        """Test _get_model_name when agent has a model object with .name (not .model_name)."""
        model_obj = SimpleNamespace(name="claude-3-5-sonnet-20241022")
        obj = SimpleNamespace(model=model_obj)
        assert _get_model_name(obj) == "claude-3-5-sonnet-20241022"


class TestExtractUsage:
    def test_callable_usage(self) -> None:
        usage_obj = SimpleNamespace(request_tokens=5, response_tokens=10)
        result = SimpleNamespace(usage=lambda: usage_obj)
        extracted = _extract_usage(result)
        assert extracted == {"input_tokens": 5, "output_tokens": 10}

    def test_non_callable_usage(self) -> None:
        usage_obj = SimpleNamespace(input_tokens=3, output_tokens=7)
        result = SimpleNamespace(usage=usage_obj)
        extracted = _extract_usage(result)
        assert extracted["input_tokens"] == 3
        assert extracted["output_tokens"] == 7

    def test_no_usage_returns_zeros(self) -> None:
        result = SimpleNamespace()
        extracted = _extract_usage(result)
        assert extracted == {"input_tokens": 0, "output_tokens": 0}

    def test_non_callable_usage_with_request_tokens(self) -> None:
        """Test usage attribute with request_tokens (not input_tokens) key."""
        usage_obj = SimpleNamespace(request_tokens=8, response_tokens=12)
        result = SimpleNamespace(usage=usage_obj)
        extracted = _extract_usage(result)
        assert extracted["input_tokens"] == 8
        assert extracted["output_tokens"] == 12

    def test_non_callable_usage_with_response_tokens(self) -> None:
        """Test usage attribute with response_tokens (not output_tokens) key."""
        usage_obj = SimpleNamespace(request_tokens=15, response_tokens=25)
        result = SimpleNamespace(usage=usage_obj)
        extracted = _extract_usage(result)
        assert extracted["input_tokens"] == 15
        assert extracted["output_tokens"] == 25
