"""Async event buffer with subscriber support for real-time streaming.

This module provides a simple async buffer that stores events in memory
and supports pub/sub for real-time SSE streaming to clients.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field

from agent_debugger_sdk.core.events import TraceEvent


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

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish event to all subscribers.

        Args:
            session_id: Session ID to publish to
            event: TraceEvent to publish
        """
        if session_id not in self._events:
            self._events[session_id] = []
        self._events[session_id].append(event)

        async with self._lock:
            queues = self._queues.get(session_id, [])
            dead_queues = []

            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_queues.append(queue)

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
