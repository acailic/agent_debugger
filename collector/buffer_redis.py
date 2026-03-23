"""Redis-backed event buffer using Streams + pub/sub."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from agent_debugger_sdk.core.events import TraceEvent, EventType
from collector.buffer_base import BufferBase


class RedisEventBuffer(BufferBase):
    """Redis-backed event buffer using Streams for durable storage and pub/sub for live fan-out.

    This buffer implements the BufferBase interface using Redis Streams for durable
    event storage and Redis pub/sub for real-time event distribution to subscribers.

    Attributes:
        _redis: Redis async client instance
        _stream_prefix: Prefix for Redis stream keys
        _pubsub_prefix: Prefix for Redis pub/sub channel keys
        _max_stream_len: Maximum length of Redis streams (approximate, using MAXLEN)
        _local_queues: Dict mapping session_id to list of subscriber queues
        _pubsub_tasks: Dict mapping session_id to pubsub listener tasks
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        redis_url: str = "redis://localhost:6379",
        stream_prefix: str = "ad:stream:",
        pubsub_prefix: str = "ad:live:",
        max_stream_len: int = 10_000,
    ) -> None:
        """Initialize the Redis event buffer.

        Args:
            redis_client: Optional existing Redis client. If None, creates new one from URL.
            redis_url: Redis connection URL (used if redis_client is None).
            stream_prefix: Prefix for Redis stream keys.
            pubsub_prefix: Prefix for Redis pub/sub channel keys.
            max_stream_len: Maximum approximate length for each Redis stream.
        """
        self._redis = redis_client or Redis.from_url(redis_url)
        self._stream_prefix = stream_prefix
        self._pubsub_prefix = pubsub_prefix
        self._max_stream_len = max_stream_len
        self._local_queues: dict[str, list[asyncio.Queue]] = {}
        self._pubsub_tasks: dict[str, asyncio.Task] = {}

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish an event to the buffer.

        Events are written to a Redis Stream for durability and also published
        to a pub/sub channel for real-time delivery to subscribers.

        Args:
            session_id: Session ID to publish to.
            event: TraceEvent to publish.
        """
        payload = json.dumps(event.to_dict(), default=str)

        # Durable: add to stream
        await self._redis.xadd(
            f"{self._stream_prefix}{session_id}",
            {"event": payload},
            maxlen=self._max_stream_len,
        )

        # Live: publish for SSE subscribers
        await self._redis.publish(f"{self._pubsub_prefix}{session_id}", payload)

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """Subscribe to events for a session.

        Creates a new queue for the subscriber and starts a pub/sub listener
        task if this is the first subscriber for the session.

        Args:
            session_id: Session ID to subscribe to.

        Returns:
            asyncio.Queue that will receive TraceEvent objects.
        """
        queue: asyncio.Queue = asyncio.Queue()

        if session_id not in self._local_queues:
            self._local_queues[session_id] = []
            # Start listener task for this session
            self._pubsub_tasks[session_id] = asyncio.create_task(
                self._listen(session_id)
            )

        self._local_queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from events.

        Removes the queue from subscribers and cancels the listener task
        if this was the last subscriber for the session.

        Args:
            session_id: Session ID to unsubscribe from.
            queue: Queue to remove from subscribers.
        """
        if session_id in self._local_queues:
            try:
                self._local_queues[session_id].remove(queue)
            except ValueError:
                pass  # Queue not in list

            # Clean up if no more subscribers
            if not self._local_queues[session_id]:
                del self._local_queues[session_id]
                task = self._pubsub_tasks.pop(session_id, None)
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    def get_events(self, session_id: str) -> list[TraceEvent]:
        """Get all stored events for a session.

        Note: Redis streams are read via xrange commands, not stored in-memory.
        This method returns an empty list. Use Redis client directly to read
        from streams if needed.

        Args:
            session_id: Session ID to get events for.

        Returns:
            Empty list (Redis streams are read differently).
        """
        return []

    def get_session_ids(self) -> list[str]:
        """Get all session IDs with active subscribers.

        Returns:
            List of session IDs that have active subscribers.
        """
        return list(self._local_queues.keys())

    async def _listen(self, session_id: str) -> None:
        """Listen for pub/sub messages and distribute to local queues.

        This runs as a background task for each session with subscribers.
        It deserializes Redis pub/sub messages and puts TraceEvent objects
        into all subscriber queues for the session.

        Args:
            session_id: Session ID to listen for.
        """
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"{self._pubsub_prefix}{session_id}")

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])

                    # Deserialize: convert ISO timestamp string → datetime,
                    # event_type string → EventType enum
                    if isinstance(data.get("timestamp"), str):
                        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

                    if isinstance(data.get("event_type"), str):
                        data["event_type"] = EventType(data["event_type"])

                    event = TraceEvent(**data)

                    # Distribute to all subscriber queues
                    for q in self._local_queues.get(session_id, []):
                        await q.put(event)

                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    # Skip malformed messages
                    continue

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(f"{self._pubsub_prefix}{session_id}")

    async def close(self) -> None:
        """Close the Redis connection and clean up resources.

        Cancels all pub/sub listener tasks and closes the Redis connection.
        """
        # Cancel all listener tasks
        for task in self._pubsub_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._pubsub_tasks.clear()
        self._local_queues.clear()

        # Close Redis connection
        await self._redis.close()

    async def __aenter__(self) -> RedisEventBuffer:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
