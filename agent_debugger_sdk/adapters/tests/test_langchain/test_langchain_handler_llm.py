"""Tests for LangChainTracingHandler LLM callback methods."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer

from .test_langchain_mocks import MockLLMResult


class TestLangChainTracingHandlerLLM:
    """Test LangChainTracingHandler LLM callbacks."""

    @pytest.mark.asyncio
    async def test_on_llm_start(self):
        """Test on_llm_start callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-llm-start")

            llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1
            assert llm_events[0].model == "gpt-4"
            assert llm_events[0].messages == [{"role": "user", "content": "Hello"}]

    @pytest.mark.asyncio
    async def test_on_llm_end(self):
        """Test on_llm_end callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-llm-end")

            llm_events = [e for e in events if e.event_type == EventType.LLM_RESPONSE]
            assert len(llm_events) == 1
            assert llm_events[0].content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_on_llm_end_extracts_tool_calls_from_generation_message(self):
        """Test on_llm_end preserves tool_calls returned by LangChain messages."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
            handler = LangChainTracingHandler(session_id="test-llm-tool-calls")
            context = TraceContext(
                session_id="test-llm-tool-calls",
                agent_name="test",
                framework="langchain",
            )

            run_id = uuid.uuid4()
            response = SimpleNamespace(
                generations=[
                    [
                        SimpleNamespace(
                            text="",
                            message=SimpleNamespace(
                                content="",
                                tool_calls=[
                                    {"id": "call-1", "name": "search", "args": {"q": "Belgrade"}},
                                ],
                            ),
                        )
                    ]
                ],
                llm_output={"token_usage": {"prompt_tokens": 8, "completion_tokens": 3}},
            )

            async with context:
                handler.set_context(context)
                await handler.on_llm_start(serialized={"name": "ChatOpenAI"}, prompts=["Hello"], run_id=run_id)
                await handler.on_llm_end(
                    response=response,
                    run_id=run_id,
                    invocation_params={"model_name": "glm-4.6"},
                )

            buffer = get_event_buffer()
            events = await buffer.get_events("test-llm-tool-calls")

            llm_event = next(e for e in events if e.event_type == EventType.LLM_RESPONSE)
            assert llm_event.model == "glm-4.6"
            assert llm_event.tool_calls == [{"id": "call-1", "name": "search", "arguments": {"q": "Belgrade"}}]

    @pytest.mark.asyncio
    async def test_on_llm_error(self):
        """Test on_llm_error callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-llm-error")

            error_events = [e for e in events if e.event_type == EventType.ERROR]
            assert len(error_events) == 1
            assert error_events[0].error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_on_llm_start_uses_parent_model_name_and_filtered_settings(self):
        """Test llm_start uses parent run mapping and model_name fallback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            llm_events = [
                e for e in await buffer.get_events("test-llm-model-name") if e.event_type == EventType.LLM_REQUEST
            ]
            assert len(llm_events) == 1
            assert llm_events[0].parent_id == "parent-event-id"
            assert llm_events[0].model == "gpt-4o-mini"
            assert llm_events[0].settings == {"temperature": 0.2, "max_tokens": 50}
