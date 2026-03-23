"""Tests for buffer interface compliance."""
import asyncio

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent


def _make_event(session_id: str = "s1", name: str = "test") -> TraceEvent:
    """Create a test event."""
    return TraceEvent(
        session_id=session_id,
        parent_id=None,
        event_type=EventType.TOOL_CALL,
        name=name,
        data={},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )


def test_event_buffer_is_subclass_of_base():
    """Test that EventBuffer is a subclass of BufferBase."""
    from collector.buffer import EventBuffer
    from collector.buffer_base import BufferBase

    assert issubclass(EventBuffer, BufferBase)


@pytest.mark.asyncio
async def test_publish_and_subscribe():
    """Test basic publish and subscribe functionality."""
    from collector.buffer import EventBuffer

    buf = EventBuffer()
    queue = await buf.subscribe("s1")
    event = _make_event()
    await buf.publish("s1", event)
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.id == event.id
    await buf.unsubscribe("s1", queue)


@pytest.mark.asyncio
async def test_get_events():
    """Test retrieving stored events."""
    from collector.buffer import EventBuffer

    buf = EventBuffer()
    event1 = _make_event(session_id="s1", name="event1")
    event2 = _make_event(session_id="s1", name="event2")

    await buf.publish("s1", event1)
    await buf.publish("s1", event2)

    events = await buf.get_events("s1")
    assert len(events) == 2
    assert events[0].name == "event1"
    assert events[1].name == "event2"


@pytest.mark.asyncio
async def test_get_session_ids():
    """Test retrieving session IDs."""
    from collector.buffer import EventBuffer

    buf = EventBuffer()
    await buf.publish("s1", _make_event(session_id="s1"))
    await buf.publish("s2", _make_event(session_id="s2"))

    session_ids = await buf.get_session_ids()
    assert set(session_ids) == {"s1", "s2"}
