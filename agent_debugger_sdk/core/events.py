"""Data models for agent execution trace events.

This module defines the core event types and data structures used to capture
and analyze agent execution traces. Events form a tree structure where each
event can have a parent, enabling hierarchical trace analysis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from enum import StrEnum
from typing import Any


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a dictionary.

        Converts the event to a JSON-serializable dictionary format,
        handling datetime serialization and nested data structures.

        Returns:
            Dictionary representation of this event
        """
        return {
            "id": self.id,
            "session_id": self.session_id,
            "parent_id": self.parent_id,
            "event_type": str(self.event_type),
            "timestamp": self.timestamp.isoformat(),
            "name": self.name,
            "data": self.data,
            "metadata": self.metadata,
            "importance": self.importance,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tool call event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "tool_name": self.tool_name,
                "arguments": self.arguments,
            }
        )
        return base


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tool result event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "tool_name": self.tool_name,
                "result": self.result,
                "error": self.error,
                "duration_ms": self.duration_ms,
            }
        )
        return base


@dataclass(kw_only=True)
class LLMRequestEvent(TraceEvent):
    """Event representing an LLM API request.

    Captures the details of a request sent to an LLM, including
    the model, messages, available tools, and request settings.

    Attributes:
        event_type: Always EventType.LLM_REQUEST
        model: The model identifier (e.g., "gpt-4", "claude-3-opus")
        messages: The conversation history sent to the LLM
        tools: Tool definitions available to the LLM
        settings: Model settings (temperature, max_tokens, etc.)
    """

    event_type: EventType = EventType.LLM_REQUEST
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the LLM request event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "model": self.model,
                "messages": self.messages,
                "tools": self.tools,
                "settings": self.settings,
            }
        )
        return base


@dataclass(kw_only=True)
class LLMResponseEvent(TraceEvent):
    """Event representing an LLM API response.

    Captures the response from an LLM, including generated content,
    tool calls requested, token usage, and cost information.

    Attributes:
        event_type: Always EventType.LLM_RESPONSE
        model: The model that generated this response
        content: The text content of the response
        tool_calls: Tool calls requested by the LLM
        usage: Token usage (input_tokens, output_tokens)
        cost_usd: Estimated cost in USD
        duration_ms: API call duration in milliseconds
    """

    event_type: EventType = EventType.LLM_RESPONSE
    model: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    cost_usd: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the LLM response event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "model": self.model,
                "content": self.content,
                "tool_calls": self.tool_calls,
                "usage": self.usage,
                "cost_usd": self.cost_usd,
                "duration_ms": self.duration_ms,
            }
        )
        return base


@dataclass(kw_only=True)
class DecisionEvent(TraceEvent):
    """Event representing an agent decision point.

    Captures the reasoning process when an agent makes a decision,
    including the confidence level, supporting evidence, alternatives
    considered, and the chosen action.

    Attributes:
        event_type: Always EventType.DECISION
        reasoning: The agent's reasoning for this decision
        confidence: Confidence level (0.0-1.0)
        evidence: Supporting evidence for the decision
        alternatives: Alternative options that were considered
        chosen_action: The action that was selected
    """

    event_type: EventType = EventType.DECISION
    reasoning: str = ""
    confidence: float = 0.5
    evidence: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    chosen_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the decision event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "reasoning": self.reasoning,
                "confidence": self.confidence,
                "evidence": self.evidence,
                "alternatives": self.alternatives,
                "chosen_action": self.chosen_action,
            }
        )
        return base


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "error_type": self.error_type,
                "error_message": self.error_message,
                "stack_trace": self.stack_trace,
            }
        )
        return base


@dataclass(kw_only=True)
class Session:
    """Dataclass representing a complete agent execution session.

    A session encompasses the entire execution of an agent from start
    to finish, including all events, metrics, and configuration.

    Attributes:
        id: Unique session identifier (UUID)
        agent_name: Name/identifier of the agent
        framework: The agent framework used (pydantic_ai, langchain, autogen)
        started_at: When the session started
        ended_at: When the session ended (None if still running)
        status: Current session status (running, completed, error)
        total_tokens: Total tokens used across all LLM calls
        total_cost_usd: Total estimated cost in USD
        tool_calls: Number of tool calls made
        llm_calls: Number of LLM API calls made
        errors: Number of errors encountered
        config: Agent configuration settings
        tags: Tags for categorizing and filtering sessions
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    framework: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    status: str = "running"
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a dictionary."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "framework": self.framework,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
            "config": self.config,
            "tags": self.tags,
        }


@dataclass(kw_only=True)
class Checkpoint:
    """Dataclass representing a state snapshot for time-travel debugging.

    Checkpoints capture the complete state of an agent at a specific
    point in execution, enabling state restoration and analysis.

    Attributes:
        id: Unique checkpoint identifier (UUID)
        session_id: ID of the session this checkpoint belongs to
        event_id: ID of the event this checkpoint is associated with
        sequence: Sequential number for ordering checkpoints
        state: The agent's state at this point
        memory: The agent's memory/context at this point
        timestamp: When this checkpoint was created
        importance: Relative importance score (0.0-1.0)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""
    sequence: int = 0
    state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    importance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize the checkpoint to a dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "state": self.state,
            "memory": self.memory,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
        }
