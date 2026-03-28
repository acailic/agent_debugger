"""Tests for LangChainAdapter functionality."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_debugger_sdk.core.events import EventType
from collector.buffer import get_event_buffer


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
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter, LangChainTracingHandler

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
            events = await buffer.get_events("test-context-session")

            assert len(events) >= 2
            assert events[0].event_type == EventType.AGENT_START
            assert events[-1].event_type == EventType.AGENT_END

    @pytest.mark.asyncio
    async def test_get_callbacks(self):
        """Test get_callbacks returns handler list."""
        from agent_debugger_sdk.adapters.langchain import LangChainAdapter, LangChainTracingHandler

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
