"""Comprehensive unit tests for collector/buffer.py EventBuffer.

Tests cover:
- Public API methods (publish, subscribe, unsubscribe, get_events, get_session_ids, flush)
- Event ordering and storage
- Subscriber notification
- Memory bounds enforcement
- Lock management across event loops
- Singleton behavior (get_event_buffer, set_event_buffer)
- Edge cases (empty sessions, non-existent sessions, multiple subscribers)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.buffer import EventBuffer, get_event_buffer, set_event_buffer

# =============================================================================
# Test Helpers
# =============================================================================


def _make_event(
    session_id: str = "s1",
    name: str = "test",
    event_type: EventType = EventType.TOOL_CALL,
    importance: float = 0.5,
) -> TraceEvent:
    """Factory to create TraceEvent instances for tests."""
    return TraceEvent(
        session_id=session_id,
        parent_id=None,
        event_type=event_type,
        name=name,
        data={},
        metadata={},
        importance=importance,
        upstream_event_ids=[],
    )


# =============================================================================
# Publish and Subscribe Tests
# =============================================================================


@pytest.mark.asyncio
async def test_publish_stores_event():
    """Publish should store event in buffer."""
    buf = EventBuffer()
    event = _make_event(session_id="s1", name="event1")

    await buf.publish("s1", event)

    events = await buf.get_events("s1")
    assert len(events) == 1
    assert events[0].name == "event1"
    assert events[0].session_id == "s1"


@pytest.mark.asyncio
async def test_publish_maintains_ordering():
    """Events should be stored in publish order."""
    buf = EventBuffer()
    event1 = _make_event(session_id="s1", name="first")
    event2 = _make_event(session_id="s1", name="second")
    event3 = _make_event(session_id="s1", name="third")

    await buf.publish("s1", event1)
    await buf.publish("s1", event2)
    await buf.publish("s1", event3)

    events = await buf.get_events("s1")
    assert [e.name for e in events] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_publish_notifies_subscribers():
    """Publish should notify all subscribers."""
    buf = EventBuffer()
    queue1 = await buf.subscribe("s1")
    queue2 = await buf.subscribe("s1")
    event = _make_event(session_id="s1", name="pub_event")

    await buf.publish("s1", event)

    received1 = await queue1.get()
    received2 = await queue2.get()
    assert received1.id == event.id
    assert received2.id == event.id


@pytest.mark.asyncio
async def test_subscribe_creates_queue():
    """Subscribe should create and return a queue."""
    buf = EventBuffer()
    queue = await buf.subscribe("s1")

    assert isinstance(queue, asyncio.Queue)
    assert queue.maxsize == 100


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    """Unsubscribe should remove queue from subscribers."""
    buf = EventBuffer()
    queue = await buf.subscribe("s1")
    await buf.unsubscribe("s1", queue)

    # Publish after unsubscribe
    event = _make_event(session_id="s1", name="after_unsub")
    await buf.publish("s1", event)

    # Queue should not receive event
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_unsubscribe_non_existent_queue_no_error():
    """Unsubscribing a queue that was never subscribed should not raise."""
    buf = EventBuffer()
    other_queue = asyncio.Queue()

    # Should not raise
    await buf.unsubscribe("s1", other_queue)


@pytest.mark.asyncio
async def test_multiple_subscribers_independent():
    """Multiple subscribers should receive independent copies."""
    buf = EventBuffer()
    queue1 = await buf.subscribe("s1")
    queue2 = await buf.subscribe("s1")

    event = _make_event(session_id="s1", name="shared")
    await buf.publish("s1", event)

    # Both queues receive the event
    assert await queue1.get() == event
    assert await queue2.get() == event


# =============================================================================
# Event Retrieval Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_events_returns_copy():
    """get_events should return a copy, not internal list."""
    buf = EventBuffer()
    event = _make_event(session_id="s1", name="original")
    await buf.publish("s1", event)

    events = await buf.get_events("s1")
    events.append(_make_event(session_id="s1", name="fake"))

    # Original buffer should be unchanged
    events_after = await buf.get_events("s1")
    assert len(events_after) == 1
    assert events_after[0].name == "original"


@pytest.mark.asyncio
async def test_get_events_non_existent_session():
    """get_events should return empty list for non-existent session."""
    buf = EventBuffer()
    events = await buf.get_events("nonexistent")
    assert events == []


@pytest.mark.asyncio
async def test_get_events_filters_by_session():
    """Events should be isolated by session ID."""
    buf = EventBuffer()
    await buf.publish("s1", _make_event(session_id="s1", name="s1_event"))
    await buf.publish("s2", _make_event(session_id="s2", name="s2_event"))
    await buf.publish("s1", _make_event(session_id="s1", name="s1_event2"))

    s1_events = await buf.get_events("s1")
    s2_events = await buf.get_events("s2")

    assert len(s1_events) == 2
    assert len(s2_events) == 1
    assert all(e.session_id == "s1" for e in s1_events)
    assert all(e.session_id == "s2" for e in s2_events)


@pytest.mark.asyncio
async def test_get_session_ids():
    """get_session_ids should return all session IDs with events."""
    buf = EventBuffer()
    await buf.publish("s1", _make_event(session_id="s1"))
    await buf.publish("s2", _make_event(session_id="s2"))
    await buf.publish("s3", _make_event(session_id="s3"))

    session_ids = await buf.get_session_ids()
    assert set(session_ids) == {"s1", "s2", "s3"}


@pytest.mark.asyncio
async def test_get_session_ids_empty_buffer():
    """get_session_ids should return empty list when no sessions."""
    buf = EventBuffer()
    session_ids = await buf.get_session_ids()
    assert session_ids == []


# =============================================================================
# Flush Tests
# =============================================================================


@pytest.mark.asyncio
async def test_flush_removes_events():
    """Flush should atomically remove and return all events."""
    buf = EventBuffer()
    event1 = _make_event(session_id="s1", name="e1")
    event2 = _make_event(session_id="s1", name="e2")

    await buf.publish("s1", event1)
    await buf.publish("s1", event2)

    flushed = await buf.flush("s1")
    assert len(flushed) == 2
    assert flushed[0].name == "e1"
    assert flushed[1].name == "e2"

    # Events should be removed
    remaining = await buf.get_events("s1")
    assert remaining == []


@pytest.mark.asyncio
async def test_flush_non_existent_session():
    """Flushing non-existent session should return empty list."""
    buf = EventBuffer()
    flushed = await buf.flush("nonexistent")
    assert flushed == []


@pytest.mark.asyncio
async def test_flush_one_session_does_not_affect_others():
    """Flushing one session should not affect other sessions."""
    buf = EventBuffer()
    await buf.publish("s1", _make_event(session_id="s1", name="s1_e1"))
    await buf.publish("s2", _make_event(session_id="s2", name="s2_e1"))
    await buf.publish("s1", _make_event(session_id="s1", name="s1_e2"))

    await buf.flush("s1")

    assert await buf.get_events("s1") == []
    s2_events = await buf.get_events("s2")
    assert len(s2_events) == 1
    assert s2_events[0].name == "s2_e1"


@pytest.mark.asyncio
async def test_flush_removes_session_activity():
    """Flush should remove session activity timestamp."""
    buf = EventBuffer()
    await buf.publish("s1", _make_event(session_id="s1"))

    # Session should exist
    assert "s1" in buf._session_activity

    await buf.flush("s1")

    # Activity should be removed
    assert "s1" not in buf._session_activity


# =============================================================================
# Memory Bounds Tests
# =============================================================================


@pytest.mark.asyncio
async def test_max_events_per_session_trims_oldest():
    """When exceeding max_events_per_session, oldest events should be trimmed."""
    buf = EventBuffer(max_events_per_session=3)

    # Add 5 events
    for i in range(5):
        await buf.publish("s1", _make_event(session_id="s1", name=f"event{i}"))

    events = await buf.get_events("s1")
    assert len(events) == 3
    # Should keep newest 3
    assert [e.name for e in events] == ["event2", "event3", "event4"]


@pytest.mark.asyncio
async def test_max_events_per_session_exact_boundary():
    """At exact boundary, no trimming should occur."""
    buf = EventBuffer(max_events_per_session=3)

    for i in range(3):
        await buf.publish("s1", _make_event(session_id="s1", name=f"event{i}"))

    events = await buf.get_events("s1")
    assert len(events) == 3
    assert [e.name for e in events] == ["event0", "event1", "event2"]


@pytest.mark.asyncio
async def test_max_sessions_evicts_lru():
    """When exceeding max_sessions, LRU session should be evicted."""
    buf = EventBuffer(max_sessions=2)

    # Create two sessions with different activity times
    older = datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc)

    await buf.publish("old_session", _make_event(session_id="old_session"))
    buf._session_activity["old_session"] = older

    await buf.publish("new_session", _make_event(session_id="new_session"))
    buf._session_activity["new_session"] = newer

    # Add third session - should evict old_session
    await buf.publish("third_session", _make_event(session_id="third_session"))

    session_ids = await buf.get_session_ids()
    assert "old_session" not in session_ids
    assert "new_session" in session_ids
    assert "third_session" in session_ids


@pytest.mark.asyncio
async def test_max_sessions_allows_current_session():
    """Current session should not be evicted even at max capacity."""
    buf = EventBuffer(max_sessions=2)

    await buf.publish("s1", _make_event(session_id="s1"))
    await buf.publish("s2", _make_event(session_id="s2"))

    # s1 should still exist since we're publishing to it
    await buf.publish("s1", _make_event(session_id="s1", name="second"))

    session_ids = await buf.get_session_ids()
    assert set(session_ids) == {"s1", "s2"}


# =============================================================================
# Lock Management Tests
# =============================================================================


@pytest.mark.asyncio
async def test_lock_per_event_loop():
    """Each event loop should get its own lock."""
    buf = EventBuffer()

    # Get lock in current loop
    lock1 = buf._get_lock()
    assert isinstance(lock1, asyncio.Lock)

    # Simulate different loop by changing loop reference
    buf._lock_loop = None
    lock2 = buf._get_lock()

    # Should create new lock for new loop
    assert lock1 is not lock2


@pytest.mark.asyncio
async def test_concurrent_publish_safety():
    """Concurrent publishes should be safe."""
    buf = EventBuffer()
    session_id = "concurrent_session"

    # Publish concurrently
    tasks = [
        buf.publish(session_id, _make_event(session_id=session_id, name=f"event{i}"))
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    events = await buf.get_events(session_id)
    assert len(events) == 10


# =============================================================================
# Subscriber Queue Full Handling
# =============================================================================


@pytest.mark.asyncio
async def test_full_queue_is_removed_from_subscribers():
    """Full queue should be removed and logged as warning."""
    buf = EventBuffer()
    tiny_queue = asyncio.Queue(maxsize=1)
    tiny_queue.put_nowait("blocking")  # Fill the queue

    # Manually add to subscribers (normally done via subscribe)
    buf._queues["s1"] = [tiny_queue]

    event = _make_event(session_id="s1", name="should_fail")
    await buf.publish("s1", event)

    # Full queue should be removed
    assert tiny_queue not in buf._queues["s1"]


# =============================================================================
# Session Activity Tracking
# =============================================================================


@pytest.mark.asyncio
async def test_publish_updates_session_activity():
    """Publish should update session activity timestamp."""
    buf = EventBuffer()
    event = _make_event(session_id="s1")

    before = datetime.now(timezone.utc)
    await buf.publish("s1", event)
    after = datetime.now(timezone.utc)

    assert "s1" in buf._session_activity
    assert before <= buf._session_activity["s1"] <= after


@pytest.mark.asyncio
async def test_activity_updated_on_multiple_publishes():
    """Each publish should update activity timestamp."""
    buf = EventBuffer()

    await buf.publish("s1", _make_event(session_id="s1"))
    first_activity = buf._session_activity["s1"]

    # Small delay to ensure timestamp difference
    await asyncio.sleep(0.01)
    await buf.publish("s1", _make_event(session_id="s1", name="second"))

    second_activity = buf._session_activity["s1"]
    assert second_activity > first_activity


# =============================================================================
# Singleton Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_event_buffer_singleton(reset_event_buffer):
    """get_event_buffer should return same instance on multiple calls."""
    buf1 = get_event_buffer()
    buf2 = get_event_buffer()

    assert buf1 is buf2
    assert isinstance(buf1, EventBuffer)


@pytest.mark.asyncio
async def test_set_event_buffer_override(reset_event_buffer):
    """set_event_buffer should override global singleton."""
    custom_buf = EventBuffer(max_events_per_session=5)
    set_event_buffer(custom_buf)

    result = get_event_buffer()
    assert result is custom_buf
    assert result.max_events_per_session == 5


@pytest.mark.asyncio
async def test_set_event_buffer_none_creates_new(reset_event_buffer):
    """set_event_buffer(None) should reset to create new instance next time."""
    buf1 = get_event_buffer()
    set_event_buffer(None)
    buf2 = get_event_buffer()

    assert buf1 is not buf2
    assert isinstance(buf2, EventBuffer)


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_multiple_sessions_independent():
    """Multiple sessions should maintain independent event streams."""
    buf = EventBuffer()

    await buf.publish("s1", _make_event(session_id="s1", name="s1_a"))
    await buf.publish("s2", _make_event(session_id="s2", name="s2_a"))
    await buf.publish("s1", _make_event(session_id="s1", name="s1_b"))
    await buf.publish("s2", _make_event(session_id="s2", name="s2_b"))

    s1_events = await buf.get_events("s1")
    s2_events = await buf.get_events("s2")

    assert [e.name for e in s1_events] == ["s1_a", "s1_b"]
    assert [e.name for e in s2_events] == ["s2_a", "s2_b"]


@pytest.mark.asyncio
async def test_subscribe_after_events_published():
    """Subscribing after events are published should not deliver old events."""
    buf = EventBuffer()

    # Publish event
    await buf.publish("s1", _make_event(session_id="s1", name="old"))

    # Subscribe after
    queue = await buf.subscribe("s1")

    # Queue should be empty (old events not delivered)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_flush_then_publish():
    """Publishing after flush should create new event list."""
    buf = EventBuffer()

    await buf.publish("s1", _make_event(session_id="s1", name="before"))
    await buf.flush("s1")
    await buf.publish("s1", _make_event(session_id="s1", name="after"))

    events = await buf.get_events("s1")
    assert len(events) == 1
    assert events[0].name == "after"


@pytest.mark.asyncio
async def test_empty_session_in_session_ids():
    """Session with no events should not appear in get_session_ids."""
    buf = EventBuffer()

    # Only subscribe, don't publish
    await buf.subscribe("s1")

    session_ids = await buf.get_session_ids()
    assert "s1" not in session_ids


@pytest.mark.asyncio
async def test_different_event_types():
    """Buffer should handle different event types correctly."""
    buf = EventBuffer()

    await buf.publish("s1", _make_event(session_id="s1", event_type=EventType.LLM_RESPONSE))
    await buf.publish("s1", _make_event(session_id="s1", event_type=EventType.TOOL_CALL))
    await buf.publish("s1", _make_event(session_id="s1", event_type=EventType.DECISION))

    events = await buf.get_events("s1")
    assert events[0].event_type == EventType.LLM_RESPONSE
    assert events[1].event_type == EventType.TOOL_CALL
    assert events[2].event_type == EventType.DECISION
