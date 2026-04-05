"""TraceContext class for managing async-safe state during agent execution tracing."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from agent_debugger_sdk.core.emitter import EventBufferLike, EventEmitter
from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from agent_debugger_sdk.core.recorders import RecordingMixin

from .pipeline import _get_default_event_buffer
from .session_manager import SessionManager
from .vars import (
    _current_context,
    _current_parent_id,
    _current_session_id,
    _default_checkpoint_persister,
    _default_event_persister,
    _default_session_start_hook,
    _default_session_update_hook,
    _event_sequence,
)


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
        self._session_manager = SessionManager(
            session=self.session,
            session_start_hook=self._session_start_hook,
            session_update_hook=self._session_update_hook,
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

        self._session_start_event: TraceEvent | None = None
        self._entered = False
        self._transport: Any | None = None  # HttpTransport instance if in cloud mode
        self._restored_state: BaseCheckpointState | None = None

    @classmethod
    async def restore(
        cls,
        checkpoint_id: str,
        *,
        session_id: str | None = None,
        server_url: str | None = None,
        label: str = "",
        replay_events: bool = False,
        track_drift: bool = False,
        original_session_id: str | None = None,
        importance_threshold: float | None = None,
        on_replay_event: Any | None = None,
    ) -> TraceContext:
        """Restore execution from a checkpoint.

        Creates a new TraceContext pre-populated with checkpoint state.
        The restored session references the original in its config.

        Args:
            checkpoint_id: ID of checkpoint to restore from.
            session_id: Optional session ID for the restored session (new UUID if None).
            server_url: Server URL (uses configured endpoint if None).
            label: Label for the restored session.
            replay_events: If True, fetch and replay events recorded after the
                checkpoint, storing them in ``ctx.replayed_events``.
            track_drift: If True, attach a :class:`~agent_debugger_sdk.drift.DriftDetector`
                as ``ctx._drift_detector`` for comparing restored vs original execution.
            original_session_id: Session ID to pull post-checkpoint events from.
                Defaults to the session recorded in the checkpoint payload.
            importance_threshold: When ``replay_events=True``, only include events
                with importance >= this value.
            on_replay_event: Optional callback invoked for each replayed event
                (including a synthetic restore-start event).  Return ``False`` to
                cancel the remainder of the replay.

        Returns:
            TraceContext with restored state accessible via ctx.restored_state.

        Example:
            async with await TraceContext.restore("cp-abc123") as ctx:
                state = ctx.restored_state  # LangChainCheckpointState
                messages = state.messages   # Pre-populated history
        """
        import logging

        logger = logging.getLogger(__name__)

        session, restored_state = await SessionManager.restore_from_checkpoint(
            checkpoint_id,
            session_id=session_id,
            server_url=server_url,
            label=label,
        )

        ctx = cls(
            session_id=session.id,
            agent_name=session.agent_name,
            framework=session.framework,
            config=session.config,
        )
        ctx._restored_state = restored_state
        ctx.replayed_events: list[dict[str, Any]] = []
        ctx._drift_detector = None
        ctx._hook_errors: list[Exception] = []
        ctx._restored_target: Any = None

        # Apply restore hook for the checkpoint's framework
        if restored_state is not None:
            framework = getattr(restored_state, "framework", "custom")
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY

            hook = RESTORE_HOOK_REGISTRY.get(framework)
            if hook is not None:
                try:
                    import types
                    restore_target = types.SimpleNamespace()
                    result = await hook(restored_state, restore_target)
                    ctx._restored_target = result if result is not None else restore_target
                except Exception as exc:
                    ctx._hook_errors.append(exc)
                    logger.warning("Restore hook for %r failed: %s", framework, exc)

        # Note: DriftDetector will be seeded inside replay_events block if track_drift is True

        # Auto-replay post-checkpoint events if requested
        if replay_events:
            from .session_manager import _resolve_restore_server_url

            resolved_url = _resolve_restore_server_url(server_url)
            orig_session_id = (
                original_session_id
                or session.config.get("original_session_id", "")
            )
            checkpoint_sequence: int = session.config.get("checkpoint_sequence", 0)

            # Emit a synthetic restore-start event so callers (e.g. cancellation
            # callbacks) receive at least one notification even when there are no
            # events to replay.
            restore_start_event: dict[str, Any] = {
                "event_type": "restore_start",
                "checkpoint_id": checkpoint_id,
                "session_id": orig_session_id,
            }
            if on_replay_event is not None:
                if on_replay_event(restore_start_event) is False:
                    return ctx

            # Fetch recorded events from the original session
            raw_events: list[dict[str, Any]] = []
            try:
                import httpx

                # Strip trailing slash to avoid double slashes
                base_url = resolved_url.rstrip("/")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Fetch with pagination (limit=100, paginate until partial page)
                    limit = 100
                    offset = 0
                    while True:
                        response = await client.get(
                            f"{base_url}/api/sessions/{orig_session_id}/traces",
                            params={"limit": limit, "offset": offset}
                        )
                        response.raise_for_status()
                        page_traces = response.json().get("traces", [])
                        raw_events.extend(page_traces)
                        if len(page_traces) < limit:
                            break
                        offset += limit
            except Exception as exc:
                logger.warning("Auto-replay event fetch failed: %s", exc)

            # Seed drift detector with baseline events for comparison
            if track_drift:
                from agent_debugger_sdk.drift import DriftDetector
                ctx._drift_detector = DriftDetector(raw_events)

            # Filter: only events after the checkpoint sequence
            post_events = [
                e for e in raw_events
                if e.get("sequence", checkpoint_sequence + 1) > checkpoint_sequence
            ]

            # Filter by importance threshold
            if importance_threshold is not None:
                post_events = [
                    e for e in post_events
                    if e.get("importance", 1.0) >= importance_threshold
                ]

            # Seed drift detector with post-checkpoint events as baseline
            if ctx._drift_detector is not None:
                ctx._drift_detector.original_events = post_events.copy()

            # Replay each event, honouring cancellation
            for event in post_events:
                if on_replay_event is not None:
                    if on_replay_event(event) is False:
                        break
                ctx.replayed_events.append(event)

        return ctx

    @property
    def restored_state(self) -> BaseCheckpointState | None:
        """The checkpoint state this context was restored from, if any."""
        return self._restored_state

    @property
    def restored_target(self) -> Any:
        """The reconstructed framework target from the restore hook, if any."""
        return self._restored_target

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

        # Wire in HTTP transport for cloud mode (when API key is present)
        # IMPORTANT: Do NOT call configure_event_pipeline() here as it mutates
        # global ContextVars and would break concurrent sessions. Instead, set
        # instance-level hooks.
        # Only set up HTTP transport if hooks aren't already configured via
        # configure_event_pipeline() (e.g., in tests or server-side usage).
        # Check ALL hooks, not just session_start - tests may configure only some hooks.
        hooks_configured = any(
            [
                self._session_start_hook,
                self._session_update_hook,
                self._event_persister,
                self._checkpoint_persister,
            ]
        )
        from agent_debugger_sdk.config import get_config

        config = get_config()
        if not hooks_configured and config.enabled and getattr(config, "api_key", None):
            # No hooks configured - use HTTP transport to send events to the server
            from agent_debugger_sdk.transport import HttpTransport

            self._transport = HttpTransport(config.endpoint, config.api_key)
            # Set instance-level hooks (not global pipeline)
            self._event_persister = self._transport.send_event
            self._session_start_hook = self._transport.send_session_start
            self._session_update_hook = self._transport.send_session_update
            self._emitter._event_persister = self._event_persister
            self._emitter._session_update_hook = self._session_update_hook
            # Update session manager hooks after transport setup
            self._session_manager._session_start_hook = self._session_start_hook
            self._session_manager._session_update_hook = self._session_update_hook
        else:
            # Hooks already configured (e.g., via configure_event_pipeline in tests)
            self._transport = None

        self._entered = True
        await self._session_manager.start()

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

        await self._emit_event(end_event)
        await self._session_manager.update(status)

        _current_session_id.set(None)
        _current_parent_id.set(None)
        _event_sequence.set(0)
        _current_context.set(None)
        self._entered = False

        # Close transport if it was created
        if self._transport is not None:
            await self._transport.close()
            self._transport = None

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

        from agent_debugger_sdk.checkpoints import serialize_checkpoint_state, validate_checkpoint_state

        validated = validate_checkpoint_state(state)
        state_dict = serialize_checkpoint_state(validated)

        self._checkpoint_sequence += 1
        checkpoint_id = str(uuid.uuid4())

        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=self.session_id,
            event_id=_current_parent_id.get() or "",
            sequence=self._checkpoint_sequence,
            state=state_dict,
            memory=memory or {},
            timestamp=datetime.now(timezone.utc),
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
        """Emit an event through the shared event emitter."""
        await self._emitter.emit(event)
