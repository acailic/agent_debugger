"""Core event models for agent execution tracing.

This package contains the base event types and specialized event classes
used throughout the agent debugger SDK.
"""

# Import from base
# Import from domain modules
from agent_debugger_sdk.core.events.agent import AgentTurnEvent, BehaviorAlertEvent
from agent_debugger_sdk.core.events.base import (
    BASE_EVENT_FIELDS,
    EventType,
    RiskLevel,
    SafetyOutcome,
    SessionStatus,
    TraceEvent,
    _serialize_field_value,
)
from agent_debugger_sdk.core.events.checkpoint import Checkpoint
from agent_debugger_sdk.core.events.decisions import DecisionEvent
from agent_debugger_sdk.core.events.errors import ErrorEvent
from agent_debugger_sdk.core.events.llm import LLMRequestEvent, LLMResponseEvent
from agent_debugger_sdk.core.events.registry import EVENT_TYPE_REGISTRY
from agent_debugger_sdk.core.events.safety import (
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
)
from agent_debugger_sdk.core.events.session import Session
from agent_debugger_sdk.core.events.tools import ToolCallEvent, ToolResultEvent

# Force populate the EVENT_TYPE_REGISTRY to ensure class identity consistency
# when modules are imported in different orders (e.g., in tests)
# This must happen AFTER all event classes are imported
try:
    # Access via dict key to trigger __missing__ and populate the registry
    _ = EVENT_TYPE_REGISTRY[EventType.TOOL_CALL]
except KeyError:
    # If TOOL_CALL is not registered yet, try another event type
    pass

__all__ = [
    # From base.py
    "BASE_EVENT_FIELDS",
    "_serialize_field_value",
    "EventType",
    "RiskLevel",
    "SafetyOutcome",
    "SessionStatus",
    "TraceEvent",
    # From domain modules
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
