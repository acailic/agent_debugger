"""Redundancy scoring for agent steps.

Based on RedundancyBench (arXiv:2605.29893) - identifies redundant, harmful,
and essential steps in agent execution traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = ["StepContribution", "RedundancyScore", "score_session"]


class StepContribution(Enum):
    """Classification of a step's contribution to the session outcome."""

    ESSENTIAL = "essential"  # Step contributes positively to goal achievement
    REDUNDANT = "redundant"  # Step has no meaningful impact on outcome
    HARMFUL = "harmful"  # Step negatively impacts outcome or causes errors
    UNKNOWN = "unknown"  # Unable to determine contribution


@dataclass
class RedundancyScore:
    """Redundancy analysis for a single step/event."""

    step_id: str
    score: float  # 0.0 (redundant) to 1.0 (essential)
    contribution: StepContribution
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "score": self.score,
            "contribution": self.contribution.value,
            "reasoning": self.reasoning,
        }


def _event_has_error(event: TraceEvent) -> bool:
    """Check if event indicates an error occurred."""
    if event.event_type == EventType.ERROR:
        return True
    if event.event_type == EventType.TOOL_RESULT and getattr(event, "error", None):
        return True
    if event.event_type == EventType.SAFETY_CHECK:
        outcome = str(getattr(event, "outcome", "pass"))
        return bool(outcome and outcome != "pass")
    if event.event_type == EventType.REFUSAL:
        return True
    if event.event_type == EventType.POLICY_VIOLATION:
        return True
    return event.event_type == EventType.BEHAVIOR_ALERT


def _event_has_downstream_impact(event: TraceEvent, all_events: list[TraceEvent]) -> bool:
    """Check if this event has downstream events that depend on it."""
    event_id = event.id

    # Check if any event references this as upstream
    for other_event in all_events:
        upstream_ids = getattr(other_event, "upstream_event_ids", [])
        if upstream_ids and event_id in upstream_ids:
            return True

    # Check if this is a decision or tool call that influenced later events
    # These event types typically have downstream impact by default
    return event.event_type in {EventType.DECISION, EventType.TOOL_CALL, EventType.LLM_REQUEST}


def _classify_step_contribution(
    event: TraceEvent,
    all_events: list[TraceEvent],
    session_errors: int,
    total_llm_calls: int,
    total_tool_calls: int
) -> tuple[StepContribution, str]:
    """Classify a step's contribution and provide reasoning."""

    # Harmful steps
    if _event_has_error(event):
        if event.event_type == EventType.ERROR:
            return StepContribution.HARMFUL, "Runtime error that disrupted execution"
        if event.event_type == EventType.TOOL_RESULT and getattr(event, "error", None):
            return StepContribution.HARMFUL, f"Tool execution failed: {getattr(event, 'error', 'unknown')}"
        if event.event_type == EventType.SAFETY_CHECK:
            return StepContribution.HARMFUL, "Safety check did not pass"
        if event.event_type == EventType.REFUSAL:
            return StepContribution.HARMFUL, "Request refused, blocking progress"
        if event.event_type == EventType.POLICY_VIOLATION:
            return StepContribution.HARMFUL, "Policy violation that required intervention"
        if event.event_type == EventType.BEHAVIOR_ALERT:
            return StepContribution.HARMFUL, "Behavior alert indicating problematic pattern"

    # Essential steps (high impact events)
    if event.event_type == EventType.DECISION:
        confidence = getattr(event, "confidence", None)
        if confidence is not None and confidence < 0.3:
            return StepContribution.ESSENTIAL, "Low-confidence decision point requiring inspection"
        evidence = getattr(event, "evidence", None)
        if evidence:
            return StepContribution.ESSENTIAL, "Decision with supporting evidence"
        return StepContribution.ESSENTIAL, "Agent decision point that guided execution"

    if event.event_type == EventType.AGENT_TURN:
        return StepContribution.ESSENTIAL, "Major agent turn/phase in execution"

    if event.event_type == EventType.LLM_RESPONSE:
        cost = getattr(event, "cost_usd", None) or 0
        if cost > 0.01:
            return StepContribution.ESSENTIAL, f"High-cost LLM call (${cost:.4f})"
        return StepContribution.ESSENTIAL, "LLM response that generated content or reasoning"

    if event.event_type == EventType.TOOL_CALL:
        return StepContribution.ESSENTIAL, "Tool invocation that performed external action"

    if event.event_type == EventType.TOOL_RESULT and not getattr(event, "error", None):
        return StepContribution.ESSENTIAL, "Tool result that provided data or completed action"

    # Check for downstream impact
    if _event_has_downstream_impact(event, all_events):
        return StepContribution.ESSENTIAL, "Step influenced subsequent execution events"

    # Redundant steps (low impact events)
    if event.event_type == EventType.LLM_REQUEST:
        return StepContribution.REDUNDANT, "LLM request (response analyzed separately)"

    if event.event_type == EventType.CHECKPOINT:
        return StepContribution.REDUNDANT, "State checkpoint (bookkeeping event)"

    if event.event_type == EventType.PROMPT_POLICY:
        return StepContribution.REDUNDANT, "Prompt policy evaluation (internal check)"

    # Default to essential for unknown types (better to over-analyze than miss issues)
    return StepContribution.UNKNOWN, "Unable to classify contribution"


