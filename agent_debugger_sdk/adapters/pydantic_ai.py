"""PydanticAI adapter for agent execution tracing.

This module provides the PydanticAIAdapter class that wraps PydanticAI agents
and captures execution traces for debugging and visualization.

PydanticAI has built-in OpenTelemetry instrumentation. This adapter hooks into
that system to capture events and forward them to our trace collector.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any
from typing import Generic
from typing import TypeVar

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import LLMRequestEvent
from agent_debugger_sdk.core.events import LLMResponseEvent
from agent_debugger_sdk.core.events import ToolCallEvent

try:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models import InstrumentationSettings
    from pydantic_ai.models import Model
    from pydantic_ai.result import RunResult

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False
    Agent = Any
    Model = Any
    RunResult = Any
    InstrumentationSettings = Any

T = TypeVar("T")
R = TypeVar("R")

_pydantic_run_context: ContextVar[dict[str, Any] | None] = ContextVar("pydantic_run_context", default=None)


class PydanticAIAdapter(Generic[T]):
    """Adapter to trace PydanticAI agents.

    Wraps a PydanticAI Agent and captures execution traces including:
    - LLM requests and responses
    - Tool calls and results
    - Decision points
    - Errors

    Example:
        >>> from pydantic_ai import Agent
        >>> from agent_debugger_sdk.adapters import PydanticAIAdapter
        >>>
        >>> agent = Agent('openai:gpt-4o')
        >>> adapter = PydanticAIAdapter(agent)
        >>>
        >>> # Use as context manager
        >>> async with adapter.trace_session(agent_name="my_agent") as session_id:
        ...     result = await agent.run("Hello")
        ...     print(f"Session: {session_id}")
        >>>
        >>> # Or instrument and use directly
        >>> instrumented = adapter.instrument()
        >>> result = await instrumented.run("Hello")
    """

    def __init__(
        self,
        agent: Agent,
        session_id: str | None = None,
        agent_name: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            agent: The PydanticAI Agent instance to trace.
            session_id: Optional session ID. If not provided, one will be generated.
            agent_name: Human-readable name for the agent.
            tags: Optional tags for categorizing this session.
        """
        if not PYDANTIC_AI_AVAILABLE:
            raise ImportError("PydanticAI is not installed. Install it with: pip install pydantic-ai")

        self.agent = agent
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_name = agent_name or agent.__class__.__name__
        self.tags = tags or []
        self._context: TraceContext | None = None
        self._instrumented = False
        self._original_run: Any = None

    def instrument(self) -> Agent:
        """Return the agent with tracing instrumentation.

        This wraps the agent's run method to capture traces.

        Returns:
            The same agent instance with tracing enabled.
        """
        if self._instrumented:
            return self.agent

        self._original_run = self.agent.run
        self._instrumented = True

        adapter = self

        async def traced_run(
            user_prompt: str | None = None,
            *,
            message_history: list[ModelMessage] | None = None,
            model: Model | str | None = None,
            **kwargs: Any,
        ) -> RunResult:
            async with adapter.trace_session(
                agent_name=adapter.agent_name,
                tags=adapter.tags,
            ):
                result = await adapter._original_run(
                    user_prompt,
                    message_history=message_history,
                    model=model,
                    **kwargs,
                )

                await adapter._capture_result(result)

            return result

        self.agent.run = traced_run
        return self.agent

    @asynccontextmanager
    async def trace_session(
        self,
        agent_name: str = "",
        tags: list[str] | None = None,
    ):
        """Context manager for tracing a complete agent run.

        Args:
            agent_name: Name of the agent for this session.
            tags: Optional tags for categorizing this session.

        Yields:
            The session ID string.
        """
        self._context = TraceContext(
            session_id=self.session_id,
            agent_name=agent_name or self.agent_name,
            framework="pydantic_ai",
            tags=tags or self.tags,
        )

        async with self._context as ctx:
            _pydantic_run_context.set(
                {
                    "session_id": self.session_id,
                    "context": ctx,
                }
            )

            try:
                yield self.session_id
            finally:
                _pydantic_run_context.set(None)

    async def _capture_result(self, result: RunResult) -> None:
        """Capture the result of an agent run.

        Args:
            result: The RunResult from the agent execution.
        """
        if not self._context:
            return

        if hasattr(result, "all_messages"):
            await self._process_messages(result.all_messages())

    async def _process_messages(self, messages: list[ModelMessage]) -> None:
        """Process and emit events for a list of messages.

        Args:
            messages: List of ModelMessage objects from the run.
        """
        if not self._context:
            return

        for msg in messages:
            await self._emit_message_event(msg)

    async def _emit_message_event(self, message: ModelMessage) -> None:
        """Emit appropriate events for a message.

        Args:
            message: A ModelMessage from the conversation.
        """
        if not self._context:
            return

        if hasattr(message, "parts"):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    event = ToolCallEvent(
                        session_id=self.session_id,
                        parent_id=self._context.get_current_parent(),
                        tool_name=part.tool_name,
                        arguments=part.args if isinstance(part.args, dict) else {"args": part.args},
                        name=f"tool_call_{part.tool_name}",
                        importance=0.4,
                    )
                    await self._context._emit_event(event)

    async def record_llm_request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> str:
        """Record an LLM request event.

        Args:
            model: The model identifier.
            messages: The messages being sent to the LLM.
            tools: Available tools for the LLM.
            settings: Model settings (temperature, etc.).

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=model,
            messages=messages,
            tools=tools or [],
            settings=settings or {},
            name=f"llm_request_{model}",
            importance=0.3,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_llm_response(
        self,
        model: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float = 0.0,
        duration_ms: float = 0.0,
    ) -> str:
        """Record an LLM response event.

        Args:
            model: The model that generated the response.
            content: The text content of the response.
            tool_calls: Tool calls requested by the LLM.
            usage: Token usage statistics.
            cost_usd: Estimated cost in USD.
            duration_ms: Duration of the API call.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=model,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage or {"input_tokens": 0, "output_tokens": 0},
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            name=f"llm_response_{model}",
            importance=0.5,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Record a tool call event.

        Args:
            tool_name: Name of the tool being called.
            arguments: Arguments passed to the tool.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            tool_name=tool_name,
            arguments=arguments,
            name=f"tool_call_{tool_name}",
            importance=0.4,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> str:
        """Record a tool result event.

        Args:
            tool_name: Name of the tool that was called.
            result: The return value from the tool.
            error: Error message if the call failed.
            duration_ms: Execution time in milliseconds.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        return await self._context.record_tool_result(
            tool_name=tool_name,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )


class PydanticAIInstrumentor:
    """Low-level instrumentor for PydanticAI using OpenTelemetry hooks.

    This provides finer-grained instrumentation by hooking into PydanticAI's
    internal event system. Use this if you need more control over event capture.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize the instrumentor.

        Args:
            session_id: The session ID to associate events with.
        """
        self.session_id = session_id
        self._start_times: dict[str, float] = {}
        self._context: TraceContext | None = None

    def set_context(self, context: TraceContext) -> None:
        """Set the trace context.

        Args:
            context: The TraceContext to use for event emission.
        """
        self._context = context

    async def on_model_request(self, data: dict[str, Any]) -> None:
        """Handle model request event.

        Args:
            data: Event data containing model, messages, etc.
        """
        if not self._context:
            return

        request_id = data.get("request_id", str(uuid.uuid4()))
        self._start_times[request_id] = time.time()

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=data.get("model", "unknown"),
            messages=data.get("messages", []),
            tools=data.get("tools", []),
            settings=data.get("settings", {}),
            name=f"llm_request_{data.get('model', 'unknown')}",
            importance=0.3,
        )

        await self._context._emit_event(event)

    async def on_model_response(self, data: dict[str, Any]) -> None:
        """Handle model response event.

        Args:
            data: Event data containing response, usage, etc.
        """
        if not self._context:
            return

        request_id = data.get("request_id", "")
        start_time = self._start_times.pop(request_id, time.time())
        duration_ms = (time.time() - start_time) * 1000

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=data.get("model", "unknown"),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls", []),
            usage=data.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            cost_usd=data.get("cost_usd", 0.0),
            duration_ms=duration_ms,
            name=f"llm_response_{data.get('model', 'unknown')}",
            importance=0.5,
        )

        await self._context._emit_event(event)

    async def on_tool_call(self, data: dict[str, Any]) -> None:
        """Handle tool call event.

        Args:
            data: Event data containing tool name and arguments.
        """
        if not self._context:
            return

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            tool_name=data.get("tool_name", "unknown"),
            arguments=data.get("arguments", {}),
            name=f"tool_call_{data.get('tool_name', 'unknown')}",
            importance=0.4,
        )

        await self._context._emit_event(event)

    async def on_tool_result(self, data: dict[str, Any]) -> None:
        """Handle tool result event.

        Args:
            data: Event data containing tool name and result.
        """
        if not self._context:
            return

        await self._context.record_tool_result(
            tool_name=data.get("tool_name", "unknown"),
            result=data.get("result"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
        )
