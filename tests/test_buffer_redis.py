"""Tests for Redis-backed event buffer.

These tests require the 'redis' package which is an optional dependency.
They will be skipped if redis is not installed.
"""
from __future__ import annotations

import asyncio

import pytest

# Skip entire module if redis is not installed
pytest.importorskip("redis")

from unittest.mock import AsyncMock, MagicMock, patch

from agent_debugger_sdk.core.events import TraceEvent, EventType
from collector.buffer_base import BufferBase
from collector.buffer_redis import RedisEventBuffer


def _make_event(session_id: str = "s1") -> TraceEvent:
    """Create a test TraceEvent."""
    return TraceEvent(
        session_id=session_id,
        parent_id=None,
        event_type=EventType.TOOL_CALL,
        name="test",
        data={},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )


def test_redis_buffer_is_subclass():
    """Test that RedisEventBuffer is a subclass of BufferBase."""
    assert issubclass(RedisEventBuffer, BufferBase)


@pytest.mark.asyncio
async def test_publish_calls_redis_xadd_and_publish():
    """Test that publish() calls Redis XADD and PUBLISH."""
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()
    mock_redis.publish = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis)
    event = _make_event()

    await buf.publish("s1", event)

    # Verify XADD was called for durable storage
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert "ad:stream:s1" in call_args[0][0]
    assert "event" in call_args[0][1]

    # Verify PUBLISH was called for live fan-out
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert "ad:live:s1" in call_args[0][0]


@pytest.mark.asyncio
async def test_subscribe_creates_queue_and_listener():
    """Test that subscribe() creates a queue and starts listener task."""
    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()

    # Mock pubsub() to return our mock_pubsub
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    buf = RedisEventBuffer(redis_client=mock_redis)
    queue = await buf.subscribe("s1")

    assert isinstance(queue, asyncio.Queue)
    assert "s1" in buf._local_queues
    assert queue in buf._local_queues["s1"]
    assert "s1" in buf._pubsub_tasks

    # Clean up
    task = buf._pubsub_tasks.pop("s1")
    task.cancel()


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    """Test that unsubscribe() removes queue from subscribers."""
    mock_redis = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis)
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()

    # Manually set up subscriptions
    buf._local_queues["s1"] = [queue1, queue2]

    # Unsubscribe one queue
    await buf.unsubscribe("s1", queue1)

    assert queue1 not in buf._local_queues["s1"]
    assert queue2 in buf._local_queues["s1"]


@pytest.mark.asyncio
async def test_unsubscribe_last_cancels_task():
    """Test that unsubscribing last queue cancels listener task."""
    mock_redis = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis)
    queue = asyncio.Queue()

    # Create a mock task
    task = asyncio.create_task(asyncio.sleep(10))
    buf._local_queues["s1"] = [queue]
    buf._pubsub_tasks["s1"] = task

    # Unsubscribe last queue
    await buf.unsubscribe("s1", queue)

    assert "s1" not in buf._local_queues
    assert "s1" not in buf._pubsub_tasks
    assert task.cancelled()


@pytest.mark.asyncio
async def test_get_events_returns_empty_list():
    """Test that get_events() returns empty list (streams read differently)."""
    mock_redis = AsyncMock()
    buf = RedisEventBuffer(redis_client=mock_redis)

    events = buf.get_events("s1")
    assert events == []


def test_get_session_ids():
    """Test that get_session_ids() returns list of session IDs."""
    mock_redis = AsyncMock()
    buf = RedisEventBuffer(redis_client=mock_redis)

    # Add some mock sessions
    buf._local_queues = {"s1": [], "s2": [], "s3": []}

    session_ids = buf.get_session_ids()
    assert set(session_ids) == {"s1", "s2", "s3"}


@pytest.mark.asyncio
async def test_close_cancels_tasks_and_closes_redis():
    """Test that close() cancels all tasks and closes Redis connection."""
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis)

    # Create mock tasks
    task1 = asyncio.create_task(asyncio.sleep(10))
    task2 = asyncio.create_task(asyncio.sleep(10))
    buf._pubsub_tasks = {"s1": task1, "s2": task2}
    buf._local_queues = {"s1": [], "s2": []}

    await buf.close()

    assert task1.cancelled()
    assert task2.cancelled()
    assert len(buf._pubsub_tasks) == 0
    assert len(buf._local_queues) == 0
    mock_redis.close.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager():
    """Test that buffer works as async context manager."""
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()

    async with RedisEventBuffer(redis_client=mock_redis) as buf:
        assert isinstance(buf, RedisEventBuffer)

    mock_redis.close.assert_called_once()


@pytest.mark.asyncio
async def test_custom_prefixes():
    """Test that custom stream and pubsub prefixes work."""
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()
    mock_redis.publish = AsyncMock()

    buf = RedisEventBuffer(
        redis_client=mock_redis,
        stream_prefix="custom:stream:",
        pubsub_prefix="custom:live:",
    )

    event = _make_event()
    await buf.publish("s1", event)

    # Verify custom prefixes are used
    xadd_call = mock_redis.xadd.call_args
    assert "custom:stream:s1" in xadd_call[0][0]

    publish_call = mock_redis.publish.call_args
    assert "custom:live:s1" in publish_call[0][0]


@pytest.mark.asyncio
async def test_max_stream_len():
    """Test that max_stream_len parameter is passed to XADD."""
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis, max_stream_len=5000)
    event = _make_event()

    await buf.publish("s1", event)

    call_kwargs = mock_redis.xadd.call_args[1]
    assert call_kwargs["maxlen"] == 5000


@pytest.mark.asyncio
async def test_event_serialization():
    """Test that events are properly serialized to JSON."""
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()
    mock_redis.publish = AsyncMock()

    buf = RedisEventBuffer(redis_client=mock_redis)
    event = _make_event()
    event.data = {"key": "value", "nested": {"a": 1}}
    event.metadata = {"meta": "data"}

    await buf.publish("s1", event)

    # Verify the event was serialized
    call_args = mock_redis.xadd.call_args
    payload = call_args[0][1]["event"]

    import json
    parsed = json.loads(payload)
    assert parsed["session_id"] == "s1"
    assert parsed["event_type"] == "tool_call"
    assert parsed["data"]["key"] == "value"
    assert parsed["metadata"]["meta"] == "data"
