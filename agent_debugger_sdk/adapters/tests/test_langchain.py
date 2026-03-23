"""Tests for LangChain adapter."""

from __future__ import annotations

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
