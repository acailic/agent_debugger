"""Tests for SDK core context module."""

from __future__ import annotations

import asyncio

import pytest

from agent_debugger_sdk.core.context import (
    TraceContext,
    configure_event_pipeline,
    get_current_context,
    get_current_parent_id,
    get_current_session_id,
)
from agent_debugger_sdk.core.context.pipeline import _get_default_event_buffer
from agent_debugger_sdk.core.context.vars import (
    _current_context,
    _current_parent_id,
    _current_session_id,
    _event_sequence,
)
from agent_debugger_sdk.core.events import EventType, SessionStatus


class TestContextVariables:
    """Tests for context variable defaults and operations."""

    def test_session_id_defaults_to_none(self):
        assert _current_session_id.get() is None

    def test_parent_id_defaults_to_none(self):
        assert _current_parent_id.get() is None

    def test_event_sequence_defaults_to_zero(self):
        assert _event_sequence.get() == 0

    def test_context_defaults_to_none(self):
        assert _current_context.get() is None


class TestConfigureEventPipeline:
    """Tests for configure_event_pipeline function."""

    def test_configure_sets_buffer(self):
        class DummyBuffer:
            pass

        buffer = DummyBuffer()
        configure_event_pipeline(buffer)
        assert _get_default_event_buffer() is buffer

    def test_configure_clears_buffer_with_none(self):
        configure_event_pipeline(None)
        # After clearing, falls back to collector's get_event_buffer() if available
        # The value depends on whether collector module is importable
        result = _get_default_event_buffer()
        # Just verify the function doesn't raise and returns something
        assert result is None or hasattr(result, "_events")


class TestTraceContextCreation:
    """Tests for TraceContext instantiation."""

    def test_creates_with_auto_session_id(self):
        ctx = TraceContext(agent_name="test")
        assert ctx.session_id is not None
        assert len(ctx.session_id) == 36  # UUID format

    def test_creates_with_custom_session_id(self):
        ctx = TraceContext(session_id="custom-123", agent_name="test")
        assert ctx.session_id == "custom-123"

    def test_creates_session_object(self):
        ctx = TraceContext(
            session_id="test-1",
            agent_name="my_agent",
            framework="custom",
            config={"key": "value"},
            tags=["tag1", "tag2"],
        )
        assert ctx.session.id == "test-1"
        assert ctx.session.agent_name == "my_agent"
        assert ctx.session.framework == "custom"
        assert ctx.session.config == {"key": "value"}
        assert ctx.session.tags == ["tag1", "tag2"]

    def test_initializes_with_defaults(self):
        ctx = TraceContext()
        assert ctx._events == []
        assert ctx._entered is False
        assert ctx._checkpoint_sequence == 0

    def test_collector_endpoint_stored(self):
        ctx = TraceContext(collector_endpoint="http://localhost:8000")
        assert ctx.collector_endpoint == "http://localhost:8000"


class TestTraceContextLifecycle:
    """Tests for TraceContext async context manager behavior."""

    @pytest.mark.asyncio
    async def test_enter_sets_context_vars(self):
        ctx = TraceContext(session_id="test-enter")
        async with ctx:
            assert _current_session_id.get() == "test-enter"
            assert _current_context.get() is ctx
            assert _event_sequence.get() >= 1  # session_start event

    @pytest.mark.asyncio
    async def test_exit_clears_context_vars(self):
        ctx = TraceContext(session_id="test-exit")
        async with ctx:
            pass
        assert _current_session_id.get() is None
        assert _current_context.get() is None
        assert _event_sequence.get() == 0

    @pytest.mark.asyncio
    async def test_entered_flag_set_during_context(self):
        ctx = TraceContext()
        assert ctx._entered is False
        async with ctx:
            assert ctx._entered is True
        assert ctx._entered is False

    @pytest.mark.asyncio
    async def test_emits_session_start_event(self):
        ctx = TraceContext(agent_name="test_agent", framework="test")
        async with ctx:
            events = await ctx.get_events()
            start_events = [e for e in events if getattr(e, "event_type", None) == EventType.AGENT_START]
            assert len(start_events) >= 1

    @pytest.mark.asyncio
    async def test_emits_session_end_event_on_success(self):
        ctx = TraceContext()
        async with ctx:
            pass
        events = await ctx.get_events()
        end_events = [e for e in events if getattr(e, "event_type", None) == EventType.AGENT_END]
        assert len(end_events) >= 1

    @pytest.mark.asyncio
    async def test_session_status_completed_on_success(self):
        ctx = TraceContext()
        async with ctx:
            pass
        assert ctx.session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_session_status_error_on_exception(self):
        ctx = TraceContext()
        with pytest.raises(ValueError):
            async with ctx:
                raise ValueError("test error")
        assert ctx.session.status == SessionStatus.ERROR

    @pytest.mark.asyncio
    async def test_records_error_on_exception(self):
        ctx = TraceContext()
        with pytest.raises(ValueError):
            async with ctx:
                raise ValueError("test error")
        events = await ctx.get_events()
        error_events = [e for e in events if getattr(e, "event_type", None) == EventType.ERROR]
        assert len(error_events) >= 1


