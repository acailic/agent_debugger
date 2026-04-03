"""Tests for LangChainTracingHandler edge cases and error handling."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from .test_langchain_mocks import MockLLMResult


class TestLangChainTracingHandlerEdgeCases:
    """Test LangChainTracingHandler edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_import_error_without_langchain(self):
        """Test that ImportError is raised when LangChain is not available."""
        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", False):
            with pytest.raises(ImportError, match="LangChain is not installed"):
                from agent_debugger_sdk.adapters.langchain.handler import LangChainTracingHandler

                LangChainTracingHandler(session_id="test")

    @pytest.mark.asyncio
    async def test_callbacks_are_noops_without_context(self):
        """Test callbacks return early when no trace context is set."""
        from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler

        with patch("agent_debugger_sdk.adapters.langchain.handler.LANGCHAIN_AVAILABLE", True):
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
