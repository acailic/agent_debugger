"""Async event buffer with subscriber support for real-time streaming.

This module provides a simple async buffer that stores events in memory
and supports pub/sub for real-time SSE streaming to clients.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_debugger_sdk.core.events import TraceEvent

from .buffer_base import BufferBase

logger = logging.getLogger(__name__)


@dataclass
class EventBuffer(BufferBase):
    """Simple async buffer with subscriber support.

    Stores events in memory and allows multiple subscribers to receive
    real-time updates via asyncio queues.

    Example:
        >>> buffer = EventBuffer()
        >>> await buffer.publish("session-123", event)
        >>> queue = await buffer.subscribe("session-123")
        >>> event = await queue.get()
    """

    _queues: dict[str, list[asyncio.Queue]] = field(default_factory=lambda: defaultdict(list))
    _lock: asyncio.Lock | None = field(default=None, init=False, repr=False)
    _lock_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _events: dict[str, list[TraceEvent]] = field(default_factory=dict)
    _session_activity: dict[str, datetime] = field(default_factory=dict)
    max_events_per_session: int = 10_000
    max_sessions: int = 1_000

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish event to all subscribers.

        Args:
            session_id: Session ID to publish to
            event: TraceEvent to publish
        """
        async with self._get_lock():
            # Enforce memory bounds (sync operation, no I/O)
            self._enforce_bounds(session_id)

            # Store event and update activity
            if session_id not in self._events:
                self._events[session_id] = []
            self._events[session_id].append(event)
            self._session_activity[session_id] = datetime.now(timezone.utc)

            # Notify subscribers
            queues = self._queues.get(session_id, [])
            dead_queues = []

            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_queues.append(queue)
                    logger.warning(f"Dropping subscriber queue for session {session_id} due to QueueFull")

            for q in dead_queues:
                self._queues[session_id].remove(q)

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """Subscribe to events for a session.

        Args:
            session_id: Session ID to subscribe to

        Returns:
            asyncio.Queue that will receive events
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._get_lock():
            self._queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from events.

        Args:
            session_id: Session ID to unsubscribe from
            queue: Queue to remove from subscribers
        """
        async with self._get_lock():
            if queue in self._queues[session_id]:
                self._queues[session_id].remove(queue)

    async def get_events(self, session_id: str) -> list[TraceEvent]:
        """Get all stored events for a session.

        Returns a copy to prevent external modification. Consider making
        this return a read-only view if performance is critical.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent objects (copy)
        """
        async with self._get_lock():
            return list(self._events.get(session_id, []))

    async def get_session_ids(self) -> list[str]:
        """Get all session IDs with buffered events.

        Returns a copy to prevent external modification of the internal keys.
        Consider making this return a read-only view if performance is critical.

        Returns:
            List of session IDs (copy)
        """
        async with self._get_lock():
            return list(self._events.keys())

    async def flush(self, session_id: str) -> list[TraceEvent]:
        """Atomically pop and return all events for a session.

        Args:
            session_id: Session ID to flush

        Returns:
            List of TraceEvent objects (may be empty)
        """
        async with self._get_lock():
            events = self._events.pop(session_id, [])
            self._session_activity.pop(session_id, None)
            return events

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _enforce_bounds(self, session_id: str) -> bool:
        """Enforce memory bounds for events and sessions.

        This is a synchronous method as it only modifies in-memory data.

        Args:
            session_id: Current session being accessed

        Returns:
            True if data was dropped due to bounds enforcement.
        """
        dropped = False

        # Trim events if this session exceeds max
        if session_id in self._events and len(self._events[session_id]) >= self.max_events_per_session:
            excess = len(self._events[session_id]) - self.max_events_per_session + 1
            self._events[session_id] = self._events[session_id][excess:]
            logger.warning(f"Trimmed {excess} oldest events from session {session_id}")
            dropped = True

        # Evict oldest sessions if we exceed max_sessions
        if len(self._events) >= self.max_sessions and session_id not in self._events:
            if self._session_activity:
                lru_session = min(self._session_activity, key=self._session_activity.get)
                self._events.pop(lru_session, None)
                self._session_activity.pop(lru_session, None)
                logger.warning(f"Evicted session {lru_session} due to memory bounds")
                dropped = True

        return dropped


_event_buffer: EventBuffer | None = None


def get_event_buffer() -> EventBuffer:
    """Get the global event buffer singleton.

    Creates the buffer on first call, returns existing instance thereafter.

    Returns:
        The global EventBuffer instance
    """
    global _event_buffer
    if _event_buffer is None:
        _event_buffer = EventBuffer()
    return _event_buffer


def set_event_buffer(buf: EventBuffer | None) -> None:
    """Override the global event buffer.

    Pass ``None`` to reset so the next ``get_event_buffer()`` call creates
    a fresh instance.  Intended for tests that need an isolated buffer.

    Args:
        buf: An EventBuffer instance to use, or None to clear.
    """
    global _event_buffer
    _event_buffer = buf
