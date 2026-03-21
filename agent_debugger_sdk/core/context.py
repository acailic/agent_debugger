"""Thread-local state management for tracing agent execution.

This module provides the TraceContext class for managing async-safe state
during agent execution tracing. It uses contextvars for proper async support
and provides methods for recording decisions, tool results, errors, and
checkpoints.
"""

from __future__ import annotations

import asyncio
import uuid
from contextvars import ContextVar
from datetime import UTC
from datetime import datetime
from typing import Any

from .events import Checkpoint
from .events import DecisionEvent
from .events import ErrorEvent
from .events import EventType
from .events import Session
from .events import ToolResultEvent
from .events import TraceEvent

_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_parent_id: ContextVar[str | None] = ContextVar("current_parent_id", default=None)
_event_sequence: ContextVar[int] = ContextVar("event_sequence", default=0)
_current_context: ContextVar[TraceContext | None] = ContextVar("current_context", default=None)


class TraceContext:
    """Async-safe context manager for tracing agent execution.

    Manages thread-local (actually async-context-local) state for tracking
    the current trace session, parent event IDs for hierarchical events,
    and event sequencing.

    Usage:
        async with TraceContext(session_id="my-session") as ctx:
            ctx.record_decision(
                reasoning="User asked about weather",
                confidence=0.9,
                evidence=[{"source": "user_input", "content": "What's the weather?"}],
                chosen_action="call_weather_tool"
            )

            result = await some_tool()
            ctx.record_tool_result("some_tool", result)

    Attributes:
        session_id: Unique identifier for this tracing session
        collector_endpoint: Optional endpoint for trace collection
        session: Session metadata object
        _event_queue: Async queue for buffering events
    """

    def __init__(
        self,
        session_id: str | None = None,
        collector_endpoint: str | None = None,
        agent_name: str = "",
        framework: str = "",
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Initialize the trace context.

        Args:
            session_id: Unique identifier for this session. If not provided,
                a UUID will be generated.
            collector_endpoint: Optional HTTP endpoint for the trace collector.
                If not provided, events are only queued locally.
            agent_name: Name of the agent being traced.
            framework: Framework being used (pydantic_ai, langchain, autogen).
            config: Agent configuration settings.
            tags: Tags for categorizing this session.
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.collector_endpoint = collector_endpoint
        self._event_queue: asyncio.Queue[TraceEvent | Checkpoint] = asyncio.Queue()
        self._checkpoint_sequence = 0

        self.session = Session(
            id=self.session_id,
            agent_name=agent_name,
            framework=framework,
            config=config or {},
            tags=tags or [],
        )

        self._session_start_event: TraceEvent | None = None
        self._entered = False

    async def __aenter__(self) -> TraceContext:
        """Enter the tracing context.

        Sets up context variables and emits a session start event.

        Returns:
            The TraceContext instance for use within the context.
        """
        _current_session_id.set(self.session_id)
        _current_parent_id.set(None)
        _event_sequence.set(0)
        _current_context.set(self)

        self._entered = True

        start_event = TraceEvent(
            session_id=self.session_id,
            parent_id=None,
            event_type=EventType.AGENT_START,
            name="session_start",
            data={"agent_name": self.session.agent_name, "framework": self.session.framework},
            metadata={"config": self.session.config, "tags": self.session.tags},
            importance=0.2,
        )
        self._session_start_event = start_event
        await self._emit_event(start_event)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the tracing context.

        Emits a session end event and cleans up context variables.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        status = "completed"
        if exc_type is not None:
            status = "error"
            await self.record_error(
                error_type=exc_type.__name__,
                error_message=str(exc_val),
            )

        end_event = TraceEvent(
            session_id=self.session_id,
            parent_id=self._session_start_event.id if self._session_start_event else None,
            event_type=EventType.AGENT_END,
            name="session_end",
            data={
                "status": status,
                "total_tokens": self.session.total_tokens,
                "total_cost_usd": self.session.total_cost_usd,
                "tool_calls": self.session.tool_calls,
                "llm_calls": self.session.llm_calls,
                "errors": self.session.errors,
            },
            importance=0.2,
        )
        self.session.status = status
        self.session.ended_at = datetime.now(UTC)

        await self._emit_event(end_event)

        _current_session_id.set(None)
        _current_parent_id.set(None)
        _event_sequence.set(0)
        _current_context.set(None)
        self._entered = False

    async def record_decision(
        self,
        reasoning: str,
        confidence: float,
        evidence: list[dict[str, Any]],
        chosen_action: str,
        alternatives: list[dict[str, Any]] | None = None,
        name: str = "decision",
    ) -> str:
        """Record a decision point in the agent execution.

        Captures the reasoning process when an agent makes a decision,
        including confidence level, supporting evidence, alternatives
        considered, and the chosen action.

        Args:
            reasoning: The agent's reasoning for this decision.
            confidence: Confidence level (0.0-1.0).
            evidence: List of evidence items supporting the decision.
                Each item should have 'source' and 'content' keys.
            chosen_action: The action that was selected.
            alternatives: Optional list of alternative actions considered.
                Each item should have 'action' and 'reason_rejected' keys.
            name: Human-readable name for this decision point.

        Returns:
            The event ID of the recorded decision.

        Example:
            event_id = await ctx.record_decision(
                reasoning="User query about weather requires weather API",
                confidence=0.85,
                evidence=[{"source": "user_input", "content": "What's the weather?"}],
                chosen_action="call_weather_tool",
                alternatives=[
                    {"action": "search_web", "reason_rejected": "Less accurate for weather"}
                ]
            )
        """
        self._check_entered()

        confidence = max(0.0, min(1.0, confidence))

        event = DecisionEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            event_type=EventType.DECISION,
            name=name,
            reasoning=reasoning,
            confidence=confidence,
            evidence=evidence,
            alternatives=alternatives or [],
            chosen_action=chosen_action,
            importance=0.7,
        )

        await self._emit_event(event)
        return event.id

    async def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: float = 0,
        name: str | None = None,
    ) -> str:
        """Record the result of a tool call.

        Captures the outcome of a tool execution, including success/failure
        status, duration, and any returned data or error.

        Args:
            tool_name: Name of the tool that was called.
            result: The return value from the tool.
            error: Error message if the tool call failed.
            duration_ms: Execution time in milliseconds.
            name: Optional human-readable name for this event.

        Returns:
            The event ID of the recorded tool result.

        Example:
            result = await search_web("weather today")
            await ctx.record_tool_result(
                tool_name="search_web",
                result=result,
                duration_ms=150.5
            )
        """
        self._check_entered()

        importance = 0.5
        if error:
            importance = 0.9
            self.session.errors += 1

        event = ToolResultEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            event_type=EventType.TOOL_RESULT,
            name=name or f"{tool_name}_result",
            tool_name=tool_name,
            result=result,
            error=error,
            duration_ms=duration_ms,
            importance=importance,
        )

        self.session.tool_calls += 1
        await self._emit_event(event)
        return event.id

    async def record_error(
        self,
        error_type: str,
        error_message: str,
        stack_trace: str | None = None,
        name: str | None = None,
    ) -> str:
        """Record an error that occurred during agent execution.

        Captures error details including type, message, and optional
        stack trace for debugging purposes.

        Args:
            error_type: The exception class name or error category.
            error_message: Human-readable error message.
            stack_trace: Optional stack trace for debugging.
            name: Optional human-readable name for this event.

        Returns:
            The event ID of the recorded error.

        Example:
            try:
                result = await risky_operation()
            except Exception as e:
                await ctx.record_error(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    stack_trace=traceback.format_exc()
                )
                raise
        """
        self._check_entered()

        event = ErrorEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            event_type=EventType.ERROR,
            name=name or f"error_{error_type}",
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            importance=0.9,
        )

        self.session.errors += 1
        await self._emit_event(event)
        return event.id

    async def create_checkpoint(
        self,
        state: dict[str, Any],
        memory: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> str:
        """Create a checkpoint for time-travel debugging.

        Checkpoints capture the complete state of an agent at a specific
        point in execution, enabling state restoration and analysis.

        Args:
            state: The agent's state at this point.
            memory: Optional memory/context snapshot at this point.
            importance: Relative importance score (0.0-1.0) for selective replay.

        Returns:
            The checkpoint ID.

        Example:
            checkpoint_id = await ctx.create_checkpoint(
                state={"current_step": 3, "data": processed_data},
                memory={"conversation_history": messages},
                importance=0.8
            )
        """
        self._check_entered()

        self._checkpoint_sequence += 1
        checkpoint_id = str(uuid.uuid4())

        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=self.session_id,
            event_id=_current_parent_id.get() or "",
            sequence=self._checkpoint_sequence,
            state=state,
            memory=memory or {},
            timestamp=datetime.now(UTC),
            importance=max(0.0, min(1.0, importance)),
        )

        await self._event_queue.put(checkpoint)

        event = TraceEvent(
            id=str(uuid.uuid4()),
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            event_type=EventType.CHECKPOINT,
            name=f"checkpoint_{self._checkpoint_sequence}",
            data={
                "checkpoint_id": checkpoint_id,
                "sequence": self._checkpoint_sequence,
            },
            importance=checkpoint.importance,
        )
        await self._emit_event(event)

        return checkpoint_id

    def set_parent(self, event_id: str) -> None:
        """Set the parent event ID for hierarchical event tracking.

        All subsequent events will have this event as their parent,
        creating a hierarchical trace structure.

        Args:
            event_id: The event ID to set as the current parent.

        Example:
            decision_id = await ctx.record_decision(...)
            ctx.set_parent(decision_id)
            await ctx.record_tool_result("tool", result)
            ctx.clear_parent()
        """
        self._check_entered()
        _current_parent_id.set(event_id)

    def get_current_parent(self) -> str | None:
        """Get the current parent event ID.

        Returns:
            The current parent event ID, or None if no parent is set.
        """
        return _current_parent_id.get()

    def clear_parent(self) -> None:
        """Clear the current parent event ID.

        Subsequent events will have no parent (parent_id = None).
        """
        self._check_entered()
        _current_parent_id.set(None)

    def get_event_sequence(self) -> int:
        """Get the current event sequence number.

        Returns:
            The current sequence number (number of events emitted).
        """
        return _event_sequence.get()

    async def get_events(self) -> list[TraceEvent | Checkpoint]:
        """Get all queued events from this context.

        Non-destructively retrieves all events currently in the queue.
        Events remain in the queue after this call.

        Returns:
            List of all queued events and checkpoints.
        """
        events: list[TraceEvent | Checkpoint] = []
        temp_list: list[TraceEvent | Checkpoint] = []

        while True:
            try:
                event = self._event_queue.get_nowait()
                events.append(event)
                temp_list.append(event)
            except asyncio.QueueEmpty:
                break

        for event in temp_list:
            await self._event_queue.put(event)

        return events

    async def drain_events(self) -> list[TraceEvent | Checkpoint]:
        """Drain and return all queued events.

        Destructively retrieves all events, clearing the queue.

        Returns:
            List of all queued events and checkpoints.
        """
        events: list[TraceEvent | Checkpoint] = []

        while True:
            try:
                event = self._event_queue.get_nowait()
                events.append(event)
            except asyncio.QueueEmpty:
                break

        return events

    def _check_entered(self) -> None:
        """Check that the context has been entered.

        Raises:
            RuntimeError: If the context has not been entered.
        """
        if not self._entered:
            raise RuntimeError(
                "TraceContext has not been entered. Use 'async with TraceContext(...) as ctx:' to enter the context."
            )

    async def _emit_event(self, event: TraceEvent) -> None:
        """Emit an event to the queue.

        Increments the event sequence and queues the event for collection.

        Args:
            event: The event to emit.
        """
        current_seq = _event_sequence.get()
        _event_sequence.set(current_seq + 1)

        event.metadata["sequence"] = current_seq + 1

        await self._event_queue.put(event)

        if event.event_type == EventType.LLM_RESPONSE:
            usage = event.data.get("usage", {})
            self.session.total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            self.session.total_cost_usd += event.data.get("cost_usd", 0.0)
            self.session.llm_calls += 1


def get_current_context() -> TraceContext | None:
    """Get the currently active TraceContext.

    Returns:
        The active TraceContext if within a context manager, None otherwise.
    """
    return _current_context.get()


def get_current_session_id() -> str | None:
    """Get the current session ID.

    Returns:
        The current session ID if within a context, None otherwise.
    """
    return _current_session_id.get()


def get_current_parent_id() -> str | None:
    """Get the current parent event ID.

    Returns:
        The current parent event ID if set, None otherwise.
    """
    return _current_parent_id.get()
