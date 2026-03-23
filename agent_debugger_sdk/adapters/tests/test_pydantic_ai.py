"""Tests for PydanticAI adapter."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from collector.buffer import get_event_buffer

from agent_debugger_sdk.core.events import EventType


class MockAgent:
    """Mock PydanticAI Agent for testing."""

    def __init__(self, name: str = "test_agent"):
        self.name = name
        self.run = AsyncMock(return_value=MagicMock(all_messages=lambda: []))


class TestPydanticAIAdapter:
    """Test PydanticAIAdapter functionality."""

    @pytest.mark.asyncio
    async def test_adapter_initialization(self):
        """Test adapter initializes correctly."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            mock_agent.__class__.__name__ = "Agent"

            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-session",
                agent_name="test_agent",
                tags=["test"],
            )

            assert adapter.session_id == "test-session"
            assert adapter.agent_name == "test_agent"
            assert adapter.tags == ["test"]

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self):
        """Test context manager creates a session."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-session",
                agent_name="test_agent",
            )

            session_id = None
            async with adapter.trace_session() as sid:
                session_id = sid

            assert session_id == "test-session"

    @pytest.mark.asyncio
    async def test_context_manager_emits_events(self):
        """Test context manager emits start and end events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-session-events",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                pass

            buffer = get_event_buffer()
            events = buffer.get_events("test-session-events")

            assert len(events) >= 2
            assert events[0].event_type == EventType.AGENT_START
            assert events[-1].event_type == EventType.AGENT_END

    @pytest.mark.asyncio
    async def test_record_llm_request(self):
        """Test recording LLM request events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-llm-request",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                await adapter.record_llm_request(
                    model="gpt-4",
                    messages=[{"role": "user", "content": "Hello"}],
                    tools=[{"name": "test_tool"}],
                    settings={"temperature": 0.7},
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-llm-request")

            llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
            assert len(llm_events) == 1
            assert llm_events[0].model == "gpt-4"
            assert llm_events[0].messages == [{"role": "user", "content": "Hello"}]

    @pytest.mark.asyncio
    async def test_record_llm_response(self):
        """Test recording LLM response events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-llm-response",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                await adapter.record_llm_response(
                    model="gpt-4",
                    content="Hello, world!",
                    usage={"input_tokens": 10, "output_tokens": 5},
                    cost_usd=0.001,
                    duration_ms=100.5,
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-llm-response")

            llm_events = [e for e in events if e.event_type == EventType.LLM_RESPONSE]
            assert len(llm_events) == 1
            assert llm_events[0].content == "Hello, world!"
            assert llm_events[0].duration_ms == 100.5

    @pytest.mark.asyncio
    async def test_record_tool_call(self):
        """Test recording tool call events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-tool-call",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                await adapter.record_tool_call(
                    tool_name="search",
                    arguments={"query": "test query"},
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-tool-call")

            tool_events = [e for e in events if e.event_type == EventType.TOOL_CALL]
            assert len(tool_events) == 1
            assert tool_events[0].tool_name == "search"
            assert tool_events[0].arguments == {"query": "test query"}

    @pytest.mark.asyncio
    async def test_record_tool_result(self):
        """Test recording tool result events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            mock_agent = MagicMock()
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-tool-result",
                agent_name="test_agent",
            )

            async with adapter.trace_session():
                await adapter.record_tool_result(
                    tool_name="search",
                    result=["result1", "result2"],
                    duration_ms=50.2,
                )

            buffer = get_event_buffer()
            events = buffer.get_events("test-tool-result")

            tool_events = [e for e in events if e.event_type == EventType.TOOL_RESULT]
            assert len(tool_events) == 1
            assert tool_events[0].tool_name == "search"
            assert tool_events[0].result == ["result1", "result2"]

    @pytest.mark.asyncio
    async def test_import_error_without_pydantic_ai(self):
        """Test that ImportError is raised when PydanticAI is not available."""
        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", False):
            with pytest.raises(ImportError, match="PydanticAI is not installed"):
                from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

                PydanticAIAdapter(MagicMock())

    @pytest.mark.asyncio
    async def test_instrument_wraps_run_once_and_captures_tool_call_parts(self):
        """Test instrument() wraps run idempotently and captures tool-call parts."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter
        from agent_debugger_sdk.adapters.pydantic_ai import _pydantic_run_context

        class FakeToolCallPart:
            def __init__(self, tool_name: str, args):
                self.tool_name = tool_name
                self.args = args

        result = MagicMock(
            all_messages=lambda: [
                SimpleNamespace(
                    parts=[
                        FakeToolCallPart("search", {"query": "Belgrade"}),
                        FakeToolCallPart("lookup", "raw-input"),
                        object(),
                    ]
                )
            ]
        )
        mock_agent = MockAgent()
        mock_agent.run = AsyncMock(return_value=result)

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True), patch(
            "agent_debugger_sdk.adapters.pydantic_ai.ToolCallPart", FakeToolCallPart, create=True
        ):
            adapter = PydanticAIAdapter(
                mock_agent,
                session_id="test-instrumented-run",
                agent_name="instrumented_agent",
                tags=["coverage"],
            )

            instrumented = adapter.instrument()
            assert adapter.instrument() is instrumented

            returned = await instrumented.run(
                "Hello",
                message_history=[],
                model="gpt-4o-mini",
                retries=2,
            )

        assert returned is result
        adapter._original_run.assert_awaited_once_with(
            "Hello",
            message_history=[],
            model="gpt-4o-mini",
            retries=2,
        )
        assert _pydantic_run_context.get() is None

        buffer = get_event_buffer()
        events = buffer.get_events("test-instrumented-run")
        tool_calls = [event for event in events if event.event_type == EventType.TOOL_CALL]

        assert len(tool_calls) == 2
        assert tool_calls[0].tool_name == "search"
        assert tool_calls[0].arguments == {"query": "Belgrade"}
        assert tool_calls[1].tool_name == "lookup"
        assert tool_calls[1].arguments == {"args": "raw-input"}

    @pytest.mark.asyncio
    async def test_adapter_methods_return_empty_without_context(self):
        """Test adapter helpers are no-ops when no trace context is active."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

        with patch("agent_debugger_sdk.adapters.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            adapter = PydanticAIAdapter(MagicMock(), session_id="no-context", agent_name="test_agent")

            assert await adapter.record_llm_request("gpt-4", []) == ""
            assert await adapter.record_llm_response("gpt-4", "hello") == ""
            assert await adapter.record_tool_call("search", {"q": "x"}) == ""
            assert await adapter.record_tool_result("search", {"ok": True}) == ""

            await adapter._capture_result(MagicMock(all_messages=lambda: []))
            await adapter._process_messages([MagicMock()])
            await adapter._emit_message_event(MagicMock(parts=[]))


class TestPydanticAIInstrumentor:
    """Test PydanticAIInstrumentor functionality."""

    @pytest.mark.asyncio
    async def test_instrumentor_initialization(self):
        """Test instrumentor initializes correctly."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor

        instrumentor = PydanticAIInstrumentor(session_id="test-session")
        assert instrumentor.session_id == "test-session"
        assert instrumentor._context is None

    @pytest.mark.asyncio
    async def test_on_model_request(self):
        """Test on_model_request emits event."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor
        from agent_debugger_sdk.core.context import TraceContext

        instrumentor = PydanticAIInstrumentor(session_id="test-instrumentor")
        context = TraceContext(
            session_id="test-instrumentor",
            agent_name="test",
            framework="pydantic_ai",
        )

        async with context:
            instrumentor.set_context(context)

            await instrumentor.on_model_request(
                {
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "tools": [],
                    "settings": {"temperature": 0.7},
                }
            )

        buffer = get_event_buffer()
        events = buffer.get_events("test-instrumentor")

        llm_events = [e for e in events if e.event_type == EventType.LLM_REQUEST]
        assert len(llm_events) == 1
        assert llm_events[0].model == "gpt-4"

    @pytest.mark.asyncio
    async def test_on_model_response(self):
        """Test on_model_response emits event."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor
        from agent_debugger_sdk.core.context import TraceContext

        instrumentor = PydanticAIInstrumentor(session_id="test-instrumentor-resp")
        context = TraceContext(
            session_id="test-instrumentor-resp",
            agent_name="test",
            framework="pydantic_ai",
        )

        async with context:
            instrumentor.set_context(context)

            request_id = str(uuid.uuid4())
            instrumentor._start_times[request_id] = 0

            await instrumentor.on_model_response(
                {
                    "request_id": request_id,
                    "model": "gpt-4",
                    "content": "Hello!",
                    "tool_calls": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }
            )

        buffer = get_event_buffer()
        events = buffer.get_events("test-instrumentor-resp")

        llm_events = [e for e in events if e.event_type == EventType.LLM_RESPONSE]
        assert len(llm_events) == 1
        assert llm_events[0].content == "Hello!"

    @pytest.mark.asyncio
    async def test_on_tool_call_and_result_emit_events(self):
        """Test tool call and result hooks emit tool events."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor
        from agent_debugger_sdk.core.context import TraceContext

        instrumentor = PydanticAIInstrumentor(session_id="test-instrumentor-tool")
        context = TraceContext(
            session_id="test-instrumentor-tool",
            agent_name="test",
            framework="pydantic_ai",
        )

        async with context:
            instrumentor.set_context(context)
            await instrumentor.on_tool_call({"tool_name": "search", "arguments": {"q": "trace"}})
            await instrumentor.on_tool_result(
                {"tool_name": "search", "result": ["hit"], "error": None, "duration_ms": 12.5}
            )

        buffer = get_event_buffer()
        events = buffer.get_events("test-instrumentor-tool")

        assert any(event.event_type == EventType.TOOL_CALL for event in events)
        assert any(event.event_type == EventType.TOOL_RESULT for event in events)

    @pytest.mark.asyncio
    async def test_instrumentor_hooks_are_noops_without_context(self):
        """Test instrumentor hooks safely return when no context is set."""
        from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor

        instrumentor = PydanticAIInstrumentor(session_id="no-context-instrumentor")

        await instrumentor.on_model_request({})
        await instrumentor.on_model_response({})
        await instrumentor.on_tool_call({})
        await instrumentor.on_tool_result({})
