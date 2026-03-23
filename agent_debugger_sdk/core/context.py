"""Thread-local state management for tracing agent execution.

This module provides the TraceContext class for managing async-safe state
during agent execution tracing. It uses contextvars for proper async support
and provides methods for recording decisions, tool results, errors, and
checkpoints.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Protocol

from .events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
    Session,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from .scorer import get_importance_scorer


class EventBufferLike(Protocol):
    """Protocol for publish-capable event buffers."""

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish an event for live consumers."""
        ...

_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_parent_id: ContextVar[str | None] = ContextVar("current_parent_id", default=None)
_event_sequence: ContextVar[int] = ContextVar("event_sequence", default=0)
_current_context: ContextVar[TraceContext | None] = ContextVar("current_context", default=None)
_default_event_buffer: ContextVar[EventBufferLike | None] = ContextVar("default_event_buffer", default=None)
_default_event_persister: ContextVar[Callable[[TraceEvent], Awaitable[None]] | None] = ContextVar(
    "default_event_persister",
    default=None,
)
_default_checkpoint_persister: ContextVar[Callable[[Checkpoint], Awaitable[None]] | None] = ContextVar(
    "default_checkpoint_persister",
    default=None,
)
_default_session_start_hook: ContextVar[Callable[[Session], Awaitable[None]] | None] = ContextVar(
    "default_session_start_hook",
    default=None,
)
_default_session_update_hook: ContextVar[Callable[[Session], Awaitable[None]] | None] = ContextVar(
    "default_session_update_hook",
    default=None,
)


def _get_default_event_buffer() -> EventBufferLike | None:
    """Resolve the shared event buffer lazily.

    Importing collector modules at SDK import time creates a package-level cycle.
    Resolve the singleton only when a context is instantiated and only when no
    explicit/default buffer has already been configured.
    """
    configured = _default_event_buffer.get()
    if configured is not None:
        return configured

    try:
        from collector.buffer import get_event_buffer
    except ImportError:
        return None
    return get_event_buffer()


