"""Core PydanticAI adapter implementation.

This module provides the PydanticAIAdapter class that wraps PydanticAI agents
and captures execution traces for debugging and visualization.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from agent_debugger_sdk.core.context import TraceContext

from .event_recording import EventRecorder
from .message_processing import MessageProcessor

try:
    from pydantic_ai import Agent, AgentRunResult
    from pydantic_ai.models import Model

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False
    Agent = Any
    AgentRunResult = Any
    Model = Any

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
        self._message_processor: MessageProcessor | None = None
        self._event_recorder: EventRecorder | None = None

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
            message_history: list[Any] | None = None,
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

        # Initialize processors with the context
        self._message_processor = MessageProcessor(self.session_id, self._context)
        self._event_recorder = EventRecorder(self.session_id, self._context)

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
            requested_model: The model that was requested.
            duration_ms: Duration of the run in milliseconds.
        """
        if not self._context or not self._message_processor:
            return

        if hasattr(result, "all_messages"):
            # Update message processor with agent for model name resolution
            self._message_processor._agent = self.agent
            await self._message_processor.process_messages(
                result.all_messages(),
                requested_model=requested_model,
                duration_ms=duration_ms,
            )

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
        if not self._event_recorder:
            return ""

        return await self._event_recorder.record_llm_request(model, messages, tools, settings)

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
        if not self._event_recorder:
            return ""

        return await self._event_recorder.record_llm_response(
            model,
            content,
            tool_calls,
            usage,
            cost_usd,
            duration_ms,
        )

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
        if not self._event_recorder:
            return ""

        return await self._event_recorder.record_tool_call(tool_name, arguments)

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
        if not self._event_recorder:
            return ""

        return await self._event_recorder.record_tool_result(tool_name, result, error, duration_ms)

    async def _process_messages(
        self,
        messages: list[Any],
        *,
        requested_model: Any = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Process messages (backward compatibility wrapper).

        Args:
            messages: List of messages to process.
            requested_model: The model that was requested.
            duration_ms: Duration of processing.
        """
        if not self._message_processor:
            return

        await self._message_processor.process_messages(
            messages,
            requested_model=requested_model,
            duration_ms=duration_ms,
        )
