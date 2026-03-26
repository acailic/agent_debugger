"""ContextVar declarations and accessor functions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.core.emitter import EventBufferLike
    from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent

_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_parent_id: ContextVar[str | None] = ContextVar("current_parent_id", default=None)
_event_sequence: ContextVar[int] = ContextVar("event_sequence", default=0)
# Use Any to avoid circular import with TraceContext
# Type checkers will see the proper type from the return annotation of get_current_context()
_current_context: ContextVar[Any] = ContextVar("current_context", default=None)
_default_event_buffer: ContextVar[EventBufferLike | None] = ContextVar("default_event_buffer", default=None)
_default_event_persister: ContextVar[Callable[[TraceEvent], Awaitable[None]] | None] = ContextVar(
    "default_event_persister",
    default=None,
)
_default_checkpoint_persister: ContextVar[Callable[[Checkpoint], Awaitable[None]] | None] = ContextVar(
    "default_checkpoint_persister",
    default=None,
)
_default_session_start_hook: ContextVar[Callable[[Session], Awaitable[None]] | None] = ContextVar(
    "default_session_start_hook",
    default=None,
)
_default_session_update_hook: ContextVar[Callable[[Session], Awaitable[None]] | None] = ContextVar(
    "default_session_update_hook",
    default=None,
)


def get_current_context():  # noqa: ANN401
    """Get the currently active TraceContext.

    Returns:
        The active TraceContext if within a context manager, None otherwise.
    """
    return _current_context.get()


def get_current_session_id() -> str | None:
    """Get the current session ID.

    Returns:
        The current session ID if within a context, None otherwise.
    """
    return _current_session_id.get()


def get_current_parent_id() -> str | None:
    """Get the current parent event ID.

    Returns:
        The current parent event ID if set, None otherwise.
    """
    return _current_parent_id.get()
