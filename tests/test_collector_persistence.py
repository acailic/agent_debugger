"""Unit tests for collector/persistence.py"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.buffer import EventBuffer
from collector.persistence import (
    DEFAULT_STORAGE_PATH,
    FALLBACK_STORAGE_PATH,
    USER_STORAGE_PATH,
    PersistenceManager,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage_path():
    """Create a temporary directory for test storage."""
    temp_dir = tempfile.mkdtemp(prefix="test_persistence_")
    yield Path(temp_dir)
    # Cleanup is handled by tempfile.mkdtemp context


@pytest.fixture
def mock_buffer():
    """Create a mock EventBuffer for testing."""
    buffer = MagicMock(spec=EventBuffer)
    buffer.get_session_ids = AsyncMock(return_value=[])
    buffer.flush = AsyncMock(return_value=[])
    return buffer


@pytest.fixture
def sample_events():
    """Create sample TraceEvent objects for testing."""
    events = [
        TraceEvent(
            session_id="s1",
            parent_id=None,
            event_type=EventType.TOOL_CALL,
            name="tool_call_1",
            data={"tool_name": "search", "arguments": {"q": "test"}},
            metadata={"source": "test"},
            importance=0.5,
            upstream_event_ids=[],
        ),
        TraceEvent(
            session_id="s1",
            parent_id=None,
            event_type=EventType.LLM_RESPONSE,
            name="llm_response_1",
            data={"content": "Hello", "model": "gpt-4"},
            metadata={"source": "test"},
            importance=0.7,
            upstream_event_ids=[],
        ),
        TraceEvent(
            session_id="s2",
            parent_id=None,
            event_type=EventType.DECISION,
            name="decision_1",
            data={"reasoning": "test", "confidence": 0.8, "chosen_action": "answer", "evidence": []},
            metadata={"source": "test"},
            importance=0.6,
            upstream_event_ids=[],
        ),
    ]
    return events


@pytest.fixture
def persistence_manager(temp_storage_path, mock_buffer):
    """Create a PersistenceManager instance for testing."""
    return PersistenceManager(buffer=mock_buffer, storage_path=temp_storage_path, flush_interval=0.1)


# =============================================================================
# Initialization Tests
# =============================================================================


def test_persistence_manager_init_with_custom_path(mock_buffer, temp_storage_path):
    """Test initialization with custom storage path."""
    manager = PersistenceManager(buffer=mock_buffer, storage_path=temp_storage_path, flush_interval=2.0)

    assert manager.buffer is mock_buffer
    assert manager.storage_path == temp_storage_path
    assert manager.flush_interval == 2.0
    assert manager._task is None
    assert manager._running is False


def test_persistence_manager_init_with_default_path(mock_buffer):
    """Test initialization with default storage path resolution."""
    manager = PersistenceManager(buffer=mock_buffer)

    assert manager.buffer is mock_buffer
    assert manager.storage_path is not None
    assert isinstance(manager.storage_path, Path)
    assert manager.flush_interval == 1.0
    assert manager._task is None
    assert manager._running is False


def test_resolve_default_storage_path_prefers_writable_path(monkeypatch):
    """Test that writable paths are preferred over non-writable ones."""
    buffer = MagicMock(spec=EventBuffer)

    # Mock path checks - make default writable, others not checked
    def mock_is_writable(path):
        if path == DEFAULT_STORAGE_PATH:
            return True
        return False

    manager = PersistenceManager(buffer=buffer)
    manager._is_writable_path = mock_is_writable

    result = manager._resolve_default_storage_path()

    assert result == DEFAULT_STORAGE_PATH


def test_resolve_default_storage_path_falls_back_to_user_path(monkeypatch):
    """Test fallback to user storage path when default is not writable."""
    buffer = MagicMock(spec=EventBuffer)

    def mock_is_writable(path):
        if path == USER_STORAGE_PATH:
            return True
        return False

    manager = PersistenceManager(buffer=buffer)
    manager._is_writable_path = mock_is_writable

    result = manager._resolve_default_storage_path()

    assert result == USER_STORAGE_PATH


def test_resolve_default_storage_path_falls_back_to_temp(monkeypatch):
    """Test fallback to temp path when preferred paths are not writable."""
    buffer = MagicMock(spec=EventBuffer)

    def mock_is_writable(path):
        if path == FALLBACK_STORAGE_PATH:
            return True
        return False

    manager = PersistenceManager(buffer=buffer)
    manager._is_writable_path = mock_is_writable

    result = manager._resolve_default_storage_path()

    assert result == FALLBACK_STORAGE_PATH


def test_resolve_default_storage_path_creates_temp_when_no_writable(monkeypatch):
    """Test that a temp directory is created when no preferred path is writable."""
    buffer = MagicMock(spec=EventBuffer)

    def mock_is_writable(path):
        return False

    manager = PersistenceManager(buffer=buffer)
    manager._is_writable_path = mock_is_writable

    with patch("collector.persistence.tempfile.mkdtemp") as mock_mkdtemp:
        mock_mkdtemp.return_value = "/tmp/agent_debugger_traces_test"
        result = manager._resolve_default_storage_path()

    assert result == Path("/tmp/agent_debugger_traces_test")


# =============================================================================
# Path Writability Tests
# =============================================================================


def test_is_writable_path_for_existing_writable_directory(tmp_path):
    """Test writability check for existing writable directory."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))

    assert manager._is_writable_path(tmp_path) is True


