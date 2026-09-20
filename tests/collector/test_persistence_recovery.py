"""Regression coverage for recoverable NDJSON delivery failures."""

import asyncio
import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.buffer import EventBuffer
from collector.persistence import PersistenceManager


def event(name):
    return TraceEvent(session_id="session", event_type=EventType.ERROR, name=name)


def stored_ids(tmp_path):
    return [json.loads(line)["id"] for line in (tmp_path / "session.json").read_text().splitlines()]


@pytest.mark.asyncio
async def test_failed_batch_retries_before_new_events_without_republishing(tmp_path, monkeypatch):
    buffer = EventBuffer()
    manager = PersistenceManager(buffer, tmp_path)
    old, new = event("old"), event("new")
    subscriber = await buffer.subscribe("session")
    await buffer.publish("session", old)
    write = manager._write_sync
    attempts = 0

    def fail_once(path, lines):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("disk unavailable")
        write(path, lines)

    monkeypatch.setattr(manager, "_write_sync", fail_once)
    with pytest.raises(OSError, match="disk unavailable"):
        await manager.flush()
    await buffer.publish("session", new)
    await manager.flush()
    await manager.flush()

    assert stored_ids(tmp_path) == [old.id, new.id]
    assert [subscriber.get_nowait().id, subscriber.get_nowait().id] == [old.id, new.id]
    assert subscriber.empty()


@pytest.mark.asyncio
async def test_partial_append_is_rolled_back_before_retry(tmp_path, monkeypatch):
    buffer = EventBuffer()
    manager = PersistenceManager(buffer, tmp_path)
    existing, old, new = event("existing"), event("old 世界"), event("new")
    await buffer.publish("session", existing)
    await manager.flush()
    original_bytes = (tmp_path / "session.json").read_bytes()
    await buffer.publish("session", old)
    original_open = Path.open
    failed = False

    class PartialAppend:
        def __init__(self, file):
            self.file = file

        def __getattr__(self, name):
            return getattr(self.file, name)

        def write(self, data):
            self.file.write(data[: len(data) // 2])
            raise OSError("disk full after partial append")

    @contextmanager
    def partial_open(path, mode="r", *args, **kwargs):
        nonlocal failed
        with original_open(path, mode, *args, **kwargs) as file:
            if "a" in mode and not failed:
                failed = True
                yield PartialAppend(file)
            else:
                yield file

    monkeypatch.setattr(Path, "open", partial_open)
    with pytest.raises(OSError, match="disk full after partial append"):
        await manager.flush()
    assert (tmp_path / "session.json").read_bytes() == original_bytes

    await buffer.publish("session", new)
    await manager.flush()

    assert stored_ids(tmp_path) == [existing.id, old.id, new.id]


@pytest.mark.asyncio
async def test_concurrent_flushes_preserve_order_and_write_once(tmp_path, monkeypatch):
    buffer = EventBuffer()
    manager = PersistenceManager(buffer, tmp_path)
    old, new = event("old"), event("new")
    await buffer.publish("session", old)
    started, release = asyncio.Event(), asyncio.Event()
    write = manager._write_session_events
    calls = []

    async def blocked_write(session_id, events):
        calls.append([item.id for item in events])
        if len(calls) == 1:
            started.set()
            await release.wait()
        await write(session_id, events)

    monkeypatch.setattr(manager, "_write_session_events", blocked_write)
    first = asyncio.create_task(manager.flush())
    try:
        await asyncio.wait_for(started.wait(), 2)
        await buffer.publish("session", new)
        second = asyncio.create_task(manager.flush())
    finally:
        release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 2)

    assert calls == [[old.id], [new.id]]
    assert stored_ids(tmp_path) == [old.id, new.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("shutdown", [False, True])
async def test_cancellation_waits_for_existing_disk_write_without_duplicates(tmp_path, monkeypatch, shutdown):
    buffer = EventBuffer()
    manager = PersistenceManager(buffer, tmp_path, flush_interval=0.001)
    old, new = event("old"), event("new")
    await buffer.publish("session", old)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    write = manager._write_sync
    calls = 0

    def blocked_write(path, lines):
        nonlocal calls
        calls += 1
        if calls == 1:
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=5):
                raise TimeoutError("test did not release disk write")
        write(path, lines)

    monkeypatch.setattr(manager, "_write_sync", blocked_write)
    if shutdown:
        await manager.start()
    else:
        flush = asyncio.create_task(manager.flush())
    try:
        await asyncio.wait_for(started.wait(), 2)
        if not shutdown:
            flush.cancel()
            with pytest.raises(asyncio.CancelledError):
                await flush
        await buffer.publish("session", new)
        finished = asyncio.create_task(manager.stop() if shutdown else manager.flush())
        # Allow shutdown/retry to reach the pending writer while it is blocked.
        await asyncio.sleep(0)
        assert not finished.done()
    finally:
        release.set()
    await asyncio.wait_for(finished, 2)
    await manager.flush()

    assert calls == 2
    assert stored_ids(tmp_path) == [old.id, new.id]
