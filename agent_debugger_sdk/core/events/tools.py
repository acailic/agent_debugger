"""Tool call and result events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, TraceEvent


@dataclass(kw_only=True)
class ToolCallEvent(TraceEvent):
    """Event representing a tool/function call by the agent.

    Captures when an agent invokes a tool, including the tool name
    and arguments passed. The parent_id should link to the LLM response
    that triggered this call.

    Attributes:
        event_type: Always EventType.TOOL_CALL
        tool_name: Name of the tool being called
        arguments: Arguments passed to the tool
    """

    event_type: EventType = EventType.TOOL_CALL
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class ToolResultEvent(TraceEvent):
    """Event representing the result of a tool call.

    Captures the outcome of a tool execution, including success/failure
    status, duration, and any returned data. Should be paired with
    a preceding ToolCallEvent.

    Attributes:
        event_type: Always EventType.TOOL_RESULT
        tool_name: Name of the tool that was called
        result: The return value from the tool
        error: Error message if the tool call failed
        duration_ms: Execution time in milliseconds
    """

    event_type: EventType = EventType.TOOL_RESULT
    tool_name: str = ""
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
