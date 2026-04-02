"""Tests for the simplified high-level API (trace decorator, trace_session)."""

from __future__ import annotations

import pytest

from agent_debugger_sdk import trace, trace_session
from agent_debugger_sdk.simple import _ensure_initialized


class TestTraceDecorator:
    """Tests for the @trace decorator."""

    def test_trace_imports(self) -> None:
        """trace and trace_session should be importable from the SDK."""
        from agent_debugger_sdk import trace, trace_session  # noqa: F401

    def test_ensure_initialized(self) -> None:
        """_ensure_initialized should call init() exactly once."""
        # Reset to test idempotency
        import agent_debugger_sdk.simple as simple_mod
        from agent_debugger_sdk.config import get_config

        simple_mod._initialized = False

        _ensure_initialized()
        assert simple_mod._initialized is True
        config = get_config()
        assert config.enabled is True

        # Second call should be no-op
        _ensure_initialized()
        assert simple_mod._initialized is True

    @pytest.mark.asyncio
    async def test_trace_decorator_bare(self) -> None:
        """@trace without arguments should auto-name from function."""

        @trace
        async def my_agent(prompt: str) -> str:
            return f"response to {prompt}"

        result = await my_agent("hello")
        assert result == "response to hello"
        assert my_agent.__name__ == "my_agent"

    @pytest.mark.asyncio
    async def test_trace_decorator_with_options(self) -> None:
        """@trace(name=..., framework=...) should use provided values."""

        @trace(name="custom_name", framework="pydantic_ai")
        async def my_agent(prompt: str) -> str:
            return "ok"

        result = await my_agent("test")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_trace_decorator_captures_session(self) -> None:
        """@trace should create a TraceContext with a session."""
        from agent_debugger_sdk.core.context import get_current_context

        captured_ctx = None

        @trace(name="session_test_agent")
        async def my_agent() -> str:
            nonlocal captured_ctx
            captured_ctx = get_current_context()
            return "done"

        await my_agent()
        assert captured_ctx is not None
        assert captured_ctx.session.agent_name == "session_test_agent"

    @pytest.mark.asyncio
    async def test_trace_decorator_handles_error(self) -> None:
        """@trace should propagate errors after recording them."""

        @trace(name="failing_agent")
        async def failing_agent() -> str:
            raise ValueError("agent error")

        with pytest.raises(ValueError, match="agent error"):
            await failing_agent()

    @pytest.mark.asyncio
    async def test_trace_decorator_uses_qualname_as_default(self) -> None:
        """@trace should use function __qualname__ when name is not provided."""
        from agent_debugger_sdk.core.context import get_current_context

        captured_name = None

        @trace
        async def deeply_nested() -> str:
            nonlocal captured_name
            ctx = get_current_context()
            if ctx:
                captured_name = ctx.session.agent_name
            return "ok"

        await deeply_nested()
        assert captured_name.endswith("deeply_nested")


class TestTraceSession:
    """Tests for the trace_session() context manager."""

    @pytest.mark.asyncio
    async def test_trace_session_basic(self) -> None:
        """trace_session() should yield a TraceContext."""
        async with trace_session("test_agent") as ctx:
            assert ctx is not None
            assert ctx.session.agent_name == "test_agent"

    @pytest.mark.asyncio
    async def test_trace_session_records_decision(self) -> None:
        """trace_session() should allow recording decisions."""
        async with trace_session("decision_agent") as ctx:
            event_id = await ctx.record_decision(
                reasoning="test reasoning",
                confidence=0.9,
                chosen_action="test_action",
                evidence=[],
            )
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_trace_session_records_tool_call_and_result(self) -> None:
        """trace_session() should allow recording tool calls."""
        async with trace_session("tool_agent") as ctx:
            await ctx.record_tool_call("search", {"query": "test"})
            await ctx.record_tool_result("search", result={"items": []}, duration_ms=50)

    @pytest.mark.asyncio
    async def test_trace_session_custom_framework(self) -> None:
        """trace_session() should accept framework parameter."""
        async with trace_session("lc_agent", framework="langchain") as ctx:
            assert ctx.session.framework == "langchain"

    @pytest.mark.asyncio
    async def test_trace_session_custom_session_id(self) -> None:
        """trace_session() should accept custom session_id."""
        async with trace_session("agent", session_id="custom-123") as ctx:
            assert ctx.session_id == "custom-123"

    @pytest.mark.asyncio
    async def test_trace_session_with_tags(self) -> None:
        """trace_session() should accept tags."""
        async with trace_session("tagged_agent", tags=["test", "demo"]) as ctx:
            assert "test" in ctx.session.tags
            assert "demo" in ctx.session.tags

    @pytest.mark.asyncio
    async def test_trace_session_handles_error(self) -> None:
        """trace_session() should record errors and propagate them."""
        with pytest.raises(RuntimeError, match="boom"):
            async with trace_session("error_agent"):
                raise RuntimeError("boom")