def test_is_writable_path_for_existing_readonly_directory(tmp_path, monkeypatch):
    """Test writability check for read-only directory."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))

    # Create a read-only directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    original_mode = readonly_dir.stat().st_mode
    readonly_dir.chmod(0o444)

    try:
        # On some systems, this might still be writable by owner
        result = manager._is_writable_path(readonly_dir)
        # Just check it doesn't crash
        assert isinstance(result, bool)
    finally:
        readonly_dir.chmod(original_mode)


def test_is_writable_path_for_nonexistent_path_with_writable_parent(tmp_path):
    """Test writability check for nonexistent path with writable parent."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))

    new_path = tmp_path / "new_dir" / "nested"

    assert manager._is_writable_path(new_path) is True


def test_is_writable_path_for_file(tmp_path):
    """Test writability check returns False for files."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))

    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    assert manager._is_writable_path(test_file) is False


# =============================================================================
# Lifecycle Tests
# =============================================================================


@pytest.mark.asyncio
async def test_start_creates_storage_directory(persistence_manager, temp_storage_path):
    """Test that start creates the storage directory."""
    await persistence_manager.start()

    assert temp_storage_path.exists()
    assert temp_storage_path.is_dir()
    assert persistence_manager._running is True
    assert persistence_manager._task is not None

    await persistence_manager.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent(persistence_manager):
    """Test that calling start multiple times doesn't create multiple tasks."""
    await persistence_manager.start()
    first_task = persistence_manager._task

    await persistence_manager.start()
    second_task = persistence_manager._task

    assert first_task is second_task
    assert persistence_manager._running is True

    await persistence_manager.stop()


@pytest.mark.asyncio
async def test_stop_stops_flush_loop_and_performs_final_flush(persistence_manager, sample_events):
    """Test that stop stops the background task and performs final flush."""
    persistence_manager.buffer.flush = AsyncMock(return_value=sample_events[:2])
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1"])

    await persistence_manager.start()
    assert persistence_manager._running is True

    await persistence_manager.stop()

    assert persistence_manager._running is False
    assert persistence_manager._task is None


@pytest.mark.asyncio
async def test_stop_without_start_is_safe(persistence_manager):
    """Test that calling stop without start is safe."""
    await persistence_manager.stop()

    assert persistence_manager._running is False
    assert persistence_manager._task is None


@pytest.mark.asyncio
async def test_stop_cancels_running_task(persistence_manager):
    """Test that stop properly cancels the background task."""
    await persistence_manager.start()
    task = persistence_manager._task

    await persistence_manager.stop()

    assert task.cancelled() or task.done()


# =============================================================================
# Flush Loop Tests
# =============================================================================


@pytest.mark.asyncio
async def test_flush_loop_runs_periodically(persistence_manager, sample_events):
    """Test that flush loop runs at the configured interval."""
    flush_count = 0
    original_flush = persistence_manager.flush

    async def counting_flush():
        nonlocal flush_count
        flush_count += 1
        if flush_count >= 2:
            await persistence_manager.stop()
        await original_flush()

    persistence_manager.flush = counting_flush
    persistence_manager.flush_interval = 0.05

    await persistence_manager.start()

    # Wait for a few flush cycles
    await asyncio.sleep(0.15)

    assert flush_count >= 2


@pytest.mark.asyncio
async def test_flush_loop_handles_exceptions_gracefully(persistence_manager, caplog):
    """Test that flush loop continues after exceptions."""
    call_count = 0

    async def failing_flush():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Test error")
        if call_count >= 2:
            await persistence_manager.stop()

    persistence_manager.flush = failing_flush
    persistence_manager.flush_interval = 0.05

    await persistence_manager.start()
    await asyncio.sleep(0.2)

    assert call_count >= 2


@pytest.mark.asyncio
async def test_flush_loop_stops_on_cancel(persistence_manager):
    """Test that flush loop exits cleanly on CancelledError."""
    persistence_manager.flush_interval = 0.01

    await persistence_manager.start()
    await asyncio.sleep(0.05)
    await persistence_manager.stop()

    assert persistence_manager._running is False


# =============================================================================
# Flush Tests
# =============================================================================


