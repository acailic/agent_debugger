"""Background persistence for trace events.

This module provides a PersistenceManager that periodically flushes
buffered events to storage. In this repo it remains a lightweight
NDJSON fallback for file-based persistence and debugging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from contextlib import suppress
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .buffer import EventBuffer

logger = logging.getLogger(__name__)
DEFAULT_STORAGE_PATH = Path("./traces")
USER_STORAGE_PATH = Path.home() / ".local" / "share" / "agent_debugger" / "traces"
FALLBACK_STORAGE_PATH = Path(tempfile.gettempdir()) / "agent_debugger_traces"


class PersistenceManager:
    """Background writer that flushes buffered events to storage.

    Manages a background task that periodically flushes events from the
    EventBuffer to persistent storage. Storage is newline-delimited JSON
    organized by session.

    Attributes:
        buffer: The EventBuffer to flush events from
        storage_path: Base directory for trace files
        flush_interval: Seconds between flush operations
    """

    def __init__(
        self,
        buffer: EventBuffer,
        storage_path: Path | None = None,
        flush_interval: float = 1.0,
    ):
        """Initialize the persistence manager.

        Args:
            buffer: The EventBuffer instance to read events from
            storage_path: Directory to store trace files (default: ./traces)
            flush_interval: How often to flush in seconds (default: 1.0)
        """
        self.buffer = buffer
        self.storage_path = storage_path or self._resolve_default_storage_path()
        self.flush_interval = flush_interval
        self._task: asyncio.Task | None = None
        self._running = False

    def _resolve_default_storage_path(self) -> Path:
        """Choose a writable default storage path for local trace files."""
        for candidate in (DEFAULT_STORAGE_PATH, USER_STORAGE_PATH, FALLBACK_STORAGE_PATH):
            if self._is_writable_path(candidate):
                if candidate != DEFAULT_STORAGE_PATH:
                    logger.warning("Default trace path %s is not writable; using %s", DEFAULT_STORAGE_PATH, candidate)
                return candidate

        temp_path = Path(tempfile.mkdtemp(prefix="agent_debugger_traces_"))
        logger.warning("No preferred trace path is writable; using %s", temp_path)
        return temp_path

    def _is_writable_path(self, path: Path) -> bool:
        """Return whether a path can be created in or appended to."""
        if path.exists():
            return path.is_dir() and os.access(path, os.W_OK | os.X_OK)

        parent = path.parent if path.parent != Path("") else Path(".")
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        return parent.exists() and os.access(parent, os.W_OK | os.X_OK)

    async def start(self) -> None:
        """Start the background flush task."""
        if self._running:
            return

        self._running = True
        await self._ensure_storage_path()
        self._task = asyncio.create_task(self._flush_loop())
        logger.info(f"PersistenceManager started (interval={self.flush_interval}s, path={self.storage_path})")

    async def stop(self) -> None:
        """Stop the background task and perform final flush."""
        self._running = False

        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        await self.flush()
        logger.info("PersistenceManager stopped")

    async def _ensure_storage_path(self) -> None:
        """Create storage directory if it doesn't exist."""
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def _flush_loop(self) -> None:
        """Internal flush loop that runs periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in flush loop: {e}", exc_info=True)

    async def flush(self) -> None:
        """Flush all pending events to storage.

        Writes events to JSON files per session:
        - Each session gets its own file: {storage_path}/{session_id}.json
        - Files are appended to on each flush
        - Events are written as newline-delimited JSON (NDJSON)
        """
        session_ids = await self.buffer.get_session_ids()

        if not session_ids:
            return

        for session_id in session_ids:
            events = await self.buffer.flush(session_id)
            if not events:
                continue

            await self._write_session_events(session_id, events)
            logger.debug(f"Flushed {len(events)} events for session {session_id}")

    async def _write_session_events(
        self,
        session_id: str,
        events: list,
    ) -> None:
        """Write events to a session's JSON file.

        Args:
            session_id: The session identifier
            events: List of TraceEvent objects to write
        """
        await self._ensure_storage_path()
        file_path = self.storage_path / f"{session_id}.json"
        lines = []

        for event in events:
            event_dict = event.to_dict()
            event_dict["_meta"] = {
                "session_id": session_id,
                "flushed_at": datetime.now(UTC).isoformat(),
            }
            lines.append(json.dumps(event_dict, ensure_ascii=False))

        with file_path.open(mode="a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