def configure_event_pipeline(
    buffer: EventBufferLike | None,
    *,
    persist_event: Callable[[TraceEvent], Awaitable[None]] | None = None,
    persist_checkpoint: Callable[[Checkpoint], Awaitable[None]] | None = None,
    persist_session_start: Callable[[Session], Awaitable[None]] | None = None,
    persist_session_update: Callable[[Session], Awaitable[None]] | None = None,
) -> None:
    """Configure the default event buffer for the event pipeline.

    This connects the SDK's TraceContext to the collector's EventBuffer,
    enabling real-time event streaming and persistence.

    Args:
        buffer: The EventBuffer to use for publishing events, or None to disconnect.
        persist_event: Optional async callback used to persist each emitted event.
        persist_checkpoint: Optional async callback used to persist each checkpoint.
        persist_session_start: Optional async callback used to create a session.
        persist_session_update: Optional async callback used to update a session.
    """
    _default_event_buffer.set(buffer)
    _default_event_persister.set(persist_event)
    _default_checkpoint_persister.set(persist_checkpoint)
    _default_session_start_hook.set(persist_session_start)
    _default_session_update_hook.set(persist_session_update)


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
        _events: List for buffering events
        _events_lock: Async lock for thread-safe event access
    """

    def __init__(
        self,
        session_id: str | None = None,
        collector_endpoint: str | None = None,
        agent_name: str = "",
        framework: str = "",
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        event_buffer: EventBufferLike | None = None,
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
            event_buffer: Optional event buffer for real-time event publishing.
                If not provided, uses the default configured via configure_event_pipeline().
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.collector_endpoint = collector_endpoint
        self._events: list[TraceEvent | Checkpoint] = []
        self._events_lock: asyncio.Lock = asyncio.Lock()
        self._checkpoint_sequence = 0
        self._event_buffer = event_buffer if event_buffer is not None else _get_default_event_buffer()
        self._event_persister = _default_event_persister.get()
        self._checkpoint_persister = _default_checkpoint_persister.get()
        self._session_start_hook = _default_session_start_hook.get()
        self._session_update_hook = _default_session_update_hook.get()

        self.session = Session(
            id=self.session_id,
            agent_name=agent_name,
            framework=framework,
            config=config or {},
            tags=tags or [],
        )

        self._session_start_event: TraceEvent | None = None
        self._entered = False
        self._transport: Any | None = None  # HttpTransport instance if in cloud mode

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

        # Wire in HTTP transport for cloud mode
        # IMPORTANT: Do NOT call configure_event_pipeline() here as it mutates
        # global ContextVars and would break concurrent sessions. Instead, set
        # instance-level hooks.
        from agent_debugger_sdk.config import get_config
        config = get_config()
        if config.mode == "cloud" and config.api_key:
            from agent_debugger_sdk.transport import HttpTransport
            self._transport = HttpTransport(config.endpoint, config.api_key)
            # Set instance-level hooks (not global pipeline)
            self._event_persister = self._transport.send_event
            self._session_start_hook = self._transport.send_session_start
            self._session_update_hook = self._transport.send_session_update
        else:
            self._transport = None

        self._entered = True
        if self._session_start_hook is not None:
            await self._session_start_hook(self.session)

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
            # Get stack trace from traceback object
            import traceback as tb_module

            if exc_tb is not None:
                tb_str = "".join(tb_module.format_exception(exc_type, exc_val, exc_tb))
            else:
                tb_str = "".join(tb_module.format_exception_only(exc_type, exc_val)) if exc_type else None

            await self.record_error(
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                stack_trace=tb_str,
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
        if self._session_update_hook is not None:
            await self._session_update_hook(self.session)

        _current_session_id.set(None)
        _current_parent_id.set(None)
        _event_sequence.set(0)
        _current_context.set(None)
        self._entered = False

        # Close transport if it was created
        if self._transport is not None:
            await self._transport.close()
            self._transport = None

    async def record_decision(
        self,
        reasoning: str,
        confidence: float,
        evidence: list[dict[str, Any]],
        chosen_action: str,
        evidence_event_ids: list[str] | None = None,
        upstream_event_ids: list[str] | None = None,
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
            evidence_event_ids=evidence_event_ids or [],
            alternatives=alternatives or [],
            chosen_action=chosen_action,
            importance=0.7,
            upstream_event_ids=upstream_event_ids or [],
        )

        await self._emit_event(event)
        return event.id

    async def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        """Record that the agent invoked a tool."""
        self._check_entered()

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else _current_parent_id.get(),
            event_type=EventType.TOOL_CALL,
            name=name or f"{tool_name}_call",
            tool_name=tool_name,
            arguments=arguments,
            importance=0.4,
            upstream_event_ids=upstream_event_ids or [],
        )

        await self._emit_event(event)
        return event.id

    async def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: float = 0,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
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
            parent_id=parent_id if parent_id is not None else _current_parent_id.get(),
            event_type=EventType.TOOL_RESULT,
            name=name or f"{tool_name}_result",
            tool_name=tool_name,
            result=result,
            error=error,
            duration_ms=duration_ms,
            importance=importance,
            upstream_event_ids=upstream_event_ids or [],
        )

        self.session.tool_calls += 1
        await self._emit_event(event)
        return event.id

    async def record_llm_request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        """Record an outbound LLM request."""
        self._check_entered()

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else _current_parent_id.get(),
            event_type=EventType.LLM_REQUEST,
            name=name or f"llm_request_{model}",
            model=model,
            messages=messages,
            tools=tools or [],
            settings=settings or {},
            importance=0.35,
            upstream_event_ids=upstream_event_ids or [],
        )

        await self._emit_event(event)
        return event.id

    async def record_llm_response(
        self,
        model: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float = 0.0,
        duration_ms: float = 0.0,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        """Record an inbound LLM response."""
        self._check_entered()

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else _current_parent_id.get(),
            event_type=EventType.LLM_RESPONSE,
            name=name or f"llm_response_{model}",
            model=model,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage or {"input_tokens": 0, "output_tokens": 0},
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            importance=0.5,
            upstream_event_ids=upstream_event_ids or [],
        )

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

    async def record_safety_check(
        self,
        policy_name: str,
        outcome: str,
        risk_level: str,
        rationale: str,
        *,
        blocked_action: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record an explicit safety check event."""
        self._check_entered()
        event = SafetyCheckEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"safety_check_{policy_name}",
            policy_name=policy_name,
            outcome=outcome,
            risk_level=risk_level,
            rationale=rationale,
            blocked_action=blocked_action,
            evidence=evidence or [],
            upstream_event_ids=upstream_event_ids or [],
            importance=0.8 if outcome != "pass" else 0.55,
        )
        await self._emit_event(event)
        return event.id

    async def record_refusal(
        self,
        reason: str,
        policy_name: str,
        *,
        risk_level: str = "medium",
        blocked_action: str | None = None,
        safe_alternative: str | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record an intentional refusal event."""
        self._check_entered()
        event = RefusalEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"refusal_{policy_name}",
            reason=reason,
            policy_name=policy_name,
            risk_level=risk_level,
            blocked_action=blocked_action,
            safe_alternative=safe_alternative,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.85,
        )
        await self._emit_event(event)
        return event.id

    async def record_policy_violation(
        self,
        policy_name: str,
        violation_type: str,
        *,
        severity: str = "medium",
        details: dict[str, Any] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record a policy violation event."""
        self._check_entered()
        event = PolicyViolationEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"policy_violation_{violation_type}",
            policy_name=policy_name,
            severity=severity,
            violation_type=violation_type,
            details=details or {},
            upstream_event_ids=upstream_event_ids or [],
            importance=0.9,
        )
        await self._emit_event(event)
        return event.id

    async def record_prompt_policy(
        self,
        template_id: str,
        policy_parameters: dict[str, Any],
        *,
        speaker: str = "",
        state_summary: str = "",
        goal: str = "",
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record prompt-policy state for prompt-as-action traces."""
        self._check_entered()
        event = PromptPolicyEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"prompt_policy_{template_id}",
            template_id=template_id,
            policy_parameters=policy_parameters,
            speaker=speaker,
            state_summary=state_summary,
            goal=goal,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.65,
        )
        await self._emit_event(event)
        return event.id

    async def record_agent_turn(
        self,
        agent_id: str,
        speaker: str,
        turn_index: int,
        *,
        goal: str = "",
        content: str = "",
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record a multi-agent turn event."""
        self._check_entered()
        event = AgentTurnEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"agent_turn_{turn_index}",
            agent_id=agent_id,
            speaker=speaker,
            turn_index=turn_index,
            goal=goal,
            content=content,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.6,
        )
        await self._emit_event(event)
        return event.id

    async def record_behavior_alert(
        self,
        alert_type: str,
        signal: str,
        *,
        severity: str = "medium",
        related_event_ids: list[str] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        """Record a behavior anomaly event."""
        self._check_entered()
        event = BehaviorAlertEvent(
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            name=name or f"behavior_alert_{alert_type}",
            alert_type=alert_type,
            severity=severity,
            signal=signal,
            related_event_ids=related_event_ids or [],
            upstream_event_ids=upstream_event_ids or [],
            importance=0.82,
        )
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

        async with self._events_lock:
            self._events.append(checkpoint)
        if self._checkpoint_persister is not None:
            await self._checkpoint_persister(checkpoint)

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

        Non-destructively retrieves all events currently stored.
        Events remain in the list after this call.

        Returns:
            List of all stored events and checkpoints.
        """
        async with self._events_lock:
            return list(self._events)

    async def drain_events(self) -> list[TraceEvent | Checkpoint]:
        """Drain and return all queued events.

        Destructively retrieves all events, clearing the list.

        Returns:
            List of all stored events and checkpoints.
        """
        async with self._events_lock:
            events = list(self._events)
            self._events.clear()
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
        """Emit an event to the internal list and optionally to the event buffer.

        Increments the event sequence and stores the event locally.
        If an event buffer is configured, also publishes to it for real-time streaming.
        Wraps persistence and buffer operations in error handling to prevent crashes.

        Args:
            event: The event to emit.
        """
        from agent_debugger_sdk.config import get_config
        config = get_config()
        if not config.enabled:
            return  # Skip everything when disabled

        current_seq = _event_sequence.get()
        _event_sequence.set(current_seq + 1)

        event.metadata["sequence"] = current_seq + 1
        event.importance = get_importance_scorer().score(event)

        async with self._events_lock:
            self._events.append(event)

        if isinstance(event, LLMResponseEvent):
            usage = event.usage
            self.session.total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            self.session.total_cost_usd += event.cost_usd
            self.session.llm_calls += 1

        # Persist — never crash the user's code
        persister = self._event_persister or _default_event_persister.get()
        if persister:
            try:
                await persister(event)
            except Exception:
                import logging
                logging.getLogger("agent_debugger").warning(
                    "Failed to persist event %s: collector may be unavailable", event.id,
                    exc_info=True,
                )

        # Session update — never crash the user's code
        if self._session_update_hook is not None:
            try:
                await self._session_update_hook(self.session)
            except Exception:
                import logging
                logging.getLogger("agent_debugger").warning(
                    "Failed to update session %s: collector may be unavailable", self.session_id,
                    exc_info=True,
                )

        # Publish to event buffer for real-time streaming if configured
        buffer = self._event_buffer or _default_event_buffer.get()
        if buffer:
            try:
                await buffer.publish(self.session_id, event)
            except Exception:
                import logging
                logging.getLogger("agent_debugger").warning(
                    "Failed to publish event %s to buffer", event.id,
                    exc_info=True,
                )


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
