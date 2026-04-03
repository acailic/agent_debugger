"""Tests for LangChainTracingHandler chain callback methods."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer


class TestLangChainTracingHandlerChain:
    """Test LangChainTracingHandler chain callbacks."""

    @pytest.mark.asyncio
    async def test_on_chain_start(self):
        """Test on_chain_start callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-chain-start")

            chain_events = [e for e in events if e.name.startswith("chain_start_")]
            assert len(chain_events) == 1
            assert "chain" in chain_events[0].name

    @pytest.mark.asyncio
    async def test_on_chain_end(self):
        """Test on_chain_end callback."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-chain-end")

            chain_end_events = [e for e in events if e.name == "chain_end"]
            assert len(chain_end_events) == 1

    @pytest.mark.asyncio
    async def test_chain_callbacks_use_defaults_and_emit_errors(self):
        """Test chain callback default naming and chain error emission."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
        from agent_debugger_sdk.core.context import TraceContext

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
            events = await buffer.get_events("test-chain-fallbacks")
            chain_start = next(event for event in events if event.name.startswith("chain_start_"))
            chain_end = next(event for event in events if event.name == "chain_end")
            error_event = next(event for event in events if event.event_type == EventType.ERROR)

            assert chain_start.name == "chain_start_chain"
            assert chain_start.data["chain_type"] == "unknown"
            assert chain_end.event_type == EventType.AGENT_END
            assert error_event.error_message == "chain failed"