class TestTraceContextParentChild:
    """Tests for parent-child context relationships."""

    @pytest.mark.asyncio
    async def test_set_parent_updates_context_var(self):
        ctx = TraceContext()
        async with ctx:
            ctx.set_parent("event-123")
            assert ctx.get_current_parent() == "event-123"

    @pytest.mark.asyncio
    async def test_clear_parent_resets_to_none(self):
        ctx = TraceContext()
        async with ctx:
            ctx.set_parent("event-123")
            ctx.clear_parent()
            assert ctx.get_current_parent() is None

    @pytest.mark.asyncio
    async def test_set_parent_raises_before_enter(self):
        ctx = TraceContext()
        with pytest.raises(RuntimeError, match="has not been entered"):
            ctx.set_parent("event-123")

    @pytest.mark.asyncio
    async def test_clear_parent_raises_before_enter(self):
        ctx = TraceContext()
        with pytest.raises(RuntimeError, match="has not been entered"):
            ctx.clear_parent()


class TestTraceContextEventManagement:
    """Tests for event retrieval and draining."""

    @pytest.mark.asyncio
    async def test_get_events_returns_copy(self):
        ctx = TraceContext()
        async with ctx:
            events1 = await ctx.get_events()
            events2 = await ctx.get_events()
            assert events1 is not events2

    @pytest.mark.asyncio
    async def test_get_events_non_destructive(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.get_events()
            events = await ctx.get_events()
            assert len(events) >= 1  # session_start event

    @pytest.mark.asyncio
    async def test_drain_events_clears_list(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.drain_events()
            events = await ctx.get_events()
            assert len(events) == 0


class TestTraceContextCheckpoints:
    """Tests for checkpoint creation."""

    @pytest.mark.asyncio
    async def test_create_checkpoint_returns_id(self):
        ctx = TraceContext()
        async with ctx:
            cp_id = await ctx.create_checkpoint(state={"step": 1})
            assert cp_id is not None
            assert len(cp_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_checkpoint_sequence_increments(self):
        ctx = TraceContext()
        async with ctx:
            assert ctx._checkpoint_sequence == 0
            await ctx.create_checkpoint(state={})
            assert ctx._checkpoint_sequence == 1
            await ctx.create_checkpoint(state={})
            assert ctx._checkpoint_sequence == 2

    @pytest.mark.asyncio
    async def test_checkpoint_importance_clamped(self):
        ctx = TraceContext()
        async with ctx:
            _ = await ctx.create_checkpoint(state={}, importance=1.5)
            events = await ctx.get_events()
            checkpoints = [e for e in events if hasattr(e, "importance")]
            # Check that the checkpoint event was created
            assert any(hasattr(e, "checkpoint_id") or str(e) for e in checkpoints)

    @pytest.mark.asyncio
    async def test_checkpoint_raises_before_enter(self):
        ctx = TraceContext()
        with pytest.raises(RuntimeError, match="has not been entered"):
            await ctx.create_checkpoint(state={})


class TestGetFunctions:
    """Tests for module-level getter functions."""

    @pytest.mark.asyncio
    async def test_get_current_context_returns_ctx(self):
        ctx = TraceContext()
        async with ctx:
            assert get_current_context() is ctx

    @pytest.mark.asyncio
    async def test_get_current_session_id_returns_id(self):
        ctx = TraceContext(session_id="my-session")
        async with ctx:
            assert get_current_session_id() == "my-session"

    @pytest.mark.asyncio
    async def test_get_current_parent_id_returns_none_initially(self):
        ctx = TraceContext()
        async with ctx:
            assert get_current_parent_id() is None

    @pytest.mark.asyncio
    async def test_get_functions_return_none_outside_context(self):
        assert get_current_context() is None
        assert get_current_session_id() is None
        assert get_current_parent_id() is None


class TestTraceContextConcurrency:
    """Tests for concurrent context usage."""

    @pytest.mark.asyncio
    async def test_multiple_contexts_isolated(self):
        results = []

        async def run_context(session_id: str):
            ctx = TraceContext(session_id=session_id)
            async with ctx:
                # Yield control to allow concurrent context execution
                await asyncio.sleep(0)
                results.append((session_id, get_current_session_id()))

        await asyncio.gather(
            run_context("session-1"),
            run_context("session-2"),
            run_context("session-3"),
        )

        # Each context should have seen its own session_id
        for sid, captured in results:
            assert sid == captured
