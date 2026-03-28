"""Importance scoring for trace events.

This lives in the SDK so trace emission can score events without importing
collector modules and creating package-level circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict

from agent_debugger_sdk.core.events import EventType, TraceEvent


def _event_value(event: TraceEvent, key: str, default: object = None) -> object:
    """Read structured event fields from data or attributes.

    Priority order:
    1. event.data[key] (explicitly provided values override defaults)
    2. event attribute (typed field with default value)
    3. default parameter
    """
    # First check if key is explicitly in data
    if key in event.data:
        return event.data[key]

    # Then check if it's an attribute
    if hasattr(event, key):
        value = getattr(event, key)
        if value is not None:
            return value

    # Finally return the default
    return default


def _event_value_is_default(event: TraceEvent, key: str) -> bool:
    """Check if an event field has its default value (was not explicitly set).

    Returns True if the field is missing from data AND is not a dataclass field,
    or if it has the default value from the dataclass field definition.
    This allows us to distinguish between "not provided" and "explicitly set to empty list".
    """
    # First check if the key exists in the data dict
    if key in event.data:
        return False  # Key was explicitly provided

    # Check if this is a dataclass field
    if hasattr(event.__class__, "__dataclass_fields__"):
        fields = event.__class__.__dataclass_fields__
        if key in fields:
            # This is a typed field on the event class
            # It wasn't in data, so it has the default value
            return True
        else:
            # This is NOT a typed field on the event class
            # It's not in data either, so treat as "not applicable" (True)
            return True

    # Not a dataclass or key not found
    return True


@dataclass
class ImportanceScorer:
    """Score events for importance."""

    error_weight: float = 0.4
    decision_weight: float = 0.3
    cost_weight: float = 0.15
    duration_weight: float = 0.15

    # Base scores for each event type (class-level constant)
    _BASE_SCORES: ClassVar[Dict[EventType, float]] = {
        EventType.ERROR: 0.9,
        EventType.DECISION: 0.7,
        EventType.TOOL_RESULT: 0.5,
        EventType.LLM_RESPONSE: 0.5,
        EventType.TOOL_CALL: 0.4,
        EventType.LLM_REQUEST: 0.3,
        EventType.AGENT_START: 0.2,
        EventType.AGENT_END: 0.2,
        EventType.CHECKPOINT: 0.6,
        EventType.SAFETY_CHECK: 0.75,
        EventType.REFUSAL: 0.85,
        EventType.POLICY_VIOLATION: 0.92,
        EventType.PROMPT_POLICY: 0.45,
        EventType.AGENT_TURN: 0.45,
        EventType.BEHAVIOR_ALERT: 0.88,
    }

    def score(self, event: TraceEvent) -> float:
        """Calculate importance score for an event."""
        score = self._BASE_SCORES.get(event.event_type, 0.3)

        # Apply event-type-specific modifiers
        score = self._apply_tool_result_modifier(event, score)
        score = self._apply_llm_response_modifier(event, score)
        score = self._apply_decision_modifier(event, score)
        score = self._apply_safety_check_modifier(event, score)
        score = self._apply_behavior_alert_modifier(event, score)

        # Apply universal modifiers
        score = self._apply_duration_modifier(event, score)
        score = self._apply_upstream_modifier(event, score)

        return min(score, 1.0)

    def _apply_tool_result_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply scoring modifier for TOOL_RESULT events."""
        if event.event_type == EventType.TOOL_RESULT and _event_value(event, "error"):
            return score + self.error_weight
        return score

    def _apply_llm_response_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply scoring modifier for LLM_RESPONSE events."""
        if event.event_type == EventType.LLM_RESPONSE:
            cost = float(_event_value(event, "cost_usd", 0) or 0)
            if cost > 0.01:
                return score + self.cost_weight * min(cost / 0.1, 1.0)
        return score

    def _apply_decision_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply scoring modifier for DECISION events."""
        if event.event_type != EventType.DECISION:
            return score

        confidence = float(_event_value(event, "confidence", 0.5) or 0.5)
        score += self.decision_weight * abs(0.5 - confidence) * 2

        # Check if this event has an evidence field (only DecisionEvent does)
        has_evidence_field = (
            hasattr(event.__class__, "__dataclass_fields__")
            and "evidence" in event.__class__.__dataclass_fields__
        )

        if has_evidence_field:
            # Check if evidence is empty or falsy
            evidence = _event_value(event, "evidence", [])
            if not evidence:
                score += 0.05

            # Check if evidence_event_ids is non-empty
            evidence_event_ids = _event_value(event, "evidence_event_ids", [])
            if evidence_event_ids:
                score += 0.05

        return score

    def _apply_safety_check_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply scoring modifier for SAFETY_CHECK events."""
        if event.event_type == EventType.SAFETY_CHECK:
            outcome = str(_event_value(event, "outcome", "pass"))
            if outcome != "pass":
                return score + 0.1
        return score

    def _apply_behavior_alert_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply scoring modifier for BEHAVIOR_ALERT events."""
        if event.event_type == EventType.BEHAVIOR_ALERT:
            severity = str(_event_value(event, "severity", "medium"))
            if severity == "high":
                return score + 0.05
        return score

    def _apply_duration_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply duration-based scoring modifier."""
        duration = float(_event_value(event, "duration_ms", 0) or 0)
        if duration > 1000:
            return score + self.duration_weight * min(duration / 10000, 1.0)
        return score

    def _apply_upstream_modifier(self, event: TraceEvent, score: float) -> float:
        """Apply upstream event-based scoring modifier."""
        if _event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])):
            return score + 0.03
        return score


_importance_scorer: ImportanceScorer | None = None


def get_importance_scorer() -> ImportanceScorer:
    """Get the global importance scorer singleton."""
    global _importance_scorer
    if _importance_scorer is None:
        _importance_scorer = ImportanceScorer()
    return _importance_scorer
