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
from datetime import datetime
from typing import Any, Generic, TypeVar

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

try:
    from pydantic_ai import Agent, AgentRunResult
    from pydantic_ai.messages import (
        ModelMessage,
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )
    from pydantic_ai.models import Model

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False
    Agent = Any
    AgentRunResult = Any
    ModelRequest = Any
    ModelResponse = Any
    Model = Any
    RetryPromptPart = Any
    SystemPromptPart = Any
    TextPart = Any
    ToolCallPart = Any
    ToolReturnPart = Any
    UserPromptPart = Any

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
        ) -> AgentRunResult:
            async with adapter.trace_session(
                agent_name=adapter.agent_name,
                tags=adapter.tags,
            ):
                start = time.perf_counter()
                result = await adapter._original_run(
                    user_prompt,
                    message_history=message_history,
                    model=model,
                    **kwargs,
                )
                duration_ms = (time.perf_counter() - start) * 1000

                await adapter._capture_result(result, requested_model=model, duration_ms=duration_ms)

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

    async def _capture_result(
        self,
        result: AgentRunResult,
        *,
        requested_model: Model | str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Capture the result of an agent run.

        Args:
            result: The RunResult from the agent execution.
        """
        if not self._context:
            return

        if hasattr(result, "all_messages"):
            await self._process_messages(
                result.all_messages(),
                requested_model=requested_model,
                duration_ms=duration_ms,
            )

    async def _process_messages(
        self,
        messages: list[ModelMessage],
        *,
        requested_model: Model | str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Process and emit events for a list of messages.

        Args:
            messages: List of ModelMessage objects from the run.
        """
        if not self._context:
            return

        resolved_model = self._resolve_model_name(requested_model)
        tool_call_parent_ids: dict[str, str] = {}
        prior_request_timestamp: datetime | None = None

        for index, msg in enumerate(messages):
            if isinstance(msg, ModelRequest):
                prior_request_timestamp = msg.timestamp
            response_parent_id = await self._emit_message_event(
                msg,
                model_name=resolved_model,
                response_duration_ms=(duration_ms if index == len(messages) - 1 else 0.0),
                request_timestamp=prior_request_timestamp,
                tool_call_parent_ids=tool_call_parent_ids,
            )
            if isinstance(msg, ModelResponse) and response_parent_id:
                prior_request_timestamp = None

    async def _emit_message_event(
        self,
        message: ModelMessage,
        *,
        model_name: str,
        response_duration_ms: float = 0.0,
        request_timestamp: datetime | None = None,
        tool_call_parent_ids: dict[str, str] | None = None,
    ) -> str | None:
        """Emit appropriate events for a message.

        Args:
            message: A ModelMessage from the conversation.
        """
        if not self._context:
            return None

        if isinstance(message, ModelRequest):
            request_event = LLMRequestEvent(
                session_id=self.session_id,
                parent_id=self._context.get_current_parent(),
                model=model_name,
                messages=self._request_messages_from_parts(message.parts),
                tools=[],
                settings={},
                name=f"llm_request_{model_name}",
                importance=0.3,
            )
            await self._context._emit_event(request_event)

            if tool_call_parent_ids is not None:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        await self._context.record_tool_result(
                            tool_name=part.tool_name,
                            result=part.content,
                            error=part.model_response_str() if part.outcome != "success" else None,
                            parent_id=tool_call_parent_ids.get(part.tool_call_id),
                        )
            return request_event.id

        if not isinstance(message, ModelResponse):
            return None

        tool_calls = [
            {
                "id": part.tool_call_id,
                "name": part.tool_name,
                "arguments": part.args_as_dict(),
            }
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        response_model = message.model_name or model_name
        response_event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=response_model,
            content="".join(part.content for part in message.parts if isinstance(part, TextPart)),
            tool_calls=tool_calls,
            usage=self._usage_from_message(message),
            duration_ms=self._response_duration_ms(
                request_timestamp=request_timestamp,
                response_timestamp=message.timestamp,
                fallback_ms=response_duration_ms,
            ),
            name=f"llm_response_{response_model}",
            importance=0.5,
        )
        await self._context._emit_event(response_event)

        if tool_call_parent_ids is not None:
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    tool_call_event = ToolCallEvent(
                        session_id=self.session_id,
                        parent_id=response_event.id,
                        tool_name=part.tool_name,
                        arguments=part.args_as_dict(),
                        name=f"tool_call_{part.tool_name}",
                        importance=0.4,
                    )
                    await self._context._emit_event(tool_call_event)
                    tool_call_parent_ids[part.tool_call_id] = tool_call_event.id

        return response_event.id

    def _resolve_model_name(self, requested_model: Model | str | None) -> str:
        """Resolve the active model name from explicit or agent-level configuration."""
        if isinstance(requested_model, str):
            return requested_model
        if requested_model is not None:
            name = getattr(requested_model, "model_name", None) or getattr(requested_model, "name", None)
            if name:
                return str(name)

        for attr in ("model", "_model", "model_name", "name"):
            value = getattr(self.agent, attr, None)
            if isinstance(value, str) and value:
                return value
            name = getattr(value, "model_name", None) or getattr(value, "name", None)
            if name:
                return str(name)

        return "unknown"

    def _request_messages_from_parts(self, parts: list[Any] | Any) -> list[dict[str, Any]]:
        """Convert PydanticAI request parts into our LLM-request message shape."""
        messages: list[dict[str, Any]] = []

        for part in parts:
            if isinstance(part, UserPromptPart):
                messages.append({"role": "user", "content": self._stringify_content(part.content)})
            elif isinstance(part, SystemPromptPart):
                messages.append({"role": "system", "content": self._stringify_content(part.content)})
            elif isinstance(part, ToolReturnPart):
                messages.append(
                    {
                        "role": "tool",
                        "name": part.tool_name,
                        "content": part.model_response_str(),
                    }
                )
            elif isinstance(part, RetryPromptPart):
                role = "tool" if part.tool_name else "user"
                item = {"role": role, "content": part.model_response()}
                if part.tool_name:
                    item["name"] = part.tool_name
                messages.append(item)

        return messages

    def _stringify_content(self, content: Any) -> str:
        """Render simple request content into a stable string for event payloads."""
        if isinstance(content, str):
            return content
        return str(content)

    def _usage_from_message(self, message: ModelResponse) -> dict[str, int]:
        """Extract token usage from a model response message."""
        usage = getattr(message, "usage", None)
        if usage is None:
            return {"input_tokens": 0, "output_tokens": 0}
        return {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        }

    def _response_duration_ms(
        self,
        *,
        request_timestamp: datetime | None,
        response_timestamp: datetime | None,
        fallback_ms: float,
    ) -> float:
        """Best-effort duration based on message timestamps, with run-time fallback."""
        if request_timestamp and response_timestamp:
            duration_ms = (response_timestamp - request_timestamp).total_seconds() * 1000
            if duration_ms > 0:
                return duration_ms
        return fallback_ms if fallback_ms > 0 else 1.0

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
