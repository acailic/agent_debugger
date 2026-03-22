"""Async event buffer with subscriber support for real-time streaming.

This module provides a simple async buffer that stores events in memory
and supports pub/sub for real-time SSE streaming to clients.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime

from agent_debugger_sdk.core.events import TraceEvent

logger = logging.getLogger(__name__)


@dataclass
class EventBuffer:
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
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
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
        # Enforce memory bounds
        await self._enforce_bounds(session_id)

        if session_id not in self._events:
            self._events[session_id] = []
        self._events[session_id].append(event)
        self._session_activity[session_id] = datetime.now(UTC)

        async with self._lock:
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
        async with self._lock:
            self._queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from events.

        Args:
            session_id: Session ID to unsubscribe from
            queue: Queue to remove from subscribers
        """
        async with self._lock:
            if queue in self._queues[session_id]:
                self._queues[session_id].remove(queue)

    def get_events(self, session_id: str) -> list[TraceEvent]:
        """Get all stored events for a session.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent objects
        """
        return self._events.get(session_id, [])

    def get_session_ids(self) -> list[str]:
        """Get all session IDs with buffered events.

        Returns:
            List of session IDs
        """
        return list(self._events.keys())

    def flush(self, session_id: str) -> list[TraceEvent]:
        """Atomically pop and return all events for a session.

        Args:
            session_id: Session ID to flush

        Returns:
            List of TraceEvent objects (may be empty)
        """
        events = self._events.pop(session_id, [])
        self._session_activity.pop(session_id, None)
        return events

    async def _enforce_bounds(self, session_id: str) -> None:
        """Enforce memory bounds for events and sessions.

        Args:
            session_id: Current session being accessed
        """
        # Trim events if this session exceeds max
        if session_id in self._events and len(self._events[session_id]) >= self.max_events_per_session:
            # Remove oldest events
            excess = len(self._events[session_id]) - self.max_events_per_session + 1
            self._events[session_id] = self._events[session_id][excess:]
            logger.warning(f"Trimmed {excess} oldest events from session {session_id}")

        # Evict oldest sessions if we exceed max_sessions
        if len(self._events) >= self.max_sessions and session_id not in self._events:
            # Find least recently used session
            if self._session_activity:
                lru_session = min(self._session_activity, key=self._session_activity.get)
                self._events.pop(lru_session, None)
                self._session_activity.pop(lru_session, None)
                logger.warning(f"Evicted session {lru_session} due to memory bounds")


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
