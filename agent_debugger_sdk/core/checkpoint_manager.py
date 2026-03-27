"""Checkpoint creation and management."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from .events import Checkpoint, EventType, TraceEvent


class CheckpointManager:
    """Manage checkpoint creation for TraceContext.

    Responsibilities:
    - Create checkpoints with validated state
    - Track checkpoint sequence
    - Persist checkpoints via callback
    - Emit checkpoint events
    """

    def __init__(
        self,
        session_id: str,
        event_emitter: Any,  # EventEmitter-like with emit() method
        event_store: list[TraceEvent | Checkpoint],
        event_lock: Any,  # asyncio.Lock
        checkpoint_persister: Callable[[Checkpoint], Awaitable[None]] | None = None,
    ) -> None:
        self._session_id = session_id
        self._emitter = event_emitter
        self._event_store = event_store
        self._event_lock = event_lock
        self._persister = checkpoint_persister
        self._checkpoint_sequence = 0

    def set_persister(self, persister: Callable[[Checkpoint], Awaitable[None]] | None) -> None:
        """Set the checkpoint persister callback."""
        self._persister = persister

    @property
    def checkpoint_sequence(self) -> int:
        """Get the current checkpoint sequence number."""
        return self._checkpoint_sequence

    async def create_checkpoint(
        self,
        state: dict[str, Any] | BaseCheckpointState,
        memory: dict[str, Any] | None = None,
        importance: float = 0.5,
        parent_id: str | None = None,
    ) -> str:
        """Create a checkpoint for time-travel debugging.

        Args:
            state: The agent's state at this point
            memory: Optional memory/context snapshot
            importance: Relative importance score (0.0-1.0)
            parent_id: Optional parent event ID for hierarchical tracking

        Returns:
            The checkpoint ID
        """
        from agent_debugger_sdk.checkpoints import serialize_checkpoint_state, validate_checkpoint_state

        validated = validate_checkpoint_state(state)
        state_dict = serialize_checkpoint_state(validated)

        self._checkpoint_sequence += 1
        checkpoint_id = str(uuid.uuid4())

        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=self._session_id,
            event_id=parent_id or "",
            sequence=self._checkpoint_sequence,
            state=state_dict,
            memory=memory or {},
            timestamp=datetime.now(timezone.utc),
            importance=max(0.0, min(1.0, importance)),
        )

        # Store checkpoint in event store
        async with self._event_lock:
            self._event_store.append(checkpoint)

        # Persist checkpoint if persister is configured
        if self._persister is not None:
            await self._persister(checkpoint)

        # Emit checkpoint event
        event = TraceEvent(
            id=str(uuid.uuid4()),
            session_id=self._session_id,
            parent_id=parent_id,
            event_type=EventType.CHECKPOINT,
            name=f"checkpoint_{self._checkpoint_sequence}",
            data={
                "checkpoint_id": checkpoint_id,
                "sequence": self._checkpoint_sequence,
            },
            importance=checkpoint.importance,
        )
        await self._emitter.emit(event)

        return checkpoint_id
