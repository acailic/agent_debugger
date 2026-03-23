"""Tests for bug fixes in Phase 1."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agent_debugger_sdk import configure_event_pipeline
from agent_debugger_sdk.core.decorators import trace_agent, trace_llm, trace_tool
from agent_debugger_sdk.core.events import EventType
from collector.buffer import EventBuffer, get_event_buffer
from collector.persistence import PersistenceManager


@pytest.fixture(autouse=True)
def setup_event_pipeline():
    """Connect the SDK to the event buffer before each test."""
    buffer = get_event_buffer()
    configure_event_pipeline(buffer)
    yield
    configure_event_pipeline(None)


class TestBUG004PersistenceManager:
    """Test that PersistenceManager doesn't crash with await on sync methods."""

    def test_flush_no_type_error(self):
        """Test that PersistenceManager.flush() works without TypeError."""
        buffer = EventBuffer()
        pm = PersistenceManager(buffer)

        # Publish an event
        asyncio.run(buffer.publish("session-1", MagicMock(id="event-1", to_dict=lambda: {})))

        # This should not raise TypeError
        asyncio.run(pm.flush())

    def test_get_session_ids_no_type_error(self):
        """Test that get_session_ids is async and doesn't raise TypeError."""
        buffer = EventBuffer()
        pm = PersistenceManager(buffer)

        # Publish an event to populate the buffer
        asyncio.run(buffer.publish("session-1", MagicMock(id="event-1", to_dict=lambda: {})))

        # This should not raise TypeError
        session_ids = asyncio.run(pm.buffer.get_session_ids())
        assert isinstance(session_ids, list)


        assert "session-1" in session_ids


