"""Abstract base for event buffers."""
from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import TraceEvent


class BufferBase(abc.ABC):
    """Interface for event pub/sub buffers.

    This abstract base class defines the contract that all event buffer
    implementations must follow. Both in-memory and Redis-backed buffers
    implement this interface.

    Implementations must provide:
    - Async publish/subscribe for real-time event streaming
    - Event storage and retrieval by session ID
    - Session ID enumeration
    """

    @abc.abstractmethod
    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish event to all subscribers.

        Args:
            session_id: Session ID to publish to
            event: TraceEvent to publish
        """
        ...

    @abc.abstractmethod
    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """Subscribe to events for a session.

        Args:
            session_id: Session ID to subscribe to

        Returns:
            asyncio.Queue that will receive events
        """
        ...

    @abc.abstractmethod
    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from events.

        Args:
            session_id: Session ID to unsubscribe from
            queue: Queue to remove from subscribers
        """
        ...

    @abc.abstractmethod
    def get_events(self, session_id: str) -> list[TraceEvent]:
        """Get all stored events for a session.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent objects
        """
        ...

    @abc.abstractmethod
    def get_session_ids(self) -> list[str]:
        """Get all session IDs with buffered events.

        Returns:
            List of session IDs
        """
        ...
