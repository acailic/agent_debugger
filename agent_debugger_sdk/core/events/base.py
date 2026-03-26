"""Base data models for agent execution trace events.

This module defines the core event types and base TraceEvent class used to capture
and analyze agent execution traces. Events form a tree structure where each
event can have a parent, enabling hierarchical trace analysis.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:

    class StrEnum(str, Enum):
        """Compatibility shim for StrEnum in Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


class EventType(StrEnum):
    """Enumeration of all trace event types.

    These represent the different phases and actions during agent execution:
    - AGENT_START/END: Session lifecycle events
    - TOOL_CALL/RESULT: Tool execution events
    - LLM_REQUEST/RESPONSE: LLM API interaction events
    - DECISION: Agent decision points with reasoning
    - ERROR: Error occurrences during execution
    - CHECKPOINT: State snapshots for time-travel debugging
    """

    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    DECISION = "decision"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    SAFETY_CHECK = "safety_check"
    REFUSAL = "refusal"
    POLICY_VIOLATION = "policy_violation"
    PROMPT_POLICY = "prompt_policy"
    AGENT_TURN = "agent_turn"
    BEHAVIOR_ALERT = "behavior_alert"


class SessionStatus(StrEnum):
    """Session lifecycle status values."""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class RiskLevel(StrEnum):
    """Shared risk/severity labels across domain events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyOutcome(StrEnum):
    """Explicit outcome labels for safety checks."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    BLOCK = "block"


BASE_EVENT_FIELDS = {
    "id",
    "session_id",
    "parent_id",
    "event_type",
    "timestamp",
    "name",
    "data",
    "metadata",
    "importance",
    "upstream_event_ids",
}


def _serialize_field_value(value: Any) -> Any:
    """Convert dataclass field values into JSON-serializable payloads."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value)
    if isinstance(value, list):
        return [_serialize_field_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_field_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_field_value(item) for key, item in value.items()}
    return value


@dataclass(kw_only=True)
class TraceEvent:
    """Base dataclass for all trace events.

    All events in the trace hierarchy inherit from this class. Events form
    a tree structure via the parent_id field, enabling hierarchical analysis
    of agent execution.

    Attributes:
        id: Unique identifier for this event (auto-generated UUID)
        session_id: ID of the session this event belongs to
        parent_id: ID of the parent event, if any (for hierarchical traces)
        event_type: Type of this event
        timestamp: When this event occurred (auto-generated)
        name: Human-readable name for this event
        data: Event-specific data payload
        metadata: Additional metadata about the event
        importance: Relative importance score (0.0-1.0) for filtering/display
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    parent_id: str | None = None
    event_type: EventType = EventType.AGENT_START
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    upstream_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a dictionary.

        Converts the event to a JSON-serializable dictionary format,
        handling datetime serialization and nested data structures.

        Returns:
            Dictionary representation of this event
        """
        return {field_info.name: _serialize_field_value(getattr(self, field_info.name)) for field_info in fields(self)}

    @classmethod
    def _typed_field_names(cls) -> set[str]:
        """Return event-specific dataclass fields beyond the shared base payload."""
        return {field_info.name for field_info in fields(cls) if field_info.name not in BASE_EVENT_FIELDS}

    def to_storage_data(self) -> dict[str, Any]:
        """Merge event-specific fields into the storage payload."""
        payload = dict(self.data)
        for field_name in self._typed_field_names():
            payload[field_name] = getattr(self, field_name)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceEvent:
        """Deserialize a dictionary to a TraceEvent.

        Converts a dictionary back to a TraceEvent, handling
        datetime deserialization and EventType enum conversion.

        Args:
            data: Dictionary representation of an event

        Returns:
            TraceEvent instance
        """
        # Handle timestamp deserialization
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        # Handle EventType deserialization
        if isinstance(data.get("event_type"), str):
            data["event_type"] = EventType(data["event_type"])

        return cls(**data)

    @classmethod
    def from_data(
        cls,
        event_type: EventType,
        base_kwargs: dict[str, Any],
        data: dict[str, Any],
    ) -> TraceEvent:
        """Build the typed event instance for the given event_type."""
        from agent_debugger_sdk.core.events import EVENT_TYPE_REGISTRY

        # Use try/except to trigger lazy loading via __missing__
        try:
            event_cls = EVENT_TYPE_REGISTRY[event_type]
        except KeyError:
            # Event type not in registry, use base TraceEvent class
            event_cls = cls

        typed_field_names = event_cls._typed_field_names()
        typed_kwargs = {field_name: data[field_name] for field_name in typed_field_names if field_name in data}
        payload = {key: value for key, value in data.items() if key not in typed_field_names}
        return event_cls(
            **base_kwargs,
            event_type=event_type,
            data=payload,
            **typed_kwargs,
        )
