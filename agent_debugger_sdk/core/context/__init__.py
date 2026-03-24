"""Thread-local state management for tracing agent execution.

This package provides the TraceContext class for managing async-safe state
during agent execution tracing. It uses contextvars for proper async support
and provides methods for recording decisions, tool results, errors, and
checkpoints.
"""

from .pipeline import configure_event_pipeline, _get_default_event_buffer
from .trace_context import TraceContext
from .vars import get_current_context, get_current_parent_id, get_current_session_id

__all__ = [
    "TraceContext",
    "get_current_context",
    "get_current_session_id",
    "get_current_parent_id",
    "configure_event_pipeline",
    "_get_default_event_buffer",
]
