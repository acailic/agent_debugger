"""Tests for LangChainTracingHandler initialization and context management."""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


class TestLangChainTracingHandlerInit:
    """Test LangChainTracingHandler initialization and context management."""

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
