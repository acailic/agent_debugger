"""Tests for LangChainAdapter.

``langchain_core`` is not installed in this environment, so all tests mock the
module via ``sys.modules`` before calling any adapter method that does
``import langchain_core``.

The tests verify:
1. ``is_available()`` returns False when langchain_core is not installed.
2. ``is_available()`` returns True when langchain_core is present.
3. ``patch()`` installs the handler into the global callback manager.
4. ``unpatch()`` removes the handler from the global callback manager.
5. LLM start/end callbacks emit the correct event types.
6. Tool start callback emits a tool_call event.
7. Server unreachability does not raise.
"""

from __future__ import annotations

import sys
import types
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import (
    LangChainAdapter,
    _SyncTracingCallbackHandler,
)
from agent_debugger_sdk.auto_patch.registry import PatchConfig

_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fake_langchain_core() -> types.ModuleType:
    """Return a fake ``langchain_core`` module with a mock callback manager."""
    fake_lc = types.ModuleType("langchain_core")
    fake_lc_callbacks = types.ModuleType("langchain_core.callbacks")
    fake_lc_callbacks_manager = types.ModuleType("langchain_core.callbacks.manager")

    # Expose a mutable _handlers list that mirrors real langchain_core internals
    fake_lc_callbacks_manager._handlers = []  # type: ignore[attr-defined]

    fake_lc.callbacks = fake_lc_callbacks
    fake_lc_callbacks.manager = fake_lc_callbacks_manager

    return fake_lc


def _make_fake_llm_result(text: str = "response text") -> SimpleNamespace:
    """Build a minimal LangChain LLMResult-like object."""
    generation = SimpleNamespace(text=text)
    llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    return SimpleNamespace(generations=[[generation]], llm_output=llm_output)