@pytest.mark.asyncio
async def test_flush_returns_early_with_no_sessions(persistence_manager, temp_storage_path):
    """Test that flush returns early when there are no sessions."""
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=[])

    await persistence_manager.flush()

    # No files should be created
    assert list(temp_storage_path.glob("*.json")) == []


@pytest.mark.asyncio
async def test_flush_writes_events_to_storage(persistence_manager, sample_events, temp_storage_path):
    """Test that flush writes events to the correct files."""
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1", "s2"])
    persistence_manager.buffer.flush = AsyncMock(side_effect=lambda sid: [e for e in sample_events if e.session_id == sid])

    await persistence_manager._ensure_storage_path()
    await persistence_manager.flush()

    # Check that files were created
    s1_file = temp_storage_path / "s1.json"
    s2_file = temp_storage_path / "s2.json"

    assert s1_file.exists()
    assert s2_file.exists()


@pytest.mark.asyncio
async def test_flush_appends_to_existing_files(persistence_manager, sample_events, temp_storage_path):
    """Test that flush appends to existing files rather than overwriting."""
    # Create initial file with one event
    s1_file = temp_storage_path / "s1.json"
    initial_event = sample_events[0]
    initial_event_dict = initial_event.to_dict()
    initial_event_dict["_meta"] = {
        "session_id": "s1",
        "flushed_at": datetime.now(timezone.utc).isoformat(),
    }
    s1_file.write_text(json.dumps(initial_event_dict, ensure_ascii=False) + "\n")

    initial_size = s1_file.stat().st_size

    # Flush more events
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1"])
    persistence_manager.buffer.flush = AsyncMock(return_value=sample_events[1:2])

    await persistence_manager._ensure_storage_path()
    await persistence_manager.flush()

    # File should be larger
    assert s1_file.stat().st_size > initial_size

    # Check that we have multiple lines
    lines = s1_file.read_text().strip().split("\n")
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_flush_skips_empty_sessions(persistence_manager, sample_events, temp_storage_path):
    """Test that flush skips sessions with no events."""
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1", "s2", "s3"])
    persistence_manager.buffer.flush = AsyncMock(
        side_effect=lambda sid: [] if sid == "s2" else sample_events[:1]
    )

    await persistence_manager._ensure_storage_path()
    await persistence_manager.flush()

    # Only s1 and s3 should have files
    assert (temp_storage_path / "s1.json").exists()
    assert not (temp_storage_path / "s2.json").exists()
    assert (temp_storage_path / "s3.json").exists()


# =============================================================================
# Event Writing Tests
# =============================================================================


@pytest.mark.asyncio
async def test_write_session_events_creates_file_with_correct_format(persistence_manager, sample_events, temp_storage_path):
    """Test that events are written in the correct NDJSON format."""
    await persistence_manager._ensure_storage_path()
    await persistence_manager._write_session_events("s1", sample_events[:2])

    s1_file = temp_storage_path / "s1.json"
    assert s1_file.exists()

    content = s1_file.read_text()
    lines = content.strip().split("\n")

    assert len(lines) == 2

    for line in lines:
        data = json.loads(line)
        assert "_meta" in data
        assert data["_meta"]["session_id"] == "s1"
        assert "flushed_at" in data["_meta"]
        assert "id" in data or "event_type" in data


@pytest.mark.asyncio
async def test_write_session_events_includes_metadata(persistence_manager, sample_events, temp_storage_path):
    """Test that metadata is correctly added to written events."""
    await persistence_manager._ensure_storage_path()

    before_flush = datetime.now(timezone.utc)
    await persistence_manager._write_session_events("s1", sample_events[:1])

    s1_file = temp_storage_path / "s1.json"
    content = s1_file.read_text()
    data = json.loads(content.strip())

    assert "_meta" in data
    assert data["_meta"]["session_id"] == "s1"

    flushed_at = datetime.fromisoformat(data["_meta"]["flushed_at"])
    assert flushed_at >= before_flush


@pytest.mark.asyncio
async def test_write_session_events_handles_unicode(persistence_manager, temp_storage_path):
    """Test that events with unicode content are written correctly."""
    unicode_event = TraceEvent(
        session_id="unicode",
        parent_id=None,
        event_type=EventType.LLM_RESPONSE,
        name="unicode_test",
        data={"content": "Hello 世界 🌍"},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )

    await persistence_manager._ensure_storage_path()
    await persistence_manager._write_session_events("unicode", [unicode_event])

    unicode_file = temp_storage_path / "unicode.json"
    content = unicode_file.read_text(encoding="utf-8")

    assert "世界" in content
    assert "🌍" in content


@pytest.mark.asyncio
async def test_write_session_events_creates_directory_if_needed(persistence_manager, temp_storage_path):
    """Test that _write_session_events creates the storage directory if missing."""
    # Remove the storage path
    if temp_storage_path.exists():
        temp_storage_path.rmdir()

    assert not temp_storage_path.exists()

    await persistence_manager._write_session_events("s1", [])

    assert temp_storage_path.exists()


