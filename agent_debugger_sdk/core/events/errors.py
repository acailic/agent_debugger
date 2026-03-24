"""Error events."""

from dataclasses import dataclass

from .base import EventType, TraceEvent


@dataclass(kw_only=True)
class ErrorEvent(TraceEvent):
    """Event representing an error during agent execution.

    Captures error details including type, message, and optional
    stack trace for debugging purposes.

    Attributes:
        event_type: Always EventType.ERROR
        error_type: The exception class name or error category
        error_message: Human-readable error message
        stack_trace: Optional stack trace for debugging
    """

    event_type: EventType = EventType.ERROR
    error_type: str = ""
    error_message: str = ""
    stack_trace: str | None = None