def _flush(adapter: LangChainAdapter) -> None:
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
        mock_response.json.return_value = {"id": "session-langchain-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_langchain_core(mock_httpx):
    """Inject a fake ``langchain_core`` module into sys.modules."""
    mod = _build_fake_langchain_core()
    patches = {
        "langchain_core": mod,
        "langchain_core.callbacks": mod.callbacks,
        "langchain_core.callbacks.manager": mod.callbacks.manager,
    }
    with patch.dict(sys.modules, patches):
        yield mod


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestLangChainAdapterIsAvailable:
    def test_returns_false_when_langchain_core_absent(self) -> None:
        with patch.dict(sys.modules, {"langchain_core": None}):
            adapter = LangChainAdapter()
            assert adapter.is_available() is False

    def test_returns_true_when_langchain_core_present(self) -> None:
        fake_mod = types.ModuleType("langchain_core")
        with patch.dict(sys.modules, {"langchain_core": fake_mod}):
            adapter = LangChainAdapter()
            assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# patch / unpatch
# ---------------------------------------------------------------------------


class TestLangChainAdapterPatchUnpatch:
    def test_patch_installs_handler_into_global_callbacks(self, fake_langchain_core, mock_httpx) -> None:
        """patch() should append the handler to _handlers list."""
        manager_mod = fake_langchain_core.callbacks.manager
        assert len(manager_mod._handlers) == 0

        adapter = LangChainAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert len(manager_mod._handlers) == 1
        assert isinstance(manager_mod._handlers[0], _SyncTracingCallbackHandler)

    def test_unpatch_removes_handler_from_global_callbacks(self, fake_langchain_core, mock_httpx) -> None:
        """unpatch() should remove the handler installed by patch()."""
        manager_mod = fake_langchain_core.callbacks.manager

        adapter = LangChainAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        assert len(manager_mod._handlers) == 1

        adapter.unpatch()
        assert len(manager_mod._handlers) == 0

    def test_unpatch_without_patch_does_not_raise(self) -> None:
        """Calling unpatch() before patch() should be a no-op."""
        adapter = LangChainAdapter()
        adapter.unpatch()  # should not raise

    def test_patch_creates_transport(self, fake_langchain_core, mock_httpx) -> None:
        adapter = LangChainAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        assert adapter._transport is not None


# ---------------------------------------------------------------------------
# Callback handler event emission
# ---------------------------------------------------------------------------


class TestSyncTracingCallbackHandlerEvents:
    """Tests for the _SyncTracingCallbackHandler callback methods."""

    def _make_handler(self, mock_httpx, capture_content: bool = False) -> _SyncTracingCallbackHandler:
        transport = transport_module.SyncTransport("http://localhost:9999")
        return _SyncTracingCallbackHandler(
            session_id="test-session",
            transport=transport,
            capture_content=capture_content,
        )

    def _flush_handler(self, handler: _SyncTracingCallbackHandler) -> None:
        handler._transport._queue.put(transport_module._SENTINEL)
        handler._transport._thread.join(timeout=_FLUSH_TIMEOUT)

    def test_on_llm_start_emits_request_event(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx)
        run_id = uuid.uuid4()
        handler.on_llm_start(
            {"name": "ChatOpenAI"},
            ["Hello"],
            run_id=run_id,
            invocation_params={"model": "gpt-4o", "temperature": 0.7},
        )
        self._flush_handler(handler)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_request" in types_

    def test_on_llm_end_emits_response_event(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx)
        run_id = uuid.uuid4()
        handler.on_llm_start(
            {},
            ["Hi"],
            run_id=run_id,
            invocation_params={"model": "gpt-4o"},
        )
        result = _make_fake_llm_result("OK")
        handler.on_llm_end(result, run_id=run_id)
        self._flush_handler(handler)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "llm_response" in types_

    def test_on_llm_start_omits_messages_when_capture_content_false(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx, capture_content=False)
        run_id = uuid.uuid4()
        handler.on_llm_start(
            {},
            ["secret prompt"],
            run_id=run_id,
        )
        self._flush_handler(handler)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert req["messages"] == []

    def test_on_llm_start_includes_messages_when_capture_content_true(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx, capture_content=True)
        run_id = uuid.uuid4()
        handler.on_llm_start(
            {},
            ["visible prompt"],
            run_id=run_id,
        )
        self._flush_handler(handler)
        sent = _get_trace_events(mock_httpx)
        req = next(e for e in sent if e["event_type"] == "llm_request")
        assert len(req["messages"]) == 1
        assert req["messages"][0]["content"] == "visible prompt"

    def test_on_tool_start_emits_tool_call_event(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx)
        run_id = uuid.uuid4()
        handler.on_tool_start(
            {"name": "search_web"},
            "python docs",
            run_id=run_id,
        )
        self._flush_handler(handler)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "tool_call" in types_
        tool_event = next(e for e in sent if e["event_type"] == "tool_call")
        assert tool_event["tool_name"] == "search_web"

    def test_on_llm_error_cleans_up_state(self, mock_httpx) -> None:
        handler = self._make_handler(mock_httpx)
        run_id = uuid.uuid4()
        handler.on_llm_start({}, ["prompt"], run_id=run_id)
        handler.on_llm_error(ValueError("boom"), run_id=run_id)
        # After error, tracking dicts should be empty for this run
        assert str(run_id) not in handler._start_times
        assert str(run_id) not in handler._request_event_ids

    def test_server_unreachable_does_not_raise(self, mock_httpx) -> None:
        mock_httpx.post.side_effect = Exception("connection refused")
        handler = self._make_handler(mock_httpx)
        run_id = uuid.uuid4()
        # Should not raise even if delivery fails
        handler.on_llm_start({}, ["hello"], run_id=run_id)
        self._flush_handler(handler)


# ---------------------------------------------------------------------------
# Full adapter integration (patch -> callback -> unpatch)
# ---------------------------------------------------------------------------


class TestLangChainAdapterIntegration:
    def test_handler_session_id_matches_transport_session(self, fake_langchain_core, mock_httpx) -> None:
        """The installed handler should use the session ID from get_or_create_session."""
        adapter = LangChainAdapter()
        config = PatchConfig(server_url="http://localhost:9999", agent_name="test-agent")
        adapter.patch(config)

        manager_mod = fake_langchain_core.callbacks.manager
        installed_handler = manager_mod._handlers[0]

        assert installed_handler._session_id == "session-langchain-test"

    def test_second_unpatch_is_safe(self, fake_langchain_core, mock_httpx) -> None:
        """Calling unpatch() twice should not raise."""
        adapter = LangChainAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()
        adapter.unpatch()  # second call — should be no-op