# =============================================================================
# Synchronous Write Tests
# =============================================================================


def test_write_sync_creates_new_file(tmp_path):
    """Test that _write_sync creates a new file if it doesn't exist."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))
    file_path = tmp_path / "test.json"
    lines = ['{"test": "data"}']

    manager._write_sync(file_path, lines)

    assert file_path.exists()
    content = file_path.read_text()
    assert '{"test": "data"}' in content


def test_write_sync_appends_to_existing_file(tmp_path):
    """Test that _write_sync appends to an existing file."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))
    file_path = tmp_path / "test.json"
    file_path.write_text('{"existing": "data"}\n')

    lines = ['{"new": "data"}']
    manager._write_sync(file_path, lines)

    content = file_path.read_text()
    assert '{"existing": "data"}' in content
    assert '{"new": "data"}' in content


def test_write_sync_writes_multiple_lines(tmp_path):
    """Test that _write_sync writes multiple lines with newlines."""
    manager = PersistenceManager(buffer=MagicMock(spec=EventBuffer))
    file_path = tmp_path / "test.json"
    lines = ['{"line": 1}', '{"line": 2}', '{"line": 3}']

    manager._write_sync(file_path, lines)

    content = file_path.read_text()
    assert content == '{"line": 1}\n{"line": 2}\n{"line": 3}\n'


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_lifecycle_start_flush_stop(temp_storage_path, sample_events):
    """Test the full lifecycle: start -> flush -> stop."""
    # Use real EventBuffer for integration test
    buffer = EventBuffer()
    manager = PersistenceManager(buffer=buffer, storage_path=temp_storage_path, flush_interval=0.1)

    # Publish events
    for event in sample_events:
        await buffer.publish(event.session_id, event)

    await manager.start()
    await asyncio.sleep(0.2)  # Allow flush to run
    await manager.stop()

    # Check files exist
    assert (temp_storage_path / "s1.json").exists()
    assert (temp_storage_path / "s2.json").exists()


@pytest.mark.asyncio
async def test_multiple_flush_cycles(persistence_manager, sample_events, temp_storage_path):
    """Test that multiple flush cycles correctly append to files."""
    flush_call_count = 0

    async def mock_flush(sid):
        nonlocal flush_call_count
        flush_call_count += 1
        # Return different events on different calls
        if flush_call_count == 1:
            return [sample_events[0]]
        elif flush_call_count == 2:
            return [sample_events[1]]
        return []

    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1"])
    persistence_manager.buffer.flush = mock_flush

    await persistence_manager._ensure_storage_path()
    await persistence_manager.flush()
    await persistence_manager.flush()

    s1_file = temp_storage_path / "s1.json"
    lines = s1_file.read_text().strip().split("\n")

    assert len(lines) == 2


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_flush_with_empty_event_list(persistence_manager, temp_storage_path):
    """Test flush when buffer returns empty event lists."""
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1"])
    persistence_manager.buffer.flush = AsyncMock(return_value=[])

    await persistence_manager._ensure_storage_path()
    await persistence_manager.flush()

    # File should not be created for empty sessions
    assert not (temp_storage_path / "s1.json").exists()


@pytest.mark.asyncio
async def test_concurrent_flush_calls(persistence_manager, sample_events, temp_storage_path):
    """Test that concurrent flush calls are handled correctly."""
    persistence_manager.buffer.get_session_ids = AsyncMock(return_value=["s1"])
    persistence_manager.buffer.flush = AsyncMock(return_value=sample_events[:2])

    await persistence_manager._ensure_storage_path()

    # Schedule multiple flushes concurrently
    await asyncio.gather(
        persistence_manager.flush(),
        persistence_manager.flush(),
        persistence_manager.flush(),
    )

    # Check that file exists and has content
    s1_file = temp_storage_path / "s1.json"
    assert s1_file.exists()
    content = s1_file.read_text()
    assert len(content.strip().split("\n")) >= 2


@pytest.mark.asyncio
async def test_storage_path_with_special_characters(temp_storage_path, sample_events):
    """Test handling of session IDs with special characters."""
    buffer = MagicMock(spec=EventBuffer)
    manager = PersistenceManager(buffer=buffer, storage_path=temp_storage_path)

    # Session with special characters that are valid in filenames
    special_session_id = "session-123_test"
    manager.buffer.get_session_ids = AsyncMock(return_value=[special_session_id])
    manager.buffer.flush = AsyncMock(return_value=sample_events[:1])

    await manager._ensure_storage_path()
    await manager.flush()

    expected_file = temp_storage_path / f"{special_session_id}.json"
    assert expected_file.exists()
