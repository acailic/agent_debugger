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
from agent_debugger_sdk.core.events.registry import (
    EVENT_TYPE_REGISTRY,
    update_event_type_registry,
)
from agent_debugger_sdk.core.events.repair import RepairAttemptEvent, RepairOutcome
from agent_debugger_sdk.core.events.safety import (
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
)
from agent_debugger_sdk.core.events.session import Session
from agent_debugger_sdk.core.events.tools import ToolCallEvent, ToolResultEvent

# Eagerly populate the EVENT_TYPE_REGISTRY with the classes imported above.
# This guarantees class identity: the same class objects used by callers of this
# package are the ones stored in the registry, avoiding isinstance() failures
# that can occur when lazy __missing__-based imports resolve through a different
# path (e.g., editable installs in CI where sys.path ordering differs).
update_event_type_registry(
    {
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
        EventType.REPAIR_ATTEMPT: RepairAttemptEvent,
    }
)

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
    "RepairAttemptEvent",
    "RepairOutcome",
    "Session",
    "Checkpoint",
    "EVENT_TYPE_REGISTRY",
]
