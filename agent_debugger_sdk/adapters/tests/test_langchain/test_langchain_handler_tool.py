"""Tests for LangChainTracingHandler tool callback methods."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer


class TestLangChainTracingHandlerTool:
    """Test LangChainTracingHandler tool callbacks."""

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
            events = await buffer.get_events("test-tool-start")

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
            events = await buffer.get_events("test-tool-end")

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
            events = await buffer.get_events("test-tool-error")

            tool_result_events = [e for e in events if e.event_type == EventType.TOOL_RESULT]
            assert len(tool_result_events) == 1
            assert tool_result_events[0].error == "Tool failed"

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
            tool_call = next(
                e for e in await buffer.get_events("test-tool-fallbacks") if e.event_type == EventType.TOOL_CALL
            )
            tool_result = next(
                e for e in await buffer.get_events("test-tool-fallbacks") if e.event_type == EventType.TOOL_RESULT
            )

            assert tool_call.parent_id == "parent-tool-event"
            assert tool_call.tool_name == "fallback_tool"
            assert tool_call.arguments == {"query": "Belgrade"}
            assert tool_result.tool_name == "unknown"
            assert tool_result.result == "weird-output"
