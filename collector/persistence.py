"""Background persistence for trace events.

This module provides a PersistenceManager that periodically flushes
buffered events to storage. For MVP, events are written to JSON files
organized by session.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

if TYPE_CHECKING:
    from .buffer import EventBuffer

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Background writer that flushes buffered events to storage.

    Manages a background task that periodically flushes events from the
    EventBuffer to persistent storage. For MVP, storage is JSON files
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
        self.storage_path = storage_path or Path("./traces")
        self.flush_interval = flush_interval
        self._task: asyncio.Task | None = None
        self._running = False

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
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.storage_path.mkdir, True, True)

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

        For MVP, writes events to JSON files per session:
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
            events: List of BufferedEvent objects to write
        """
        file_path = self.storage_path / f"{session_id}.json"
        lines = []

        for buffered_event in events:
            event_dict = buffered_event.event.to_dict()
            event_dict["_meta"] = {
                "session_id": buffered_event.session_id,
                "sequence": buffered_event.sequence,
                "flushed_at": datetime.now(UTC).isoformat(),
            }
            lines.append(json.dumps(event_dict, ensure_ascii=False))

        async with aiofiles.open(file_path, mode="a", encoding="utf-8") as f:
            await f.write("\n".join(lines) + "\n")
