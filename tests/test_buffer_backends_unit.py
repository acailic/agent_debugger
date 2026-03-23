from __future__ import annotations

import asyncio
import builtins
import json
from datetime import UTC
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

import collector
import collector.buffer as memory_buffer_module
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import ToolCallEvent
from agent_debugger_sdk.core.events import TraceEvent
from collector.buffer import EventBuffer
from collector.buffer_redis import RedisEventBuffer


@pytest.mark.asyncio
async def test_event_buffer_publish_flush_and_singleton(monkeypatch):
    event = ToolCallEvent(session_id="memory-session", tool_name="search", arguments={"q": "Belgrade"})
    buffer = EventBuffer()
    queue = await buffer.subscribe("memory-session")

    await buffer.publish("memory-session", event)

    assert await queue.get() == event
    assert buffer.get_events("memory-session") == [event]
    assert buffer.get_session_ids() == ["memory-session"]
    assert buffer.flush("memory-session") == [event]
    assert buffer.get_events("memory-session") == []

    monkeypatch.setattr(memory_buffer_module, "_event_buffer", None)
    singleton_a = memory_buffer_module.get_event_buffer()
    singleton_b = memory_buffer_module.get_event_buffer()
    assert singleton_a is singleton_b


@pytest.mark.asyncio
async def test_event_buffer_removes_full_subscriber_and_handles_missing_unsubscribe():
    event = TraceEvent(session_id="full-session", event_type=EventType.ERROR)
    buffer = EventBuffer(max_events_per_session=2, max_sessions=2)
    full_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    full_queue.put_nowait("occupied")
    buffer._queues["full-session"] = [full_queue]

    await buffer.publish("full-session", event)
    await buffer.unsubscribe("full-session", asyncio.Queue())

    assert buffer._queues["full-session"] == []


def test_event_buffer_enforces_bounds_for_events_and_sessions():
    buffer = EventBuffer(max_events_per_session=2, max_sessions=2)
    older = datetime(2026, 3, 23, 9, 0, tzinfo=UTC)
    newer = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)
    buffer._events["trim-session"] = [
        TraceEvent(session_id="trim-session"),
        TraceEvent(session_id="trim-session"),
    ]
    buffer._events["older-session"] = [TraceEvent(session_id="older-session")]
    buffer._session_activity.update({"older-session": older, "trim-session": newer})

    buffer._enforce_bounds("trim-session")
    assert len(buffer._events["trim-session"]) == 1

    buffer._enforce_bounds("new-session")
    assert "older-session" not in buffer._events


def test_create_buffer_supports_memory_redis_and_invalid_backend():
    memory = collector.create_buffer("memory")
    assert isinstance(memory, EventBuffer)

    with patch("collector.buffer_redis.RedisEventBuffer", return_value="redis-buffer") as redis_cls:
        assert collector.create_buffer("redis", redis_url="redis://example") == "redis-buffer"
        redis_cls.assert_called_once_with(redis_url="redis://example")

    with pytest.raises(ValueError, match="Unknown buffer backend"):
        collector.create_buffer("unsupported")


def test_get_redis_class_handles_import_success_and_failure():
    from collector.buffer_redis import _get_redis_class

    fake_module = SimpleNamespace(Redis=type("FakeRedis", (), {}))
    real_import = builtins.__import__

    def fake_import_success(name, *args, **kwargs):
        if name == "redis.asyncio":
            return fake_module
        return real_import(name, *args, **kwargs)

    def fake_import_failure(name, *args, **kwargs):
        if name == "redis.asyncio":
            raise ImportError("missing redis")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import_success):
        assert _get_redis_class() is fake_module.Redis

    with patch("builtins.__import__", side_effect=fake_import_failure):
        with pytest.raises(ImportError, match="Redis package is required"):
            _get_redis_class()


@pytest.mark.asyncio
async def test_redis_event_buffer_publish_subscribe_unsubscribe_and_close():
    redis_client = SimpleNamespace(
        xadd=AsyncMock(),
        publish=AsyncMock(),
        close=AsyncMock(),
        pubsub=MagicMock(),
    )
    buffer = RedisEventBuffer(redis_client=redis_client)

    async def fake_listen(session_id: str) -> None:
        await asyncio.sleep(60)

    buffer._listen = fake_listen

    queue = await buffer.subscribe("redis-session")
    assert buffer.get_session_ids() == ["redis-session"]
    assert buffer.get_events("redis-session") == []

    event = ToolCallEvent(session_id="redis-session", tool_name="search", arguments={"q": "Belgrade"})
    await buffer.publish("redis-session", event)

    redis_client.xadd.assert_awaited_once()
    redis_client.publish.assert_awaited_once()

    await buffer.unsubscribe("redis-session", asyncio.Queue())
    await buffer.unsubscribe("redis-session", queue)
    assert buffer.get_session_ids() == []

    buffer._pubsub_tasks["other-session"] = asyncio.create_task(asyncio.sleep(60))
    buffer._local_queues["other-session"] = [asyncio.Queue()]
    await buffer.close()
    redis_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_event_buffer_listen_distributes_valid_messages_and_skips_invalid():
    class FakePubSub:
        def __init__(self):
            self.subscribe = AsyncMock()
            self.unsubscribe = AsyncMock()

        async def listen(self):
            valid_event = TraceEvent(
                session_id="listen-session",
                event_type=EventType.ERROR,
                metadata={"source": "redis"},
            )
            yield {"type": "subscribe", "data": "ignored"}
            yield {"type": "message", "data": json.dumps(valid_event.to_dict())}
            yield {"type": "message", "data": "not-json"}

    redis_client = SimpleNamespace(pubsub=MagicMock(return_value=FakePubSub()))
    buffer = RedisEventBuffer(redis_client=redis_client)
    queue: asyncio.Queue = asyncio.Queue()
    buffer._local_queues["listen-session"] = [queue]

    await buffer._listen("listen-session")

    delivered = await queue.get()
    assert delivered.session_id == "listen-session"
    assert delivered.event_type == EventType.ERROR
    redis_client.pubsub.return_value.unsubscribe.assert_awaited_once_with("ad:live:listen-session")


@pytest.mark.asyncio
async def test_redis_event_buffer_context_manager_closes_client():
    redis_client = SimpleNamespace(
        xadd=AsyncMock(),
        publish=AsyncMock(),
        close=AsyncMock(),
        pubsub=MagicMock(),
    )

    async with RedisEventBuffer(redis_client=redis_client) as buffer:
        assert isinstance(buffer, RedisEventBuffer)

    redis_client.close.assert_awaited_once()
