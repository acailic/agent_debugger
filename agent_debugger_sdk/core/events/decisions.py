"""Agent decision events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, TraceEvent


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
        evidence_event_ids: IDs of events that provide evidence
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
