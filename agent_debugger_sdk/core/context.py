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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from .checkpoint_manager import CheckpointManager
from .emitter import EventBufferLike, EventEmitter
from .events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from .recorders import RecordingMixin
from .transport_service import TransportService

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


class TraceContext(RecordingMixin):
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
        self._emitter = EventEmitter(
            session_id=self.session_id,
            session=self.session,
            event_store=self._events,
            event_lock=self._events_lock,
            event_sequence=_event_sequence,
            event_buffer=self._event_buffer,
            event_persister=self._event_persister,
            session_update_hook=self._session_update_hook,
        )

        self._checkpoint_manager = CheckpointManager(
            session_id=self.session_id,
            event_emitter=self._emitter,
            event_store=self._events,
            event_lock=self._events_lock,
            checkpoint_persister=self._checkpoint_persister,
        )

        self._session_start_event: TraceEvent | None = None
        self._entered = False
        self._transport_service = TransportService()
        self._restored_state: BaseCheckpointState | None = None

    @classmethod
    async def restore(
        cls,
        checkpoint_id: str,
        *,
        session_id: str | None = None,
        server_url: str | None = None,
        label: str = "",
    ) -> TraceContext:
        """Restore execution from a checkpoint.

        Creates a new TraceContext pre-populated with checkpoint state.
        The restored session references the original in its config.

        Args:
            checkpoint_id: ID of checkpoint to restore from.
            session_id: Optional session ID for the restored session (new UUID if None).
            server_url: Server URL (uses configured endpoint if None).
            label: Label for the restored session.

        Returns:
            TraceContext with restored state accessible via ctx.restored_state.

        Example:
            async with await TraceContext.restore("cp-abc123") as ctx:
                state = ctx.restored_state  # LangChainCheckpointState
                messages = state.messages   # Pre-populated history
        """
        import httpx

        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        if server_url is None:
            from agent_debugger_sdk.config import get_config

            config = get_config()
            server_url = config.endpoint or "http://localhost:8000"

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server_url}/api/checkpoints/{checkpoint_id}")
            response.raise_for_status()
            checkpoint_data = response.json()

        state_dict = checkpoint_data.get("state", {})
        original_session_id = checkpoint_data.get("session_id", "")

        ctx = cls(
            session_id=session_id or str(uuid.uuid4()),
            agent_name=label or f"restored from {checkpoint_id[:8]}",
            framework=state_dict.get("framework", "custom"),
            config={
                "restored_from_checkpoint": checkpoint_id,
                "original_session_id": original_session_id,
            },
        )
        ctx._restored_state = validate_checkpoint_state(state_dict)
        return ctx

    @property
    def restored_state(self) -> BaseCheckpointState | None:
        """The checkpoint state this context was restored from, if any."""
        return self._restored_state

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
        # instance-level hooks via TransportService.
        self._transport_service.configure_for_cloud_mode()

        # Set instance-level hooks from transport service if cloud mode was configured
        if self._transport_service.event_persister is not None:
            self._event_persister = self._transport_service.event_persister
            self._emitter.set_event_persister(self._event_persister)
        if self._transport_service.session_update_hook is not None:
            self._session_update_hook = self._transport_service.session_update_hook
            self._emitter.set_session_update_hook(self._session_update_hook)
        if self._transport_service.session_start_hook is not None:
            self._session_start_hook = self._transport_service.session_start_hook

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
        status = SessionStatus.COMPLETED
        if exc_type is not None:
            status = SessionStatus.ERROR
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
        self.session.ended_at = datetime.now(timezone.utc)

        await self._emit_event(end_event)
        if self._session_update_hook is not None:
            await self._session_update_hook(self.session)

        _current_session_id.set(None)
        _current_parent_id.set(None)
        _event_sequence.set(0)
        _current_context.set(None)
        self._entered = False

        # Close transport service if it was created
        await self._transport_service.close()

    @property
    def _checkpoint_sequence(self) -> int:
        """Get the current checkpoint sequence number (for backward compatibility)."""
        return self._checkpoint_manager.checkpoint_sequence

    async def create_checkpoint(
        self,
        state: dict[str, Any] | BaseCheckpointState,
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
        return await self._checkpoint_manager.create_checkpoint(
            state=state,
            memory=memory,
            importance=importance,
            parent_id=_current_parent_id.get(),
        )

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
        """Emit an event through the shared event emitter."""
        await self._emitter.emit(event)


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


__all__ = [
    "TraceContext",
    "get_current_context",
    "get_current_session_id",
    "get_current_parent_id",
    "configure_event_pipeline",
    "_get_default_event_buffer",
]
