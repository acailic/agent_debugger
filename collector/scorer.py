"""Importance scoring for trace events.

This module provides the ImportanceScorer class for calculating
importance scores (0.0-1.0) for trace events based on various factors
including event type, errors, cost, duration, and decision confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import TraceEvent


@dataclass
class ImportanceScorer:
    """Score events for importance (0.0-1.0).

    Uses a weighted combination of factors to determine the relative
    importance of events for filtering, display prioritization, and
    attention guidance in the debugger interface.

    Attributes:
        error_weight: Weight for error-related importance (default: 0.4)
        decision_weight: Weight for decision-related importance (default: 0.3)
        cost_weight: Weight for cost-related importance (default: 0.15)
        duration_weight: Weight for duration-related importance (default: 0.15)
    """

    error_weight: float = 0.4
    decision_weight: float = 0.3
    cost_weight: float = 0.15
    duration_weight: float = 0.15

    def score(self, event: TraceEvent) -> float:
        """Calculate importance score for an event.

        The scoring algorithm considers:
        1. Base score by event type (errors highest, lifecycle events lowest)
        2. Boost for errors in tool results
        3. Boost for high-cost LLM responses
        4. Boost for long-running operations
        5. Boost for high or low confidence decisions

        Args:
            event: The trace event to score

        Returns:
            Importance score between 0.0 and 1.0
        """
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
        }
        score = base_scores.get(event.event_type, 0.3)

        if event.event_type == EventType.TOOL_RESULT and event.data.get("error"):
            score += self.error_weight

        if event.event_type == EventType.LLM_RESPONSE:
            cost = event.data.get("cost_usd", 0)
            if cost > 0.01:
                score += self.cost_weight * min(cost / 0.1, 1.0)

        duration = event.data.get("duration_ms", 0)
        if duration > 1000:
            score += self.duration_weight * min(duration / 10000, 1.0)

        if event.event_type == EventType.DECISION:
            confidence = event.data.get("confidence", 0.5)
            score += self.decision_weight * abs(0.5 - confidence) * 2

        return min(score, 1.0)


_importance_scorer: ImportanceScorer | None = None


def get_importance_scorer() -> ImportanceScorer:
    """Get the global importance scorer singleton.

    Creates the scorer on first call, returns existing instance thereafter.

    Returns:
        The global ImportanceScorer instance
    """
    global _importance_scorer
    if _importance_scorer is None:
        _importance_scorer = ImportanceScorer()
    return _importance_scorer
