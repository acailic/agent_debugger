"""Unit tests for PersistenceManager branch behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from collector.persistence import DEFAULT_STORAGE_PATH
from collector.persistence import FALLBACK_STORAGE_PATH
from collector.persistence import PersistenceManager
from collector.persistence import USER_STORAGE_PATH


class StubBuffer:
    def __init__(self, session_ids=None, events_by_session=None):
        self._session_ids = session_ids or []
        self._events_by_session = events_by_session or {}

    def get_session_ids(self):
        return list(self._session_ids)

    def flush(self, session_id):
        return self._events_by_session.get(session_id, [])


def test_resolve_default_storage_path_prefers_first_writable_path():
    manager = PersistenceManager(StubBuffer(), storage_path=Path("/tmp/custom"))

    with patch.object(
        PersistenceManager,
        "_is_writable_path",
        side_effect=lambda path: path == USER_STORAGE_PATH,
    ):
        chosen = manager._resolve_default_storage_path()

    assert chosen == USER_STORAGE_PATH


def test_resolve_default_storage_path_falls_back_to_temp_dir_when_none_writable():
    manager = PersistenceManager(StubBuffer(), storage_path=Path("/tmp/custom"))

    with patch.object(PersistenceManager, "_is_writable_path", return_value=False), patch(
        "collector.persistence.tempfile.mkdtemp",
        return_value="/tmp/generated-traces",
    ):
        chosen = manager._resolve_default_storage_path()

    assert chosen == Path("/tmp/generated-traces")


def test_is_writable_path_checks_existing_directory_and_missing_parent():
    manager = PersistenceManager(StubBuffer(), storage_path=Path("/tmp/custom"))

    with patch("collector.persistence.os.access", return_value=True):
        assert manager._is_writable_path(DEFAULT_STORAGE_PATH) is True

    missing = Path("/tmp/example/a/b/c")
    existing_parent = Path("/tmp/example")
    with patch.object(Path, "exists", autospec=True, side_effect=lambda self: self == existing_parent), patch(
        "collector.persistence.os.access",
        return_value=True,
    ):
        assert manager._is_writable_path(missing) is True


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_flushes_and_clears_task(tmp_path):
    manager = PersistenceManager(StubBuffer(), storage_path=tmp_path, flush_interval=3600)

    with patch.object(manager, "_ensure_storage_path", new=AsyncMock()) as ensure_path, patch.object(
        manager,
        "flush",
        new=AsyncMock(),
    ) as flush:
        await manager.start()
        first_task = manager._task
        await manager.start()

        assert manager._running is True
        assert manager._task is first_task
        ensure_path.assert_awaited_once()

        await manager.stop()

    assert manager._running is False
    assert manager._task is None
    flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_flush_skips_empty_buffers_and_writes_non_empty_sessions(tmp_path):
    buffer = StubBuffer(
        session_ids=["session-a", "session-b"],
        events_by_session={"session-a": [SimpleNamespace(to_dict=lambda: {"id": "1"})], "session-b": []},
    )
    manager = PersistenceManager(buffer, storage_path=tmp_path)

    with patch.object(manager, "_write_session_events", new=AsyncMock()) as writer:
        await manager.flush()

    writer.assert_awaited_once()
    assert writer.await_args.args[0] == "session-a"


@pytest.mark.asyncio
async def test_flush_returns_early_without_session_ids(tmp_path):
    manager = PersistenceManager(StubBuffer(session_ids=[]), storage_path=tmp_path)

    with patch.object(manager, "_write_session_events", new=AsyncMock()) as writer:
        await manager.flush()

    writer.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_loop_handles_transient_errors_then_cancellation(tmp_path):
    manager = PersistenceManager(StubBuffer(), storage_path=tmp_path, flush_interval=0)
    manager._running = True
    calls = 0

    async def flaky_flush():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        manager._running = False
        raise asyncio.CancelledError

    with patch("collector.persistence.asyncio.sleep", new=AsyncMock()), patch.object(
        manager, "flush", side_effect=flaky_flush
    ):
        with pytest.raises(asyncio.CancelledError):
            await manager._flush_loop()

    assert calls == 2
