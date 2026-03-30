"""Tests for FakeEventBuffer and set_event_buffer override."""

from __future__ import annotations

import asyncio

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from tests.helpers.fakes import FakeEventBuffer


def _make_event(session_id: str = "s1", name: str = "ev") -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        event_type=EventType.TOOL_CALL,
        name=name,
    )


@pytest.mark.asyncio
async def test_fake_buffer_records_published_events():
    buf = FakeEventBuffer()
    ev = _make_event("s1", "first")
    await buf.publish("s1", ev)

    assert len(buf.published) == 1
    assert buf.published[0] == ("s1", ev)


@pytest.mark.asyncio
async def test_fake_buffer_get_events_filters_by_session():
    buf = FakeEventBuffer()
    await buf.publish("s1", _make_event("s1", "a"))
    await buf.publish("s2", _make_event("s2", "b"))
    await buf.publish("s1", _make_event("s1", "c"))

    events_s1 = await buf.get_events("s1")
    assert len(events_s1) == 2
    assert events_s1[0].name == "a"
    assert events_s1[1].name == "c"


@pytest.mark.asyncio
async def test_fake_buffer_session_ids():
    buf = FakeEventBuffer()
    await buf.publish("s1", _make_event("s1"))
    await buf.publish("s2", _make_event("s2"))
    await buf.publish("s1", _make_event("s1"))

    ids = await buf.get_session_ids()
    assert set(ids) == {"s1", "s2"}


@pytest.mark.asyncio
async def test_fake_buffer_flush_removes_events():
    buf = FakeEventBuffer()
    await buf.publish("s1", _make_event("s1", "a"))
    await buf.publish("s1", _make_event("s1", "b"))

    flushed = await buf.flush("s1")
    assert len(flushed) == 2
    remaining = await buf.get_events("s1")
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_fake_buffer_subscribe_receives_events():
    buf = FakeEventBuffer()
    queue = await buf.subscribe("s1")

    ev = _make_event("s1", "pub")
    await buf.publish("s1", ev)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.name == "pub"


@pytest.mark.asyncio
async def test_fake_buffer_unsubscribe_stops_events():
    buf = FakeEventBuffer()
    queue = await buf.subscribe("s1")
    await buf.unsubscribe("s1", queue)

    await buf.publish("s1", _make_event("s1", "after"))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)


def test_set_event_buffer_override(reset_event_buffer):
    """set_event_buffer should replace the global singleton."""
    from collector.buffer import get_event_buffer, set_event_buffer

    fake = FakeEventBuffer()
    set_event_buffer(fake)

    result = get_event_buffer()
    assert result is fake


def test_set_event_buffer_none_reset(reset_event_buffer):
    """set_event_buffer(None) should reset so a fresh buffer is created."""
    from collector.buffer import get_event_buffer, set_event_buffer

    set_event_buffer(None)
    buf = get_event_buffer()
    assert isinstance(buf, FakeEventBuffer) is False
