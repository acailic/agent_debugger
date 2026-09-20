"""Redis-backed event buffer using Streams + pub/sub.

This module imports safely even when the optional 'redis' package is not
installed (Redis is imported lazily). Constructing a RedisEventBuffer
without an injected client raises RuntimeError if redis is not installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.buffer_base import BufferBase

logger = logging.getLogger(__name__)


def _get_redis_class() -> type:
    """Lazily import Redis class to avoid ImportError if redis is not installed."""
    try:
        from redis.asyncio import Redis

        return Redis
    except ImportError as e:
        raise ImportError(
            "Redis package is required for RedisEventBuffer. Install it with: pip install agent-debugger[cloud]"
        ) from e


class RedisEventBuffer(BufferBase):
    """Redis-backed event buffer using Streams for durable storage and pub/sub for live fan-out.

    This buffer implements the BufferBase interface using Redis Streams for durable
    event storage and Redis pub/sub for real-time event distribution to subscribers.

    Durability limit: XADD appends each event to a length-capped Redis Stream and
    PUBLISH fans it out to currently attached subscribers — nothing more. There is
    no persistence worker draining the streams, no consumer-group replay, and no
    redelivery of messages published while a subscriber was disconnected;
    get_events() and flush() therefore return empty lists. Acknowledged
    persistence remains the database path (collector.persistence).

    Attributes:
        _redis: Redis async client instance
        _stream_prefix: Prefix for Redis stream keys
        _pubsub_prefix: Prefix for Redis pub/sub channel keys
        _max_stream_len: Maximum length of Redis streams (approximate, using MAXLEN)
        _subscriber_maxsize: Per-subscriber queue bound (see subscribe())
        _reconnect_delay: Seconds to wait before re-subscribing after a connection drop
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
        subscriber_maxsize: int = 100,
        reconnect_delay: float = 1.0,
    ) -> None:
        """Initialize the Redis event buffer.

        Args:
            redis_client: Optional existing Redis client. If None, creates new one from URL.
            redis_url: Redis connection URL (used if redis_client is None).
            stream_prefix: Prefix for Redis stream keys.
            pubsub_prefix: Prefix for Redis pub/sub channel keys.
            max_stream_len: Maximum approximate length for each Redis stream.
            subscriber_maxsize: Bounded size of each subscriber queue (see subscribe()).
            reconnect_delay: Seconds between re-subscribe attempts after a pub/sub
                connection drop.

        Raises:
            RuntimeError: If redis_client is None and the optional 'redis' package
                is not installed.
        """
        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                redis_cls = _get_redis_class()
            except ImportError as exc:
                raise RuntimeError(
                    "redis package not installed: RedisEventBuffer requires the optional "
                    "'redis' package to construct a client (pip install redis), or inject "
                    "an existing client via redis_client="
                ) from exc
            self._redis = redis_cls.from_url(redis_url)
        self._stream_prefix = stream_prefix
        self._pubsub_prefix = pubsub_prefix
        self._max_stream_len = max_stream_len
        self._subscriber_maxsize = subscriber_maxsize
        self._reconnect_delay = reconnect_delay
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

        Overflow policy: the queue is bounded (``subscriber_maxsize``, default
        100, matching the in-memory EventBuffer's queue size). When a slow
        subscriber's queue is full the listener drops the oldest queued event
        and delivers the newest one (block-free drop-oldest), rather than
        dropping the subscriber outright as EventBuffer does — a live SSE
        stream keeps receiving the most recent events instead of ending
        silently.

        Args:
            session_id: Session ID to subscribe to.

        Returns:
            asyncio.Queue that will receive TraceEvent objects.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._subscriber_maxsize)

        if session_id not in self._local_queues:
            self._local_queues[session_id] = []
            # Start listener task for this session
            self._pubsub_tasks[session_id] = asyncio.create_task(self._listen(session_id))

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

    async def get_events(self, session_id: str) -> list[TraceEvent]:
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

    async def get_session_ids(self) -> list[str]:
        """Get all session IDs with active subscribers.

        Returns:
            List of session IDs that have active subscribers.
        """
        return list(self._local_queues.keys())

    async def flush(self, session_id: str) -> list[TraceEvent]:
        """Flush is a no-op for Redis-backed streams."""
        return []

    async def _listen(self, session_id: str) -> None:
        """Listen for pub/sub messages and distribute to local queues.

        This runs as a background task for each session with subscribers.
        It deserializes Redis pub/sub messages and puts TraceEvent objects
        into all subscriber queues for the session.

        If the Redis connection drops, the listener waits ``reconnect_delay``
        seconds and then re-subscribes. Pub/sub has no replay, so events
        published while disconnected are not redelivered (see the class
        docstring's durability limit).

        Args:
            session_id: Session ID to listen for.
        """
        channel = f"{self._pubsub_prefix}{session_id}"
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue

                    event = self._decode_message(message)
                    if event is not None:
                        self._fanout(session_id, event)

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "Redis pub/sub listener for session %s failed (%r); "
                    "reconnecting in %.1fs",
                    session_id,
                    exc,
                    self._reconnect_delay,
                )
                await asyncio.sleep(self._reconnect_delay)
                continue
            finally:
                await self._aclose_pubsub(pubsub, channel)

            # Stream ended cleanly (server closed the channel): stop listening.
            return

    async def _aclose_pubsub(self, pubsub: Any, channel: str) -> None:
        """Best-effort cleanup of a pub/sub connection; never raises.

        Args:
            pubsub: Pub/sub object returned by ``Redis.pubsub()``.
            channel: Channel name to unsubscribe from.
        """
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        # redis-py >= 5 deprecates close() in favour of aclose(); test doubles
        # may expose neither.
        close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass

    def _decode_message(self, message: Any) -> TraceEvent | None:
        """Decode a pub/sub message into a TraceEvent.

        Args:
            message: Raw pub/sub message dict from redis-py.

        Returns:
            Decoded TraceEvent, or None if the message is malformed.
        """
        try:
            data = json.loads(message["data"])

            # Deserialize: convert ISO timestamp string → datetime,
            # event_type string → EventType enum
            if isinstance(data.get("timestamp"), str):
                data["timestamp"] = datetime.fromisoformat(data["timestamp"])

            if isinstance(data.get("event_type"), str):
                data["event_type"] = EventType(data["event_type"])

            return TraceEvent(**data)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            # Skip malformed messages
            return None

    def _fanout(self, session_id: str, event: TraceEvent) -> None:
        """Deliver an event to all subscriber queues without blocking.

        Uses the drop-oldest overflow policy documented on subscribe().

        Args:
            session_id: Session the event belongs to.
            event: TraceEvent to deliver.
        """
        for q in self._local_queues.get(session_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest queued event so the newest one fits; the
                # slow subscriber keeps its place instead of being dropped.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - racy edge
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:  # pragma: no cover - single consumer
                    logger.warning(
                        "Dropping event for slow subscriber of session %s (queue full)",
                        session_id,
                    )

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
