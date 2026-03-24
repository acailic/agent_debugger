"""Core event models for agent execution tracing.

This package contains the base event types and specialized event classes
used throughout the agent debugger SDK.

TEMPORARY: During migration, this package re-exports from both the new
base.py module and the old events.py module to maintain backward compatibility.
"""

# Import from new base module
from agent_debugger_sdk.core.events.base import (
    BASE_EVENT_FIELDS,
    EventType,
    RiskLevel,
    SafetyOutcome,
    SessionStatus,
    TraceEvent as BaseTraceEvent,
    _serialize_field_value,
)

# Try to import from old events.py for backward compatibility
# This will be removed once all event types are migrated
try:
    # Import from the sibling events.py file (not this package)
    import sys
    from pathlib import Path

    # Add the parent directory to sys.path temporarily
    parent_dir = str(Path(__file__).parent)
    events_module_path = Path(parent_dir) / "events.py"

    if events_module_path.exists():
        # Load the old events.py module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_old_events",
            str(events_module_path)
        )
        old_events = importlib.util.module_from_spec(spec)
        sys.modules["_old_events"] = old_events
        spec.loader.exec_module(old_events)

        # Re-export all the old classes
        ToolCallEvent = old_events.ToolCallEvent
        ToolResultEvent = old_events.ToolResultEvent
        LLMRequestEvent = old_events.LLMRequestEvent
        LLMResponseEvent = old_events.LLMResponseEvent
        DecisionEvent = old_events.DecisionEvent
        SafetyCheckEvent = old_events.SafetyCheckEvent
        RefusalEvent = old_events.RefusalEvent
        PolicyViolationEvent = old_events.PolicyViolationEvent
        PromptPolicyEvent = old_events.PromptPolicyEvent
        AgentTurnEvent = old_events.AgentTurnEvent
        BehaviorAlertEvent = old_events.BehaviorAlertEvent
        ErrorEvent = old_events.ErrorEvent
        Session = old_events.Session
        Checkpoint = old_events.Checkpoint
        EVENT_TYPE_REGISTRY = old_events.EVENT_TYPE_REGISTRY
        # Use TraceEvent from old events to maintain compatibility
        TraceEvent = old_events.TraceEvent
    else:
        # Fall back to base module if events.py doesn't exist
        TraceEvent = BaseTraceEvent
        ToolCallEvent = None
        ToolResultEvent = None
        LLMRequestEvent = None
        LLMResponseEvent = None
        DecisionEvent = None
        SafetyCheckEvent = None
        RefusalEvent = None
        PolicyViolationEvent = None
        PromptPolicyEvent = None
        AgentTurnEvent = None
        BehaviorAlertEvent = None
        ErrorEvent = None
        Session = None
        Checkpoint = None
        EVENT_TYPE_REGISTRY = {}
except Exception:
    # If anything goes wrong, fall back to base module
    TraceEvent = BaseTraceEvent
    ToolCallEvent = None
    ToolResultEvent = None
    LLMRequestEvent = None
    LLMResponseEvent = None
    DecisionEvent = None
    SafetyCheckEvent = None
    RefusalEvent = None
    PolicyViolationEvent = None
    PromptPolicyEvent = None
    AgentTurnEvent = None
    BehaviorAlertEvent = None
    ErrorEvent = None
    Session = None
    Checkpoint = None
    EVENT_TYPE_REGISTRY = {}

__all__ = [
    # From base.py
    "EventType",
    "SessionStatus",
    "RiskLevel",
    "SafetyOutcome",
    "BASE_EVENT_FIELDS",
    "_serialize_field_value",
    "TraceEvent",
    # From old events.py (temporary)
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
