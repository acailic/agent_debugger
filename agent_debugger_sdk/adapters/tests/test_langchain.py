"""Tests for LangChain adapter."""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from collector.buffer import get_event_buffer

from agent_debugger_sdk.core.events import EventType


class MockGeneration:
    """Mock LangChain generation."""

    def __init__(self, text: str):
        self.text = text


class MockLLMResult:
    """Mock LangChain LLM result."""

    def __init__(self, text: str = "Hello!"):
        self.generations = [[MockGeneration(text)]]
        self.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}


class TestLangChainTracingHandler:
    """Test LangChainTracingHandler callback handler."""

    @pytest.mark.asyncio
    async def test_handler_initialization(self):
        """Test handler initializes correctly."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(
                session_id="test-session",
                agent_name="test_agent",
                tags=["test"],
            )

            assert handler.session_id == "test-session"
            assert handler.agent_name == "test_agent"
            assert handler.tags == ["test"]

    def test_module_marks_langchain_available_when_imports_succeed(self):
        """Test module import-path sets availability when dependencies exist."""
        import agent_debugger_sdk.adapters.langchain as langchain_mod

        fake_package = types.ModuleType("langchain_core")
        fake_callbacks = types.ModuleType("langchain_core.callbacks")
        fake_outputs = types.ModuleType("langchain_core.outputs")
        fake_callbacks.AsyncCallbackHandler = type("FakeAsyncCallbackHandler", (), {})
        fake_outputs.LLMResult = type("FakeLLMResult", (), {})
        fake_package.callbacks = fake_callbacks
        fake_package.outputs = fake_outputs

        with patch.dict(
            sys.modules,
            {
                "langchain_core": fake_package,
                "langchain_core.callbacks": fake_callbacks,
                "langchain_core.outputs": fake_outputs,
            },
        ):
            reloaded = importlib.reload(langchain_mod)
            assert reloaded.LANGCHAIN_AVAILABLE is True
            assert reloaded.AsyncCallbackHandler is fake_callbacks.AsyncCallbackHandler
            assert reloaded.LLMResult is fake_outputs.LLMResult

        importlib.reload(langchain_mod)

    @pytest.mark.asyncio
    async def test_set_context(self):
        """Test setting context."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-session")

            mock_context = MagicMock()
            handler.set_context(mock_context)

            assert handler._context == mock_context

    @pytest.mark.asyncio
    async def test_on_llm_start(self):
        """Test on_llm_start callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-llm-start")
            context = TraceContext(
                session_id="test-llm-start",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                await handler.on_llm_start(
                    serialized={"name": "ChatOpenAI"},
                    prompts=["Hello"],
                    run_id=uuid.uuid4(),
                    parent_run_id=None,
                    invocation_params={"model": "gpt-4", "temperature": 0.7},
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-llm-start")

            llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1
            assert llm_events[0].model == "gpt-4"
            assert llm_events[0].messages == [{"role": "user", "content": "Hello"}]

    @pytest.mark.asyncio
    async def test_on_llm_end(self):
        """Test on_llm_end callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-llm-end")
            context = TraceContext(
                session_id="test-llm-end",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_llm_start(
                    serialized={"name": "ChatOpenAI"},
                    prompts=["Hello"],
                    run_id=run_id,
                )

                await handler.on_llm_end(
                    response=MockLLMResult("Hello, world!"),
                    run_id=run_id,
                    invocation_params={"model": "gpt-4"},
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-llm-end")

            llm_events = [e for e in events if e.event_type == EventType.LLM_RESPONSE]
            assert len(llm_events) == 1
            assert llm_events[0].content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_on_llm_error(self):
        """Test on_llm_error callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-llm-error")
            context = TraceContext(
                session_id="test-llm-error",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_llm_start(
                    serialized={"name": "ChatOpenAI"},
                    prompts=["Hello"],
                    run_id=run_id,
                )

                await handler.on_llm_error(
                    error=ValueError("API error"),
                    run_id=run_id,
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-llm-error")

            error_events = [e for e in events if e.event_type == EventType.ERROR]
            assert len(error_events) == 1
            assert error_events[0].error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_on_tool_start(self):
        """Test on_tool_start callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-tool-start")
            context = TraceContext(
                session_id="test-tool-start",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                await handler.on_tool_start(
                    serialized={"name": "search_tool"},
                    input_str="search query",
                    run_id=uuid.uuid4(),
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-tool-start")

            tool_events = [e for e in events if e.event_type == EventType.TOOL_CALL]
            assert len(tool_events) == 1
            assert tool_events[0].tool_name == "search_tool"
            assert tool_events[0].arguments == {"input": "search query"}

    @pytest.mark.asyncio
    async def test_on_tool_end(self):
        """Test on_tool_end callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-tool-end")
            context = TraceContext(
                session_id="test-tool-end",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_tool_start(
                    serialized={"name": "search_tool"},
                    input_str="search query",
                    run_id=run_id,
                )

                await handler.on_tool_end(
                    output="search results",
                    run_id=run_id,
                    name="search_tool",
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-tool-end")

            tool_result_events = [e for e in events if e.event_type == EventType.TOOL_RESULT]
            assert len(tool_result_events) == 1
            assert tool_result_events[0].tool_name == "search_tool"
            assert tool_result_events[0].result == "search results"

    @pytest.mark.asyncio
    async def test_on_tool_error(self):
        """Test on_tool_error callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-tool-error")
            context = TraceContext(
                session_id="test-tool-error",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_tool_start(
                    serialized={"name": "search_tool"},
                    input_str="search query",
                    run_id=run_id,
                )

                await handler.on_tool_error(
                    error=RuntimeError("Tool failed"),
                    run_id=run_id,
                    name="search_tool",
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-tool-error")

            tool_result_events = [e for e in events if e.event_type == EventType.TOOL_RESULT]
            assert len(tool_result_events) == 1
            assert tool_result_events[0].error == "Tool failed"

    @pytest.mark.asyncio
    async def test_on_chain_start(self):
        """Test on_chain_start callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-chain-start")
            context = TraceContext(
                session_id="test-chain-start",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                await handler.on_chain_start(
                    serialized={"name": "test_chain", "id": ["langchain", "chain"]},
                    inputs={"query": "test"},
                    run_id=uuid.uuid4(),
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-chain-start")

            chain_events = [e for e in events if e.name.startswith("chain_start_")]
            assert len(chain_events) == 1
            assert "chain" in chain_events[0].name

    @pytest.mark.asyncio
    async def test_on_chain_end(self):
        """Test on_chain_end callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-chain-end")
            context = TraceContext(
                session_id="test-chain-end",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_chain_start(
                    serialized={"name": "test_chain"},
                    inputs={"query": "test"},
                    run_id=run_id,
                )

                await handler.on_chain_end(
                    outputs={"result": "success"},
                    run_id=run_id,
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-chain-end")

            chain_end_events = [e for e in events if e.name == "chain_end"]
            assert len(chain_end_events) == 1

    @pytest.mark.asyncio
    async def test_import_error_without_langchain(self):
        """Test that ImportError is raised when LangChain is not available."""
        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", False):
            with pytest.raises(ImportError, match="LangChain is not installed"):
                from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

                LangChainTracingHandler(session_id="test")

    @pytest.mark.asyncio
    async def test_callbacks_are_noops_without_context(self):
        """Test callbacks return early when no trace context is set."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-no-context")
            run_id = uuid.uuid4()

            await handler.on_llm_start(serialized={}, prompts=["hello"], run_id=run_id)
            await handler.on_llm_end(response=MockLLMResult("hello"), run_id=run_id)
            await handler.on_llm_error(error=ValueError("boom"), run_id=run_id)
            await handler.on_tool_start(serialized={}, input_str="x", run_id=run_id)
            await handler.on_tool_end(output="x", run_id=run_id)
            await handler.on_tool_error(error=RuntimeError("boom"), run_id=run_id)
            await handler.on_chain_start(serialized={}, inputs={"q": "x"}, run_id=run_id)
            await handler.on_chain_end(outputs={"ok": True}, run_id=run_id)
            await handler.on_chain_error(error=RuntimeError("boom"), run_id=run_id)

    @pytest.mark.asyncio
    async def test_on_llm_start_uses_parent_model_name_and_filtered_settings(self):
        """Test llm_start uses parent run mapping and model_name fallback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-llm-model-name")
            context = TraceContext(
                session_id="test-llm-model-name",
                agent_name="test",
                framework="langchain",
            )

            parent_run_id = uuid.uuid4()
            handler._run_map[str(parent_run_id)] = "parent-event-id"

            async with context:
                handler.set_context(context)

                await handler.on_llm_start(
                    serialized={"name": "ChatOpenAI"},
                    prompts=["Hello", "World"],
                    run_id=uuid.uuid4(),
                    parent_run_id=parent_run_id,
                    invocation_params={
                        "model_name": "gpt-4o-mini",
                        "temperature": 0.2,
                        "max_tokens": 50,
                        "top_p": None,
                    },
                )

            buffer = get_event_buffer()
            llm_events = [e for e in buffer.get_events("test-llm-model-name") if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1
            assert llm_events[0].parent_id == "parent-event-id"
            assert llm_events[0].model == "gpt-4o-mini"
            assert llm_events[0].settings == {"temperature": 0.2, "max_tokens": 50}

    @pytest.mark.asyncio
    async def test_tool_callbacks_handle_dict_input_and_non_serializable_output(self):
        """Test tool callback fallbacks for dict inputs and non-standard outputs."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        class WeirdOutput:
            def __str__(self):
                return "weird-output"

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-tool-fallbacks")
            context = TraceContext(
                session_id="test-tool-fallbacks",
                agent_name="test",
                framework="langchain",
            )

            parent_run_id = uuid.uuid4()
            handler._run_map[str(parent_run_id)] = "parent-tool-event"
            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_tool_start(
                    serialized={},
                    input_str={"query": "Belgrade"},
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    name="fallback_tool",
                )

                await handler.on_tool_end(
                    output=WeirdOutput(),
                    run_id=run_id,
                )

            buffer = get_event_buffer()
            tool_call = next(e for e in buffer.get_events("test-tool-fallbacks") if e.event_type == EventType.TOOL_CALL)
            tool_result = next(e for e in buffer.get_events("test-tool-fallbacks") if e.event_type == EventType.TOOL_RESULT)

            assert tool_call.parent_id == "parent-tool-event"
            assert tool_call.tool_name == "fallback_tool"
            assert tool_call.arguments == {"query": "Belgrade"}
            assert tool_result.tool_name == "unknown"
            assert tool_result.result == "weird-output"

    @pytest.mark.asyncio
    async def test_chain_callbacks_use_defaults_and_emit_errors(self):
        """Test chain callback default naming and chain error emission."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-chain-fallbacks")
            context = TraceContext(
                session_id="test-chain-fallbacks",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)
                await handler.on_chain_start(serialized={}, inputs={"step": 1}, run_id=run_id)
                await handler.on_chain_end(outputs={"done": True}, run_id=run_id)
                await handler.on_chain_error(error=RuntimeError("chain failed"), run_id=uuid.uuid4())

            buffer = get_event_buffer()
            events = buffer.get_events("test-chain-fallbacks")
            chain_start = next(event for event in events if event.name.startswith("chain_start_"))
            chain_end = next(event for event in events if event.name == "chain_end")
            error_event = next(event for event in events if event.event_type == EventType.ERROR)

            assert chain_start.name == "chain_start_chain"
            assert chain_start.data["chain_type"] == "unknown"
            assert chain_end.event_type == EventType.AGENT_END
            assert error_event.error_message == "chain failed"


class TestLangChainAdapter:
    """Test LangChainAdapter functionality."""

    @pytest.mark.asyncio
    async def test_adapter_initialization(self):
        """Test adapter initializes correctly."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        adapter = LangChainAdapter(
            session_id="test-session",
            agent_name="test_agent",
            tags=["test"],
        )

        assert adapter.session_id == "test-session"
        assert adapter.agent_name == "test_agent"
        assert adapter.tags == ["test"]

    @pytest.mark.asyncio
    async def test_handler_property(self):
        """Test handler property returns LangChainTracingHandler."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            adapter = LangChainAdapter(session_id="test-session")
            handler = adapter.handler

            assert isinstance(handler, LangChainTracingHandler)
            assert handler.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test context manager creates session."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            adapter = LangChainAdapter(
                session_id="test-context-session",
                agent_name="test_agent",
            )

            async with adapter:
                assert adapter._context is not None
                assert adapter.handler._context is not None

            buffer = get_event_buffer()
            events = buffer.get_events("test-context-session")

            assert len(events) >= 2
            assert events[0].event_type == EventType.AGENT_START
            assert events[-1].event_type == EventType.AGENT_END

    @pytest.mark.asyncio
    async def test_get_callbacks(self):
        """Test get_callbacks returns handler list."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            adapter = LangChainAdapter(session_id="test-session")
            callbacks = adapter.get_callbacks()

            assert len(callbacks) == 1
            assert isinstance(callbacks[0], LangChainTracingHandler)

    @pytest.mark.asyncio
    async def test_handler_property_is_cached_and_exit_without_context_is_safe(self):
        """Test handler is cached and __aexit__ is safe before __aenter__."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            adapter = LangChainAdapter(session_id="cached-handler")
            assert adapter.handler is adapter.handler
            await adapter.__aexit__(None, None, None)


class TestLangChainErrorBoundaries:
    """Test error boundary handling in LangChain adapter."""

    @pytest.mark.asyncio
    async def test_on_llm_start_error_boundary(self):
        """Test that on_llm_start handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            # Mock context to raise exception
            async with context:
                handler.set_context(context)

                # Patch _emit_event to raise exception
                with patch.object(
                    context, "_emit_event", side_effect=RuntimeError("Callback failed")
                ):
                    # Should not raise despite exception
                    await handler.on_llm_start(
                        serialized={"name": "ChatOpenAI"},
                        prompts=["Hello"],
                        run_id=uuid.uuid4(),
                    )

    @pytest.mark.asyncio
    async def test_on_llm_end_error_boundary(self):
        """Test that on_llm_end handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_llm_start(
                    serialized={"name": "ChatOpenAI"},
                    prompts=["Hello"],
                    run_id=run_id,
                )

                # Patch _emit_event to raise exception
                with patch.object(
                    context, "_emit_event", side_effect=ValueError("Emit failed")
                ):
                    # Should not raise despite exception
                    await handler.on_llm_end(
                        response=MockLLMResult("Hello"),
                        run_id=run_id,
                    )

    @pytest.mark.asyncio
    async def test_on_tool_start_error_boundary(self):
        """Test that on_tool_start handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                # Patch _emit_event to raise exception
                with patch.object(
                    context, "_emit_event", side_effect=RuntimeError("Tool callback failed")
                ):
                    # Should not raise despite exception
                    await handler.on_tool_start(
                        serialized={"name": "test_tool"},
                        input_str="test input",
                        run_id=uuid.uuid4(),
                    )

    @pytest.mark.asyncio
    async def test_on_tool_end_error_boundary(self):
        """Test that on_tool_end handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_tool_start(
                    serialized={"name": "test_tool"},
                    input_str="test input",
                    run_id=run_id,
                )

                # Patch record_tool_result to raise exception
                with patch.object(
                    context, "record_tool_result", side_effect=ValueError("Record failed")
                ):
                    # Should not raise despite exception
                    await handler.on_tool_end(
                        output="result",
                        run_id=run_id,
                        name="test_tool",
                    )

    @pytest.mark.asyncio
    async def test_on_chain_start_error_boundary(self):
        """Test that on_chain_start handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                # Patch _emit_event to raise exception
                with patch.object(
                    context, "_emit_event", side_effect=RuntimeError("Chain callback failed")
                ):
                    # Should not raise despite exception
                    await handler.on_chain_start(
                        serialized={"name": "test_chain"},
                        inputs={"query": "test"},
                        run_id=uuid.uuid4(),
                    )

    @pytest.mark.asyncio
    async def test_on_chain_end_error_boundary(self):
        """Test that on_chain_end handles exceptions gracefully."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-boundary")
            context = TraceContext(
                session_id="test-error-boundary",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()

            async with context:
                handler.set_context(context)

                await handler.on_chain_start(
                    serialized={"name": "test_chain"},
                    inputs={"query": "test"},
                    run_id=run_id,
                )

                # Patch _emit_event to raise exception
                with patch.object(
                    context, "_emit_event", side_effect=ValueError("Chain end failed")
                ):
                    # Should not raise despite exception
                    await handler.on_chain_end(
                        outputs={"result": "success"},
                        run_id=run_id,
                    )

    @pytest.mark.asyncio
    async def test_error_callbacks_handle_record_failures(self):
        """Test llm/tool/chain error callbacks swallow record_error/result failures."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-error-callback-boundary")
            context = TraceContext(
                session_id="test-error-callback-boundary",
                agent_name="test",
                framework="langchain",
            )

            async with context:
                handler.set_context(context)

                with patch.object(context, "record_error", side_effect=RuntimeError("record failed")):
                    await handler.on_llm_error(error=ValueError("llm"), run_id=uuid.uuid4())
                    await handler.on_chain_error(error=ValueError("chain"), run_id=uuid.uuid4())

                with patch.object(context, "record_tool_result", side_effect=RuntimeError("tool record failed")):
                    await handler.on_tool_error(error=RuntimeError("tool"), run_id=uuid.uuid4())


def test_register_auto_patch_is_noop():
    from agent_debugger_sdk.adapters.langchain import register_auto_patch

    assert register_auto_patch() is None
