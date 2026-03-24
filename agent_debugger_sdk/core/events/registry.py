"""Event type registry for mapping EventType strings to concrete event classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import EventType, TraceEvent

if TYPE_CHECKING:
    # Type hints for type checkers - these imports are used at runtime in _get_event_classes()
    from .agent import AgentTurnEvent, BehaviorAlertEvent  # noqa: F401
    from .decisions import DecisionEvent  # noqa: F401
    from .errors import ErrorEvent  # noqa: F401
    from .llm import LLMRequestEvent, LLMResponseEvent  # noqa: F401
    from .safety import (  # noqa: F401
        PolicyViolationEvent,
        PromptPolicyEvent,
        RefusalEvent,
        SafetyCheckEvent,
    )
    from .tools import ToolCallEvent, ToolResultEvent  # noqa: F401


# Deferred imports to avoid circular dependencies
def _get_event_classes() -> dict[EventType, type[TraceEvent]]:
    """Lazily import event classes to avoid circular dependencies."""
    from .agent import AgentTurnEvent, BehaviorAlertEvent
    from .decisions import DecisionEvent
    from .errors import ErrorEvent
    from .llm import LLMRequestEvent, LLMResponseEvent
    from .safety import (
        PolicyViolationEvent,
        PromptPolicyEvent,
        RefusalEvent,
        SafetyCheckEvent,
    )
    from .tools import ToolCallEvent, ToolResultEvent

    return {
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


# Create the registry as a lazily-evaluated mapping
class _EventTypeRegistry(dict[EventType, type[TraceEvent]]):
    """Lazy-loading registry for event type mappings."""

    def __missing__(self, key: EventType) -> type[TraceEvent]:
        """Load event classes on first access."""
        self.update(_get_event_classes())
        if key in self:
            return self[key]
        raise KeyError(f"EventType {key} not found in registry")


EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = _EventTypeRegistry()
