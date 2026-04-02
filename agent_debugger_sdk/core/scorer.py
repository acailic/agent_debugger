"""Importance scoring for trace events.

This lives in the SDK so trace emission can score events without importing
collector modules and creating package-level circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = ["event_value", "ImportanceScorer", "get_importance_scorer"]


def event_value(event: TraceEvent | None, key: str, default: Any = None) -> Any:
    """Extract a value from an event, checking both attributes and data dict.

    Args:
        event: The event to extract from (can be None)
        key: The key to look for
        default: Default value if key not found

    Returns:
        The value or default
    """
    if event is None:
        return default
    if hasattr(event, key):
        return getattr(event, key)
    return event.data.get(key, default)


@dataclass
class ImportanceScorer:
    """Score events for importance."""

    error_weight: float = 0.4
    decision_weight: float = 0.3
    cost_weight: float = 0.15
    duration_weight: float = 0.15

    def score(self, event: TraceEvent) -> float:
        """Calculate importance score for an event."""
        base_scores: dict[EventType, float] = {
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
        score = base_scores.get(event.event_type, 0.3)

        score += self._score_tool_result(event)
        score += self._score_llm_response(event)
        score += self._score_duration(event)
        score += self._score_decision(event)
        score += self._score_safety_check(event)
        score += self._score_behavior_alert(event)
        score += self._score_upstream_links(event)

        return min(score, 1.0)

    def _score_tool_result(self, event: TraceEvent) -> float:
        """Add bonus for failed tool results."""
        if event.event_type == EventType.TOOL_RESULT and event_value(event, "error"):
            return self.error_weight
        return 0.0

    def _score_llm_response(self, event: TraceEvent) -> float:
        """Add bonus for costly LLM responses."""
        if event.event_type == EventType.LLM_RESPONSE:
            cost = float(event_value(event, "cost_usd", 0) or 0)
            if cost > 0.01:
                return self.cost_weight * min(cost / 0.1, 1.0)
        return 0.0

    def _score_duration(self, event: TraceEvent) -> float:
        """Add bonus for long-running events."""
        duration = float(event_value(event, "duration_ms", 0) or 0)
        if duration > 1000:
            return self.duration_weight * min(duration / 10000, 1.0)
        return 0.0

    def _score_decision(self, event: TraceEvent) -> float:
        """Add bonus for low-confidence or well-evidenced decisions."""
        if event.event_type != EventType.DECISION:
            return 0.0

        bonus = 0.0
        confidence = float(event_value(event, "confidence", 0.5) or 0.5)
        bonus += self.decision_weight * abs(0.5 - confidence) * 2

        if not event_value(event, "evidence", []):
            bonus += 0.05
        if event_value(event, "evidence_event_ids", []):
            bonus += 0.05

        return bonus

    def _score_safety_check(self, event: TraceEvent) -> float:
        """Add bonus for failed safety checks."""
        if event.event_type == EventType.SAFETY_CHECK:
            outcome = str(event_value(event, "outcome", "pass"))
            if outcome != "pass":
                return 0.1
        return 0.0

    def _score_behavior_alert(self, event: TraceEvent) -> float:
        """Add bonus for high-severity behavior alerts."""
        if event.event_type == EventType.BEHAVIOR_ALERT:
            severity = str(event_value(event, "severity", "medium"))
            if severity == "high":
                return 0.05
        return 0.0

    def _score_upstream_links(self, event: TraceEvent) -> float:
        """Add bonus for events with causal links."""
        if event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])):
            return 0.03
        return 0.0


_importance_scorer: ImportanceScorer | None = None


def get_importance_scorer() -> ImportanceScorer:
    """Get the global importance scorer singleton."""
    global _importance_scorer
    if _importance_scorer is None:
        _importance_scorer = ImportanceScorer()
    return _importance_scorer