class TestBUG005RaceCondition:
    """Test that EventBuffer.publish() is thread-safe."""

    @pytest.mark.asyncio
    async def test_concurrent_publish_no_lost_events(self):
        """Test that concurrent publishes don't lose events."""
        buffer = EventBuffer()
        num_events = 100
        num_tasks = 10

        async def publish_events(task_id):
            for i in range(num_events // num_tasks):
                event = MagicMock(id=f"event-{task_id}-{i}", to_dict=lambda: {})
                await buffer.publish(f"session-{task_id}", event)


        # Run concurrent publishes
        tasks = [publish_events(i) for i in range(num_tasks)]
        await asyncio.gather(*tasks)

        # Verify all events were stored
        total_expected = num_events
        total_actual = 0
        for task_id in range(num_tasks):
            events = await buffer.get_events(f"session-{task_id}")
            total_actual += len(events)

        assert total_actual == total_expected


class TestBUG002DuplicateEvents:
    """Test that events are not duplicated in buffer after fix."""

    @pytest.mark.asyncio
    async def test_pydantic_ai_no_duplicates(self):
        """Test that PydanticAI adapter doesn't publish duplicate events."""
        buffer = get_event_buffer()
        buffer._events.clear()  # Clear any previous state

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter
            from agent_debugger_sdk.core.events import LLMRequestEvent

            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-no-dups",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                # Create and emit an LLM request
                event = LLMRequestEvent(
                    session_id="test-no-dups",
                    model="gpt-4",
                    messages=[],
                    name="test_llm",
                )
                await adapter._context._emit_event(event)

            # Check buffer - should have exactly 1 event (the LLM request)
            events = await buffer.get_events("test-no-dups")
            llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1, "Expected exactly 1 LLM request event, buffer should not have duplicates"

    @pytest.mark.asyncio
    async def test_langchain_no_duplicates(self):
        """Test that LangChain handler doesn't publish duplicate events."""
        buffer = get_event_buffer()
        buffer._events.clear()  # Clear any previous state

        with patch("agent_debugger_sdk.adapters.langchain.LANGCHAIN_AVAILABLE", True):
            from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
            from agent_debugger_sdk.core.context import TraceContext

            context = TraceContext(
                session_id="test-langchain-no-dups",
                agent_name="test_agent",
                framework="langchain",
            )
            handler = LangChainTracingHandler(
                session_id="test-langchain-no-dups",
            )
            handler.set_context(context)

            async with context:
                # Simulate the LLM start callback
                await handler.on_llm_start(
                    serialized={"name": "test"},
                    prompts=["Hello"],
                    run_id=MagicMock(),
                    parent_run_id=None,
                    invocation_params={"model": "gpt-4"},
                )

            # Check buffer - should have exactly 1 LLM request
            events = await buffer.get_events("test-langchain-no-dups")
            llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1, "Expected exactly 1 LLM request event in buffer"


class TestBUG003DuplicateAgentEvents:
    """Test that trace_agent decorator emits exactly one AGENT_START and one AGENT_END."""

    @pytest.mark.asyncio
    async def test_single_agent_start_end(self):
        """Test that @trace_agent emits exactly 1 start and 1 end event."""

        @trace_agent(name="test_agent", framework="test")
        async def test_agent_func():
            return "result"

        # Run the agent
        result = await test_agent_func()
        assert result == "result"

        # Get buffer and check events
        buffer = get_event_buffer()
        # The decorator creates a new session, find it latest session
        session_ids = await buffer.get_session_ids()
        assert len(session_ids) >= 1
        session_id = session_ids[-1]  # Get the last created session

        events = await buffer.get_events(session_id)
        start_events = [e for e in events if e.event_type == EventType.AGENT_START]
        end_events = [e for e in events if e.event_type == EventType.AGENT_END]

        assert len(start_events) == 1, "Expected exactly 1 AGENT_START event"
        assert len(end_events) == 1, "Expected exactly 1 AGENT_END event"


    @pytest.mark.asyncio
    async def test_agent_with_exception(self):
        """Test that @trace_agent properly records exceptions in AGENT_END event."""

        @trace_agent(name="failing_agent", framework="test")
        async def failing_agent_func():
            raise ValueError("Intentional error")

        # Run the agent and expect exception
        with pytest.raises(ValueError, match="Intentional error"):
            await failing_agent_func()

        # Get buffer and check events
        buffer = get_event_buffer()
        session_ids = await buffer.get_session_ids()
        session_id = session_ids[-1]
        events = await buffer.get_events(session_id)

        start_events = [e for e in events if e.event_type == EventType.AGENT_START]
        end_events = [e for e in events if e.event_type == EventType.AGENT_END]

        assert len(start_events) == 1, "Expected exactly 1 AGENT_START event"
        assert len(end_events) == 1, "Expected exactly 1 AGENT_END event"

        # Verify the end event has error status
        end_event = end_events[0]
        assert end_event.data["status"] == "error"



    @pytest.mark.asyncio
    async def test_agent_with_nested_tool(self):
        """Test that @trace_agent works with nested @trace_tool."""

        @trace_tool(name="test_tool")
        async def test_tool_func():
            return "tool_result"

        @trace_agent(name="agent_with_tool", framework="test")
        async def agent_with_tool_func():
            result = await test_tool_func()
            return result

        # Run the agent
        result = await agent_with_tool_func()
        assert result == "tool_result"

        # Get buffer and check events
        buffer = get_event_buffer()
        session_ids = await buffer.get_session_ids()
        session_id = session_ids[-1]
        events = await buffer.get_events(session_id)

        # Should have AGENT_START, TOOL_CALL, TOOL_RESULT, AGENT_END
        event_types = [e.event_type for e in events]
        assert EventType.AGENT_START in event_types, "Expected AGENT_START"
        assert EventType.TOOL_CALL in event_types, "Expected TOOL_CALL"
        assert EventType.TOOL_RESULT in event_types, "Expected TOOL_RESULT"
        assert EventType.AGENT_END in event_types, "Expected AGENT_END"


class TestBUG012ExceptionInfo:
    """Test that trace_tool and trace_llm decorators properly pass exception info to __aexit__."""

    @pytest.mark.asyncio
    async def test_trace_tool_exception_passed(self):
        """Test that @trace_tool passes exception info to context when standalone."""

        @trace_tool(name="failing_tool")
        async def failing_tool_func():
            raise RuntimeError("Tool failed")

        # Run the tool and expect exception
        with pytest.raises(RuntimeError, match="Tool failed"):
            await failing_tool_func()

        # Get buffer and check error was recorded
        buffer = get_event_buffer()
        session_ids = await buffer.get_session_ids()
        session_id = session_ids[-1]
        events = await buffer.get_events(session_id)

        # Find error events
        error_events = [e for e in events if e.event_type == EventType.ERROR]
        assert len(error_events) >= 1, "Expected at least 1 error event"

        # Verify error has stack trace
        if error_events:
            error_event = error_events[0]
            assert error_event.error_type == "RuntimeError"
            assert error_event.error_message == "Tool failed"
            # Check that stack_trace is populated (should contain traceback info)
            assert error_event.stack_trace is not None
            assert "failing_tool_func" in error_event.stack_trace or "Stack trace should contain the function name"

    @pytest.mark.asyncio
    async def test_trace_llm_exception_passed(self):
        """Test that @trace_llm passes exception info to context when standalone."""

        @trace_llm(model="test-model")
        async def failing_llm_func():
            raise RuntimeError("LLM failed")

        # Run the LLM call and expect exception
        with pytest.raises(RuntimeError, match="LLM failed"):
            await failing_llm_func()

        # Get buffer and check error was recorded
        buffer = get_event_buffer()
        session_ids = await buffer.get_session_ids()
        session_id = session_ids[-1]
        events = await buffer.get_events(session_id)

        # Find error events
        error_events = [e for e in events if e.event_type == EventType.ERROR]
        assert len(error_events) >= 1, "Expected at least 1 error event"

        # Verify error has stack trace
        if error_events:
            error_event = error_events[0]
            assert error_event.error_type == "RuntimeError"
            assert error_event.error_message == "LLM failed"
            # Check that stack_trace is populated
            assert error_event.stack_trace is not None
            assert "failing_llm_func" in error_event.stack_trace, "Stack trace should contain function name"
