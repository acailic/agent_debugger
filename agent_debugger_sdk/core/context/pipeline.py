"""Event pipeline configuration functions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.emitter import EventBufferLike
    from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent


def _get_default_event_buffer() -> EventBufferLike | None:
    """Resolve the shared event buffer lazily.

    Importing collector modules at SDK import time creates a package-level cycle.
    Resolve the singleton only when a context is instantiated and only when no
    explicit/default buffer has already been configured.
    """
    from .vars import _default_event_buffer

    configured = _default_event_buffer.get()
    if configured is not None:
        return configured

    try:
        from collector.buffer import get_event_buffer
    except ImportError:
        return None
    return get_event_buffer()


def configure_event_pipeline(
    buffer: EventBufferLike | None,
    *,
    persist_event: Callable[[TraceEvent], Awaitable[None]] | None = None,
    persist_checkpoint: Callable[[Checkpoint], Awaitable[None]] | None = None,
    persist_session_start: Callable[[Session], Awaitable[None]] | None = None,
    persist_session_update: Callable[[Session], Awaitable[None]] | None = None,
) -> None:
    """Configure the default event buffer for the event pipeline.

    This connects the SDK's TraceContext to the collector's EventBuffer,
    enabling real-time event streaming and persistence.

    Args:
        buffer: The EventBuffer to use for publishing events, or None to disconnect.
        persist_event: Optional async callback used to persist each emitted event.
        persist_checkpoint: Optional async callback used to persist each checkpoint.
        persist_session_start: Optional async callback used to create a session.
        persist_session_update: Optional async callback used to update a session.
    """
    from .vars import (
        _default_checkpoint_persister,
        _default_event_buffer,
        _default_event_persister,
        _default_session_start_hook,
        _default_session_update_hook,
    )

    _default_event_buffer.set(buffer)
    _default_event_persister.set(persist_event)
    _default_checkpoint_persister.set(persist_checkpoint)
    _default_session_start_hook.set(persist_session_start)
    _default_session_update_hook.set(persist_session_update)