def _calculate_redundancy_score(contribution: StepContribution) -> float:
    """Convert contribution classification to redundancy score.

    Score is 0.0 (fully redundant) to 1.0 (fully essential).
    """
    if contribution == StepContribution.ESSENTIAL:
        return 1.0
    elif contribution == StepContribution.HARMFUL:
        return 0.1  # Low score, but not zero because it's informative
    elif contribution == StepContribution.REDUNDANT:
        return 0.0
    else:  # UNKNOWN
        return 0.5  # Neutral score for unknown classification


def score_session(events: list[TraceEvent]) -> list[RedundancyScore]:
    """Analyze a session's events and score each step for redundancy.

    Args:
        events: List of trace events from the session

    Returns:
        List of RedundancyScore objects, one per event
    """
    if not events:
        return []

    scores: list[RedundancyScore] = []

    # Calculate session-level context
    session_errors = sum(1 for e in events if _event_has_error(e))
    total_llm_calls = sum(1 for e in events if e.event_type == EventType.LLM_REQUEST)
    total_tool_calls = sum(1 for e in events if e.event_type == EventType.TOOL_CALL)

    for event in events:
        # Classify contribution
        contribution, reasoning = _classify_step_contribution(
            event, events, session_errors, total_llm_calls, total_tool_calls
        )

        # Calculate numeric score
        score = _calculate_redundancy_score(contribution)

        scores.append(RedundancyScore(
            step_id=event.id,
            score=score,
            contribution=contribution,
            reasoning=reasoning
        ))

    return scores


def calculate_session_redundancy_summary(scores: list[RedundancyScore]) -> dict[str, Any]:
    """Calculate summary statistics for a session's redundancy analysis.

    Args:
        scores: List of RedundancyScore objects from score_session()

    Returns:
        Dictionary with summary statistics
    """
    if not scores:
        return {
            "total_steps": 0,
            "essential_count": 0,
            "redundant_count": 0,
            "harmful_count": 0,
            "unknown_count": 0,
            "avg_score": 0.0,
            "redundancy_rate": 0.0,
        }

    essential_count = sum(1 for s in scores if s.contribution == StepContribution.ESSENTIAL)
    redundant_count = sum(1 for s in scores if s.contribution == StepContribution.REDUNDANT)
    harmful_count = sum(1 for s in scores if s.contribution == StepContribution.HARMFUL)
    unknown_count = sum(1 for s in scores if s.contribution == StepContribution.UNKNOWN)

    avg_score = sum(s.score for s in scores) / len(scores)
    redundancy_rate = redundant_count / len(scores)

    return {
        "total_steps": len(scores),
        "essential_count": essential_count,
        "redundant_count": redundant_count,
        "harmful_count": harmful_count,
        "unknown_count": unknown_count,
        "avg_score": avg_score,
        "redundancy_rate": redundancy_rate,
    }