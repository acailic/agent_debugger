"""Data models for agent execution trace events.

This module defines the core event types and data structures used to capture
and analyze agent execution traces. Events form a tree structure where each
event can have a parent, enabling hierarchical trace analysis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
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
    SAFETY_CHECK = "safety_check"
    REFUSAL = "refusal"
    POLICY_VIOLATION = "policy_violation"
    PROMPT_POLICY = "prompt_policy"
    AGENT_TURN = "agent_turn"
    BEHAVIOR_ALERT = "behavior_alert"


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
            "upstream_event_ids": self.upstream_event_ids,
        }

    @classmethod
    def _typed_field_names(cls) -> set[str]:
        """Return event-specific dataclass fields beyond the shared base payload."""
        return {
            field_info.name
            for field_info in fields(cls)
            if field_info.name not in BASE_EVENT_FIELDS
        }

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
        event_cls = EVENT_TYPE_REGISTRY.get(event_type, cls)
        typed_field_names = event_cls._typed_field_names()
        typed_kwargs = {
            field_name: data[field_name]
            for field_name in typed_field_names
            if field_name in data
        }
        payload = {
            key: value
            for key, value in data.items()
            if key not in typed_field_names
        }
        return event_cls(
            **base_kwargs,
            event_type=event_type,
            data=payload,
            **typed_kwargs,
        )


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
    evidence_event_ids: list[str] = field(default_factory=list)
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
                "evidence_event_ids": self.evidence_event_ids,
                "alternatives": self.alternatives,
                "chosen_action": self.chosen_action,
            }
        )
        return base


@dataclass(kw_only=True)
class SafetyCheckEvent(TraceEvent):
    """Event representing an explicit guard or safety evaluation."""

    event_type: EventType = EventType.SAFETY_CHECK
    policy_name: str = ""
    outcome: str = "pass"
    risk_level: str = "low"
    rationale: str = ""
    blocked_action: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the safety check event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "policy_name": self.policy_name,
                "outcome": self.outcome,
                "risk_level": self.risk_level,
                "rationale": self.rationale,
                "blocked_action": self.blocked_action,
                "evidence": self.evidence,
            }
        )
        return base


@dataclass(kw_only=True)
class RefusalEvent(TraceEvent):
    """Event representing an intentional refusal."""

    event_type: EventType = EventType.REFUSAL
    reason: str = ""
    policy_name: str = ""
    risk_level: str = "medium"
    blocked_action: str | None = None
    safe_alternative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the refusal event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "reason": self.reason,
                "policy_name": self.policy_name,
                "risk_level": self.risk_level,
                "blocked_action": self.blocked_action,
                "safe_alternative": self.safe_alternative,
            }
        )
        return base


@dataclass(kw_only=True)
class PolicyViolationEvent(TraceEvent):
    """Event representing a policy violation or prompt injection signal."""

    event_type: EventType = EventType.POLICY_VIOLATION
    policy_name: str = ""
    severity: str = "medium"
    violation_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the policy violation event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "policy_name": self.policy_name,
                "severity": self.severity,
                "violation_type": self.violation_type,
                "details": self.details,
            }
        )
        return base


@dataclass(kw_only=True)
class PromptPolicyEvent(TraceEvent):
    """Event describing prompt policy or prompt-as-action state."""

    event_type: EventType = EventType.PROMPT_POLICY
    template_id: str = ""
    policy_parameters: dict[str, Any] = field(default_factory=dict)
    speaker: str = ""
    state_summary: str = ""
    goal: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the prompt policy event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "template_id": self.template_id,
                "policy_parameters": self.policy_parameters,
                "speaker": self.speaker,
                "state_summary": self.state_summary,
                "goal": self.goal,
            }
        )
        return base


@dataclass(kw_only=True)
class AgentTurnEvent(TraceEvent):
    """Event representing a single turn in a multi-agent session."""

    event_type: EventType = EventType.AGENT_TURN
    agent_id: str = ""
    speaker: str = ""
    turn_index: int = 0
    goal: str = ""
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the agent turn event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "agent_id": self.agent_id,
                "speaker": self.speaker,
                "turn_index": self.turn_index,
                "goal": self.goal,
                "content": self.content,
            }
        )
        return base


@dataclass(kw_only=True)
class BehaviorAlertEvent(TraceEvent):
    """Event representing detected suspicious or unstable behavior."""

    event_type: EventType = EventType.BEHAVIOR_ALERT
    alert_type: str = ""
    severity: str = "medium"
    signal: str = ""
    related_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the behavior alert event to a dictionary."""
        base = super().to_dict()
        base.update(
            {
                "alert_type": self.alert_type,
                "severity": self.severity,
                "signal": self.signal,
                "related_event_ids": self.related_event_ids,
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
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    status: str = "running"
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0
    replay_value: float = 0.0
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
            "replay_value": self.replay_value,
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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


EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = {
    EventType.TOOL_CALL: ToolCallEvent,
    EventType.TOOL_RESULT: ToolResultEvent,
    EventType.LLM_REQUEST: LLMRequestEvent,
    EventType.LLM_RESPONSE: LLMResponseEvent,
    EventType.DECISION: DecisionEvent,
    EventType.SAFETY_CHECK: SafetyCheckEvent,
    EventType.REFUSAL: RefusalEvent,
    EventType.POLICY_VIOLATION: PolicyViolationEvent,
    EventType.PROMPT_POLICY: PromptPolicyEvent,
    EventType.AGENT_TURN: AgentTurnEvent,
    EventType.BEHAVIOR_ALERT: BehaviorAlertEvent,
    EventType.ERROR: ErrorEvent,
}
