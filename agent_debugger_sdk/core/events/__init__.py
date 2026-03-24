"""Core event models for agent execution tracing.

This package contains the base event types and specialized event classes
used throughout the agent debugger SDK.

TEMPORARY: During migration, this package re-exports from both the new
domain modules and the legacy events.py module to maintain backward compatibility.
"""

# Import from new base module
# Import Session and Checkpoint from legacy events module (not yet migrated)
from agent_debugger_sdk.core._legacy_events import (
    EVENT_TYPE_REGISTRY,
    AgentTurnEvent,
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
    Session,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from agent_debugger_sdk.core.events.base import (
    BASE_EVENT_FIELDS,
    EventType,
    RiskLevel,
    SafetyOutcome,
    SessionStatus,
    _serialize_field_value,
)

__all__ = [
    # From base.py
    "BASE_EVENT_FIELDS",
    "_serialize_field_value",
    "EventType",
    "RiskLevel",
    "SafetyOutcome",
    "SessionStatus",
    # From legacy events.py (temporary)
    "TraceEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "LLMRequestEvent",
    "LLMResponseEvent",
    "DecisionEvent",
    "SafetyCheckEvent",
    "RefusalEvent",
    "PolicyViolationEvent",
    "PromptPolicyEvent",
    "AgentTurnEvent",
    "BehaviorAlertEvent",
    "ErrorEvent",
    "Session",
    "Checkpoint",
    "EVENT_TYPE_REGISTRY",
]
