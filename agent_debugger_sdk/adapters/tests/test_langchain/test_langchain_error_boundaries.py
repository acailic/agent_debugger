"""Tests for error boundary handling in LangChain adapter."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest


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
                with patch.object(context, "_emit_event", side_effect=RuntimeError("Callback failed")):
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

        from .test_langchain_mocks import MockLLMResult

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
                with patch.object(context, "_emit_event", side_effect=ValueError("Emit failed")):
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
                with patch.object(context, "_emit_event", side_effect=RuntimeError("Tool callback failed")):
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
                with patch.object(context, "record_tool_result", side_effect=ValueError("Record failed")):
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
                with patch.object(context, "_emit_event", side_effect=RuntimeError("Chain callback failed")):
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
                with patch.object(context, "_emit_event", side_effect=ValueError("Chain end failed")):
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
