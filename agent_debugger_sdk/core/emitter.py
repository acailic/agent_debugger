"""Event emission helpers for trace contexts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Protocol

from agent_debugger_sdk.config import get_config

from .events import Checkpoint, LLMResponseEvent, Session, TraceEvent
from .scorer import get_importance_scorer

logger = logging.getLogger("agent_debugger")


class EventBufferLike(Protocol):
    """Protocol for publish-capable event buffers."""

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish an event for live consumers."""
        ...


class EventEmitter:
    """Emit events with scoring, persistence, and live publishing."""

    def __init__(
        self,
        *,
        session_id: str,
        session: Session,
        event_store: list[TraceEvent | Checkpoint],
        event_lock: asyncio.Lock,
        event_sequence: ContextVar[int],
        event_buffer: EventBufferLike | None,
        event_persister: Callable[[TraceEvent], Awaitable[None]] | None,
        session_update_hook: Callable[[Session], Awaitable[None]] | None,
    ) -> None:
        self._session_id = session_id
        self._session = session
        self._event_store = event_store
        self._event_lock = event_lock
        self._event_sequence = event_sequence
        self._event_buffer = event_buffer
        self._event_persister = event_persister
        self._session_update_hook = session_update_hook

    def set_event_buffer(self, event_buffer: EventBufferLike | None) -> None:
        """Update the event buffer target."""
        self._event_buffer = event_buffer

    def set_event_persister(self, event_persister: Callable[[TraceEvent], Awaitable[None]] | None) -> None:
        """Update the event persister target."""
        self._event_persister = event_persister

    def set_session_update_hook(
        self,
        session_update_hook: Callable[[Session], Awaitable[None]] | None,
    ) -> None:
        """Update the session update hook target."""
        self._session_update_hook = session_update_hook

    async def emit(self, event: TraceEvent) -> None:
        """Emit an event to storage, hooks, and live consumers."""
        config = get_config()
        if not config.enabled:
            return

        current_seq = self._event_sequence.get()
        self._event_sequence.set(current_seq + 1)

        event.metadata["sequence"] = current_seq + 1
        event.importance = get_importance_scorer().score(event)

        async with self._event_lock:
            self._event_store.append(event)

        if isinstance(event, LLMResponseEvent):
            usage = event.usage
            self._session.total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            self._session.total_cost_usd += event.cost_usd
            self._session.llm_calls += 1

        if self._event_persister is not None:
            try:
                await self._event_persister(event)
            except Exception:
                logger.warning(
                    "Failed to persist event %s: collector may be unavailable",
                    event.id,
                    exc_info=True,
                )

        if self._session_update_hook is not None:
            try:
                await self._session_update_hook(self._session)
            except Exception:
                logger.warning(
                    "Failed to update session %s: collector may be unavailable",
                    self._session_id,
                    exc_info=True,
                )

        if self._event_buffer is not None:
            try:
                await self._event_buffer.publish(self._session_id, event)
            except Exception:
                logger.warning(
                    "Failed to publish event %s to buffer",
                    event.id,
                    exc_info=True,
                )
