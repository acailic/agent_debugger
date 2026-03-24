"""Tests for LangChain auto-patch adapter - targeting 85%+ coverage."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, Mock, patch

from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import LangChainAdapter, _SyncTracingCallbackHandler
from agent_debugger_sdk.auto_patch.registry import PatchConfig


def _make_transport() -> MagicMock:
    transport = MagicMock()
    transport.send_event = MagicMock()
    transport.shutdown = MagicMock()
    return transport


def _make_handler(capture_content: bool = False) -> tuple[_SyncTracingCallbackHandler, MagicMock]:
    transport = _make_transport()
    handler = _SyncTracingCallbackHandler(
        session_id="test-session-id",
        transport=transport,
        capture_content=capture_content,
    )
    return handler, transport


class TestSyncTracingCallbackHandlerInit:
    """Test handler initialization."""

    def test_handler_has_expected_attributes(self):
        handler, _ = _make_handler()
        assert handler._session_id == "test-session-id"
        assert handler._capture_content is False
        assert isinstance(handler._start_times, dict)
        assert isinstance(handler._model_names, dict)
        assert isinstance(handler._request_event_ids, dict)

    def test_raise_error_is_false(self):
        handler, _ = _make_handler()
        assert handler.raise_error is False

    def test_capture_content_can_be_enabled(self):
        handler, _ = _make_handler(capture_content=True)
        assert handler._capture_content is True

    def test_has_all_required_callbacks(self):
        handler, _ = _make_handler()
        assert hasattr(handler, "on_llm_start")
        assert hasattr(handler, "on_llm_end")
        assert hasattr(handler, "on_llm_error")
        assert hasattr(handler, "on_tool_start")
        assert hasattr(handler, "on_tool_end")
        assert hasattr(handler, "on_tool_error")
        assert hasattr(handler, "on_chain_start")
        assert hasattr(handler, "on_chain_end")
        assert hasattr(handler, "on_chain_error")


class TestSyncTracingCallbackHandlerLLM:
    """Test LLM-related callbacks."""

    def test_on_llm_start_emits_request_event(self):
        handler, transport = _make_handler()

        handler.on_llm_start(serialized={"name": "test"}, prompts=["Hello"], run_id=uuid.uuid4())

        transport.send_event.assert_called_once()
        event = transport.send_event.call_args[0][0]
        assert event.get("event_type") == "llm_request"

    def test_on_llm_start_tracks_run_id(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()

        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)

        assert str(run_id) in handler._start_times
        assert str(run_id) in handler._model_names

    def test_on_llm_start_extracts_model_from_invocation_params(self):
        handler, transport = _make_handler()

        handler.on_llm_start(
            serialized={},
            prompts=[],
            run_id=uuid.uuid4(),
            invocation_params={"model": "gpt-4"},
        )

        event = transport.send_event.call_args[0][0]
        # Model name should appear somewhere in the event
        assert "gpt-4" in str(event)

    def test_on_llm_start_omits_content_when_disabled(self):
        handler, transport = _make_handler(capture_content=False)

        handler.on_llm_start(serialized={}, prompts=["Secret"], run_id=uuid.uuid4())

        event = transport.send_event.call_args[0][0]
        assert event.get("messages", []) == []

    def test_on_llm_start_captures_content_when_enabled(self):
        handler, transport = _make_handler(capture_content=True)

        handler.on_llm_start(serialized={}, prompts=["Visible"], run_id=uuid.uuid4())

        event = transport.send_event.call_args[0][0]
        assert len(event.get("messages", [])) > 0

    def test_on_llm_end_emits_response_event(self):
        handler, transport = _make_handler()
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        transport.reset_mock()

        response = Mock(
            generations=[[Mock(text="OK")]],
            llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 10}},
        )
        handler.on_llm_end(response=response, run_id=run_id)

        transport.send_event.assert_called_once()

    def test_on_llm_end_clears_run_state(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        handler.on_llm_end(response=Mock(generations=None, llm_output=None), run_id=run_id)

        assert str(run_id) not in handler._start_times
        assert str(run_id) not in handler._model_names

    def test_on_llm_end_extracts_token_usage(self):
        handler, transport = _make_handler()
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        transport.reset_mock()

        response = Mock(
            generations=[],
            llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 20}},
        )
        handler.on_llm_end(response=response, run_id=run_id)

        event = transport.send_event.call_args[0][0]
        assert event.get("usage", {}).get("input_tokens") == 10
        assert event.get("usage", {}).get("output_tokens") == 20

    def test_on_llm_end_without_prior_start(self):
        """on_llm_end handles missing start state gracefully."""
        handler, transport = _make_handler()
        handler.on_llm_end(response=Mock(generations=None, llm_output=None), run_id=uuid.uuid4())
        transport.send_event.assert_called_once()

    def test_on_llm_end_captures_text_when_enabled(self):
        handler, transport = _make_handler(capture_content=True)
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        transport.reset_mock()

        response = Mock(
            generations=[[Mock(text="Response text")]],
            llm_output=None,
        )
        handler.on_llm_end(response=response, run_id=run_id)

        event = transport.send_event.call_args[0][0]
        assert "Response text" in str(event)

    def test_on_llm_error_clears_state(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        assert str(run_id) in handler._start_times

        handler.on_llm_error(error=Exception("LLM failed"), run_id=run_id)

        assert str(run_id) not in handler._start_times
        assert str(run_id) not in handler._model_names
        assert str(run_id) not in handler._request_event_ids

    def test_on_llm_error_does_not_emit_event(self):
        handler, transport = _make_handler()
        run_id = uuid.uuid4()
        handler.on_llm_start(serialized={}, prompts=[], run_id=run_id)
        transport.reset_mock()

        handler.on_llm_error(error=Exception("fail"), run_id=run_id)

        transport.send_event.assert_not_called()

    def test_on_llm_error_safe_without_prior_start(self):
        handler, _ = _make_handler()
        # Should not raise even with no tracked run
        handler.on_llm_error(error=Exception("oops"), run_id=uuid.uuid4())


class TestSyncTracingCallbackHandlerTool:
    """Test tool-related callbacks."""

    def test_on_tool_start_emits_event(self):
        handler, transport = _make_handler()

        handler.on_tool_start(
            serialized={"name": "search"},
            input_str="query",
            run_id=uuid.uuid4(),
        )

        transport.send_event.assert_called_once()
        event = transport.send_event.call_args[0][0]
        assert event.get("event_type") == "tool_call"

    def test_on_tool_start_with_dict_input(self):
        handler, transport = _make_handler()

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str={"a": 1, "b": 2},
            run_id=uuid.uuid4(),
        )

        event = transport.send_event.call_args[0][0]
        assert event.get("arguments") == {"a": 1, "b": 2}

    def test_on_tool_start_wraps_str_input(self):
        handler, transport = _make_handler()

        handler.on_tool_start(
            serialized={"name": "search"},
            input_str="query string",
            run_id=uuid.uuid4(),
        )

        event = transport.send_event.call_args[0][0]
        assert event.get("arguments") == {"input": "query string"}

    def test_on_tool_start_tracks_run_id(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()

        handler.on_tool_start(serialized={"name": "t"}, input_str="x", run_id=run_id)

        assert str(run_id) in handler._start_times

    def test_on_tool_end_clears_state(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()
        handler.on_tool_start(serialized={"name": "t"}, input_str="x", run_id=run_id)

        handler.on_tool_end(output="result", run_id=run_id)

        assert str(run_id) not in handler._start_times

    def test_on_tool_error_clears_state(self):
        handler, _ = _make_handler()
        run_id = uuid.uuid4()
        handler.on_tool_start(serialized={"name": "t"}, input_str="x", run_id=run_id)

        handler.on_tool_error(error=Exception("fail"), run_id=run_id)

        assert str(run_id) not in handler._start_times

    def test_on_tool_end_safe_without_prior_start(self):
        handler, _ = _make_handler()
        handler.on_tool_end(output="result", run_id=uuid.uuid4())

    def test_on_tool_error_safe_without_prior_start(self):
        handler, _ = _make_handler()
        handler.on_tool_error(error=Exception("fail"), run_id=uuid.uuid4())


class TestSyncTracingCallbackHandlerNoops:
    """Test no-op chain/agent callbacks."""

    def test_chain_callbacks_are_noops(self):
        handler, transport = _make_handler()

        handler.on_chain_start(serialized={}, inputs={}, run_id=uuid.uuid4())
        handler.on_chain_end(outputs={}, run_id=uuid.uuid4())
        handler.on_chain_error(error=Exception(), run_id=uuid.uuid4())
        handler.on_agent_action(action=Mock(), run_id=uuid.uuid4())
        handler.on_agent_finish(finish=Mock(), run_id=uuid.uuid4())
        handler.on_text(text="text", run_id=uuid.uuid4())
        handler.on_retry(retry_state=Mock(), run_id=uuid.uuid4())

        transport.send_event.assert_not_called()


class TestSyncTracingCallbackHandlerRobustness:
    """Test handler error resilience."""

    def test_exception_in_send_event_is_suppressed(self):
        """Handler swallows network failures gracefully."""
        transport = _make_transport()
        transport.send_event.side_effect = RuntimeError("network failure")

        handler = _SyncTracingCallbackHandler(
            session_id="s", transport=transport, capture_content=False
        )
        # Should not raise
        handler.on_llm_start(serialized={}, prompts=[], run_id=uuid.uuid4())

    def test_multiple_concurrent_runs_tracked_independently(self):
        handler, transport = _make_handler()
        run1 = uuid.uuid4()
        run2 = uuid.uuid4()

        handler.on_llm_start(serialized={}, prompts=["p1"], run_id=run1, invocation_params={"model": "a"})
        handler.on_llm_start(serialized={}, prompts=["p2"], run_id=run2, invocation_params={"model": "b"})

        assert str(run1) in handler._start_times
        assert str(run2) in handler._start_times
        assert handler._model_names[str(run1)] == "a"
        assert handler._model_names[str(run2)] == "b"


class TestLangChainAdapter:
    """Test the LangChain adapter."""

    def test_initialization(self):
        adapter = LangChainAdapter()
        assert adapter._handler is None
        assert adapter._transport is None

    def test_name(self):
        assert LangChainAdapter.name == "langchain"

    def test_is_available_returns_bool(self):
        adapter = LangChainAdapter()
        result = adapter.is_available()
        assert isinstance(result, bool)

    def test_is_available_true_when_langchain_importable(self):
        adapter = LangChainAdapter()
        fake_langchain = MagicMock()
        with patch.dict("sys.modules", {"langchain_core": fake_langchain}):
            result = adapter.is_available()
        assert result is True

    def test_is_available_false_when_langchain_missing(self):
        adapter = LangChainAdapter()
        with patch.dict("sys.modules", {"langchain_core": None}):
            result = adapter.is_available()
        assert result is False

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_patch_creates_handler(self, mock_transport_cls, mock_get_session):
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess-123"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler"):
            adapter.patch(PatchConfig())

        assert isinstance(adapter._handler, _SyncTracingCallbackHandler)
        assert adapter._handler._session_id == "sess-123"

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_patch_sets_capture_content(self, mock_transport_cls, mock_get_session):
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler"):
            adapter.patch(PatchConfig(capture_content=True))

        assert adapter._handler._capture_content is True

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_patch_creates_transport_with_server_url(self, mock_transport_cls, mock_get_session):
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler"):
            adapter.patch(PatchConfig(server_url="http://test:9999"))

        mock_transport_cls.assert_called_once_with("http://test:9999")

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_unpatch_clears_handler_and_transport(self, mock_transport_cls, mock_get_session):
        mock_transport = _make_transport()
        mock_transport_cls.return_value = mock_transport
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler"):
            adapter.patch(PatchConfig())

        with patch.object(LangChainAdapter, "_remove_handler"):
            adapter.unpatch()

        assert adapter._handler is None
        assert adapter._transport is None
        mock_transport.shutdown.assert_called_once()

    def test_unpatch_without_patch_is_safe(self):
        adapter = LangChainAdapter()
        adapter.unpatch()
        assert adapter._handler is None

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_patch_unpatch_cycle(self, mock_transport_cls, mock_get_session):
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with (
            patch.object(LangChainAdapter, "_install_handler"),
            patch.object(LangChainAdapter, "_remove_handler"),
        ):
            adapter.patch(PatchConfig())
            adapter.unpatch()
            mock_transport_cls.return_value = _make_transport()
            adapter.patch(PatchConfig())
            adapter.unpatch()

        assert adapter._handler is None

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_install_handler_failure_is_suppressed(self, mock_transport_cls, mock_get_session):
        """Failure to install handler into LangChain's global manager is suppressed."""
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler", side_effect=Exception("no lc")):
            adapter.patch(PatchConfig())  # Should not raise

        assert adapter._handler is not None  # handler still created despite install failure

    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.get_or_create_session")
    @patch("agent_debugger_sdk.auto_patch.adapters.langchain_adapter.SyncTransport")
    def test_remove_handler_failure_is_suppressed(self, mock_transport_cls, mock_get_session):
        """Failure to remove handler from LangChain's global manager is suppressed."""
        mock_transport_cls.return_value = _make_transport()
        mock_get_session.return_value = "sess"

        adapter = LangChainAdapter()
        with patch.object(LangChainAdapter, "_install_handler"):
            adapter.patch(PatchConfig())

        with patch.object(LangChainAdapter, "_remove_handler", side_effect=Exception("no lc")):
            adapter.unpatch()  # Should not raise

        assert adapter._handler is None  # still cleaned up
