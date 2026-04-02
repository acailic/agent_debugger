"""Tests for the simplified high-level API (trace decorator, trace_session)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.simple import _ensure_initialized, trace, trace_session


class TestEnsureInitialized:
    """Tests for _ensure_initialized idempotency."""

    def test_ensure_initialized_calls_init_once(self):
        """_ensure_initialized should call init() exactly once on multiple calls."""
        import agent_debugger_sdk.simple as simple_mod

        # Reset the flag
        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:
            # First call should invoke init
            _ensure_initialized()
            assert mock_init.call_count == 1
            assert simple_mod._initialized is True

            # Second call should be no-op
            _ensure_initialized()
            assert mock_init.call_count == 1  # Still 1, not 2
            assert simple_mod._initialized is True

    def test_ensure_initialized_idempotent(self):
        """Multiple calls to _ensure_initialized should only initialize once."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:
            for _ in range(5):
                _ensure_initialized()

            assert mock_init.call_count == 1
            assert simple_mod._initialized is True


class TestTraceDecorator:
    """Tests for the @trace decorator."""

    @pytest.mark.asyncio
    async def test_trace_decorator_bare_wraps_function(self):
        """@trace without arguments should wrap and execute the function."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                @trace
                async def my_agent(prompt: str) -> str:
                    return f"response to {prompt}"

                result = await my_agent("hello")
                assert result == "response to hello"
                assert my_agent.__name__ == "my_agent"

    @pytest.mark.asyncio
    async def test_trace_decorator_with_custom_name_and_framework(self):
        """@trace(name=..., framework=...) should use provided values."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                @trace(name="custom_name", framework="test_framework")
                async def my_agent(prompt: str) -> str:
                    return "ok"

                result = await my_agent("test")
                assert result == "ok"

                # Verify TraceContext was called with correct args
                MockCtx.assert_called_once_with(
                    agent_name="custom_name",
                    framework="test_framework",
                )

    @pytest.mark.asyncio
    async def test_trace_decorator_uses_qualname_as_default(self):
        """@trace should use function __qualname__ when name is not provided."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                @trace
                async def my_function() -> str:
                    return "result"

                await my_function()

                # Should use __qualname__ as agent name (includes full path)
                assert MockCtx.call_count == 1
                call_kwargs = MockCtx.call_args.kwargs
                assert "my_function" in call_kwargs["agent_name"]
                assert call_kwargs["framework"] == "custom"

    @pytest.mark.asyncio
    async def test_trace_decorator_with_session_start_event(self):
        """@trace should set parent when session_start_event exists."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                # Simulate having a session start event
                mock_event = MagicMock()
                mock_event.id = "session-start-123"
                mock_ctx._session_start_event = mock_event
                mock_ctx.set_parent = MagicMock()
                MockCtx.return_value = mock_ctx

                @trace
                async def my_agent() -> str:
                    return "done"

                await my_agent()

                # Should set parent to session start event ID
                mock_ctx.set_parent.assert_called_once_with("session-start-123")


class TestTraceSession:
    """Tests for the trace_session() context manager."""

    @pytest.mark.asyncio
    async def test_trace_session_yields_context(self):
        """trace_session() should yield a TraceContext."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                async with trace_session("test_agent") as ctx:
                    assert ctx is mock_ctx

                # Verify TraceContext was created with correct args
                MockCtx.assert_called_once_with(
                    agent_name="test_agent",
                    framework="custom",
                    session_id=None,
                    tags=None,
                )

    @pytest.mark.asyncio
    async def test_trace_session_with_custom_parameters(self):
        """trace_session() should accept and pass custom parameters."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                async with trace_session(
                    agent_name="custom_agent",
                    framework="langchain",
                    session_id="custom-123",
                    tags=["test", "demo"],
                ) as ctx:
                    assert ctx is mock_ctx

                # Verify all parameters were passed
                MockCtx.assert_called_once_with(
                    agent_name="custom_agent",
                    framework="langchain",
                    session_id="custom-123",
                    tags=["test", "demo"],
                )

    @pytest.mark.asyncio
    async def test_trace_session_can_record_events(self):
        """trace_session() context should allow recording events."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                mock_ctx.record_decision = AsyncMock(return_value="event-123")
                MockCtx.return_value = mock_ctx

                async with trace_session("agent") as ctx:
                    event_id = await ctx.record_decision(
                        reasoning="test reasoning",
                        confidence=0.9,
                        chosen_action="test_action",
                    )
                    assert event_id == "event-123"

                # Verify record_decision was called
                mock_ctx.record_decision.assert_called_once_with(
                    reasoning="test reasoning",
                    confidence=0.9,
                    chosen_action="test_action",
                )

    @pytest.mark.asyncio
    async def test_trace_session_with_session_start_event(self):
        """trace_session() should set parent when session_start_event exists."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                # Simulate having a session start event
                mock_event = MagicMock()
                mock_event.id = "session-start-456"
                mock_ctx._session_start_event = mock_event
                mock_ctx.set_parent = MagicMock()
                MockCtx.return_value = mock_ctx

                async with trace_session("agent") as ctx:
                    assert ctx is mock_ctx

                # Should set parent to session start event ID
                mock_ctx.set_parent.assert_called_once_with("session-start-456")

    @pytest.mark.asyncio
    async def test_trace_session_handles_exceptions(self):
        """trace_session() should propagate exceptions properly."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init"):
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                with pytest.raises(ValueError, match="test error"):
                    async with trace_session("agent"):
                        raise ValueError("test error")

                # Verify __aexit__ was called with exception info
                mock_ctx.__aexit__.assert_called_once()
                exit_args = mock_ctx.__aexit__.call_args[0]
                # exc_type, exc_value, traceback
                assert exit_args[0] is ValueError
                assert isinstance(exit_args[1], ValueError)
                assert str(exit_args[1]) == "test error"


class TestIntegration:
    """Integration tests for simple API behavior."""

    def test_init_called_on_first_trace_use(self):
        """init() should be called when @trace is first used."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:
            # Create a traced function
            @trace
            async def agent() -> str:
                return "ok"

            # init should be called during decoration
            assert mock_init.call_count == 1
            assert simple_mod._initialized is True

    @pytest.mark.asyncio
    async def test_init_called_on_first_trace_session_use(self):
        """init() should be called when trace_session() is first used."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:
            with patch("agent_debugger_sdk.core.context.TraceContext") as MockCtx:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_ctx._session_start_event = None
                MockCtx.return_value = mock_ctx

                # trace_session is a generator, so init is called when we enter the context
                async with trace_session("agent"):
                    # init should be called during context entry
                    assert mock_init.call_count == 1
                    assert simple_mod._initialized is True

    def test_multiple_trace_decorators_share_initialization(self):
        """Multiple @trace decorators should share a single initialization."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:

            @trace
            async def agent1() -> str:
                return "1"

            @trace
            async def agent2() -> str:
                return "2"

            # init should only be called once
            assert mock_init.call_count == 1
            assert simple_mod._initialized is True

    def test_trace_and_trace_session_share_initialization(self):
        """@trace and trace_session() should share a single initialization."""
        import agent_debugger_sdk.simple as simple_mod

        simple_mod._initialized = False

        with patch("agent_debugger_sdk.simple.init") as mock_init:

            @trace
            async def agent() -> str:
                return "ok"

            with patch("agent_debugger_sdk.core.context.TraceContext"):
                trace_session("agent")

            # init should only be called once across both
            assert mock_init.call_count == 1
            assert simple_mod._initialized is True
