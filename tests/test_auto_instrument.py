"""Tests for auto-instrumentation registry."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from agent_debugger_sdk.auto_instrument import AutoInstrumentor
from agent_debugger_sdk.auto_instrument import get_instrumentor
from agent_debugger_sdk.auto_instrument import _register_defaults


class TestAutoInstrumentor:
    """Test AutoInstrumentor registry functionality."""

    def test_register_and_list_instrumentors(self):
        """Test registering and listing framework instrumentors."""
        ai = AutoInstrumentor()
        ai.register("langchain", lambda: None)
        assert "langchain" in ai.available()

    def test_register_multiple_frameworks(self):
        """Test registering multiple frameworks."""
        ai = AutoInstrumentor()
        ai.register("langchain", lambda: None)
        ai.register("crewai", lambda: None)
        ai.register("pydanticai", lambda: None)

        available = ai.available()
        assert len(available) == 3
        assert "langchain" in available
        assert "crewai" in available
        assert "pydanticai" in available

    def test_instrument_calls_registered_hook(self):
        """Test that instrument() calls the registered hook."""
        called = []
        ai = AutoInstrumentor()
        ai.register("langchain", lambda: called.append(True))
        ai.instrument("langchain")
        assert called == [True]

    def test_instrument_unknown_framework_is_noop(self):
        """Test that instrumenting unknown framework is a no-op."""
        ai = AutoInstrumentor()
        # Should not raise
        ai.instrument("nonexistent")

    def test_instrument_handles_hook_exceptions_gracefully(self):
        """Test that exceptions in hooks are caught and logged."""
        ai = AutoInstrumentor()
        ai.register("broken", lambda: (_ for _ in ()).throw(ValueError("boom")))

        # Should not raise
        ai.instrument("broken")

    def test_instrument_all_calls_all_hooks(self):
        """Test that instrument_all() calls all registered hooks."""
        called = []
        ai = AutoInstrumentor()
        ai.register("langchain", lambda: called.append("langchain"))
        ai.register("crewai", lambda: called.append("crewai"))

        ai.instrument_all()

        assert "langchain" in called
        assert "crewai" in called

    def test_instrument_all_continues_on_failure(self):
        """Test that instrument_all() continues even if one hook fails."""
        called = []
        ai = AutoInstrumentor()
        ai.register("broken", lambda: (_ for _ in ()).throw(ValueError("boom")))
        ai.register("working", lambda: called.append(True))

        ai.instrument_all()

        # Working hook should still be called despite broken hook
        assert called == [True]

    def test_get_instrumentor_returns_singleton(self):
        """Test that get_instrumentor returns the global instance."""
        instrumentor1 = get_instrumentor()
        instrumentor2 = get_instrumentor()
        assert instrumentor1 is instrumentor2

    def test_register_overwrites_existing_hook(self):
        """Test that registering a framework twice overwrites the hook."""
        ai = AutoInstrumentor()
        hook1 = MagicMock()
        hook2 = MagicMock()

        ai.register("langchain", hook1)
        ai.register("langchain", hook2)

        ai.instrument("langchain")

        hook2.assert_called_once()
        hook1.assert_not_called()

    def test_available_returns_empty_list_initially(self):
        """Test that available() returns empty list for new instrumentor."""
        ai = AutoInstrumentor()
        assert ai.available() == []

    def test_multiple_registers_same_framework(self):
        """Test registering same framework multiple times updates the hook."""
        ai = AutoInstrumentor()
        call_count = []

        ai.register("fw", lambda: call_count.append(1))
        ai.register("fw", lambda: call_count.append(2))

        ai.instrument("fw")
        assert call_count == [2]

    def test_register_defaults_registers_langchain_when_available(self):
        """Test default registration path when langchain is importable."""
        fake_langchain = MagicMock()
        with patch.dict(sys.modules, {"langchain": fake_langchain}), patch(
            "agent_debugger_sdk.adapters.langchain.register_auto_patch"
        ) as register_auto_patch, patch(
            "agent_debugger_sdk.auto_instrument._global_instrumentor.register"
        ) as register:
            _register_defaults()

        register.assert_called_once_with("langchain", register_auto_patch)
