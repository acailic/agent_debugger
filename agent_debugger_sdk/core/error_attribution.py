"""Backward failure attribution for agent errors.

Based on ErrorProbe methodology - identifies and attributes failures to their root causes
by analyzing causal chains in agent execution traces.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum  # type: ignore[assignment]
else:

    class StrEnum(str, Enum):  # type: ignore[misc]
        """Compatibility shim for StrEnum in Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)

from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "FailureCategory",
    "AttributionStrength",
    "ErrorAttribution",
    "FailureChain",
    "attribute_errors",
    "find_root_causes",
    "analyze_failure_patterns",
]


class FailureCategory(StrEnum):
    """Categories of failures in agent execution."""

    RUNTIME_ERROR = "runtime_error"  # General runtime errors and exceptions
    TOOL_FAILURE = "tool_failure"  # Tool execution failures
    GUARDRAIL_BLOCK = "guardrail_block"  # Safety/policy refusals
    POLICY_VIOLATION = "policy_violation"  # Policy violations
    STATE_CORRUPTION = "state_corruption"  # Invalid or inconsistent state
    LOGIC_ERROR = "logic_error"  # Incorrect reasoning or decisions
    RESOURCE_FAILURE = "resource_failure"  # External resource failures
    TIMEOUT = "timeout"  # Operation timeouts
    UNKNOWN = "unknown"  # Unclassified failures


class AttributionStrength(StrEnum):
    """Confidence levels in failure attribution."""

    DEFINITIVE = "definitive"  # Clear causal chain with strong evidence
    STRONG = "strong"  # High confidence with supporting evidence
    MODERATE = "moderate"  # Reasonable confidence with some ambiguity
    WEAK = "weak"  # Low confidence, multiple possible causes
    SPECULATIVE = "speculative"  # Very uncertain, best-guess attribution


@dataclass(kw_only=True)
class ErrorAttribution:
    """Attribution of a failure to its root cause.

    Attributes:
        error_event_id: The error event being attributed
        root_cause_event_id: The event identified as the root cause
        failure_category: Category of the failure
        attribution_strength: Confidence in this attribution
        causal_chain: Events in the causal chain from root cause to error
        contributing_factors: Other events that contributed to the failure
        attribution_reasoning: Explanation of why this root cause was identified
        mitigation_suggestions: Suggestions for preventing similar failures
    """

    error_event_id: str
    root_cause_event_id: str
    failure_category: FailureCategory
    attribution_strength: AttributionStrength
    causal_chain: list[str] = field(default_factory=list)
    contributing_factors: list[dict[str, Any]] = field(default_factory=list)
    attribution_reasoning: str = ""
    mitigation_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "error_event_id": self.error_event_id,
            "root_cause_event_id": self.root_cause_event_id,
            "failure_category": self.failure_category.value,
            "attribution_strength": self.attribution_strength.value,
            "causal_chain": list(self.causal_chain),
            "contributing_factors": list(self.contributing_factors),
            "attribution_reasoning": self.attribution_reasoning,
            "mitigation_suggestions": list(self.mitigation_suggestions),
        }


@dataclass(kw_only=True)
class FailureChain:
    """A chain of events leading from root cause to failure.

    Attributes:
        error_event_id: The failure event at the end of the chain
        chain_events: Events in the chain from root cause to failure
        chain_length: Number of events in the chain
        total_duration: Time from root cause to failure
        weak_points: Events in the chain that represent脆弱点
        failure_category: Category of the failure
        attribution_strength: Confidence in the chain analysis
    """

    error_event_id: str
    chain_events: list[dict[str, Any]] = field(default_factory=list)
    chain_length: int = 0
    total_duration: float = 0.0
    weak_points: list[dict[str, Any]] = field(default_factory=list)
    failure_category: FailureCategory = FailureCategory.UNKNOWN
    attribution_strength: AttributionStrength = AttributionStrength.MODERATE

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "error_event_id": self.error_event_id,
            "chain_events": list(self.chain_events),
            "chain_length": self.chain_length,
            "total_duration": self.total_duration,
            "weak_points": list(self.weak_points),
            "failure_category": self.failure_category.value,
            "attribution_strength": self.attribution_strength.value,
        }


def _is_error_event(event: TraceEvent) -> bool:
    """Check if an event represents an error or failure."""
    if event.event_type == EventType.ERROR:
        return True
    if event.event_type == EventType.REFUSAL:
        return True
    if event.event_type == EventType.POLICY_VIOLATION:
        return True
    if event.event_type == EventType.BEHAVIOR_ALERT:
        return True
    if event.event_type == EventType.TOOL_RESULT:
        # Check for error in data or metadata
        error = event.data.get("error") or event.metadata.get("error")
        return error is not None
    if event.event_type == EventType.SAFETY_CHECK:
        outcome = event.data.get("outcome") or event.metadata.get("outcome")
        return outcome and outcome != "pass"
    return False


def _classify_failure_category(event: TraceEvent) -> FailureCategory:
    """Classify the category of failure for an event."""
    if event.event_type == EventType.ERROR:
        error_type = event.data.get("error_type") or event.metadata.get("error_type", "")
        error_msg = event.data.get("error_message") or event.metadata.get("error_message", "")

        if "timeout" in error_type.lower() or "timeout" in error_msg.lower():
            return FailureCategory.TIMEOUT
        if "tool" in error_type.lower() or "tool" in error_msg.lower():
            return FailureCategory.TOOL_FAILURE
        if "state" in error_type.lower() or "state" in error_msg.lower():
            return FailureCategory.STATE_CORRUPTION
        if "resource" in error_type.lower() or "resource" in error_msg.lower():
            return FailureCategory.RESOURCE_FAILURE
        return FailureCategory.RUNTIME_ERROR

    if event.event_type == EventType.REFUSAL:
        return FailureCategory.GUARDRAIL_BLOCK

    if event.event_type == EventType.POLICY_VIOLATION:
        return FailureCategory.POLICY_VIOLATION

    if event.event_type == EventType.BEHAVIOR_ALERT:
        alert_type = event.data.get("alert_type") or event.metadata.get("alert_type", "")
        if "loop" in alert_type.lower():
            return FailureCategory.LOGIC_ERROR
        if "state" in alert_type.lower():
            return FailureCategory.STATE_CORRUPTION
        return FailureCategory.LOGIC_ERROR

    if event.event_type == EventType.TOOL_RESULT:
        return FailureCategory.TOOL_FAILURE

    if event.event_type == EventType.SAFETY_CHECK:
        return FailureCategory.GUARDRAIL_BLOCK

    return FailureCategory.UNKNOWN


def _calculate_attribution_strength(
    causal_chain: list[TraceEvent],
    error_event: TraceEvent
) -> AttributionStrength:
    """Calculate confidence in the attribution based on chain quality."""
    if not causal_chain:
        return AttributionStrength.SPECULATIVE

    # Check for strong evidence
    has_explicit_dependency = any(
        error_event.id in (e.upstream_event_ids or [])
        for e in causal_chain
    )

    # Check for parent-child relationship
    has_parent_link = any(
        e.parent_id == causal_chain[-1].id if causal_chain else False
        for e in [error_event]
    )

    # Check for decision with low confidence (weak point)
    has_weak_decision = any(
        e.event_type == EventType.DECISION and
        (e.data.get("confidence") or e.metadata.get("confidence", 1.0)) < 0.7
        for e in causal_chain
    )

    # Determine strength
    if has_explicit_dependency and has_parent_link:
        return AttributionStrength.DEFINITIVE
    if has_explicit_dependency or has_parent_link:
        return AttributionStrength.STRONG
    if has_weak_decision:
        return AttributionStrength.MODERATE
    if len(causal_chain) <= 2:
        return AttributionStrength.WEAK
    return AttributionStrength.SPECULATIVE


def _trace_causal_chain(
    error_event: TraceEvent,
    all_events: list[TraceEvent]
) -> list[TraceEvent]:
    """Trace backward from error to find causal chain."""
    chain = []
    current_event = error_event
    visited = set()

    while current_event and current_event.id not in visited:
        visited.add(current_event.id)
        chain.append(current_event)

        # Find parent event
        if current_event.parent_id:
            parent_events = [e for e in all_events if e.id == current_event.parent_id]
            if parent_events:
                current_event = parent_events[0]
                continue

        # Find upstream events
        if current_event.upstream_event_ids:
            upstream_events = [e for e in all_events
                              if e.id in current_event.upstream_event_ids]
            if upstream_events:
                # Choose the most recent upstream event
                current_event = max(upstream_events, key=lambda e: e.timestamp)
                continue

        # No more causal links
        break

    # Reverse to get root cause -> error order
    chain.reverse()
    return chain


def _identify_weak_points(causal_chain: list[TraceEvent]) -> list[dict[str, Any]]:
    """Identify weak points in the causal chain."""
    weak_points = []

    for i, event in enumerate(causal_chain):
        # Low confidence decisions
        if event.event_type == EventType.DECISION:
            confidence = event.data.get("confidence") or event.metadata.get("confidence", 1.0)
            if confidence < 0.7:
                weak_points.append({
                    "event_id": event.id,
                    "position": i,
                    "weakness_type": "low_confidence_decision",
                    "description": f"Low confidence decision ({confidence:.2f})",
                    "severity": "high" if confidence < 0.5 else "medium",
                })

        # Events without evidence
        if event.event_type == EventType.DECISION:
            evidence = event.data.get("evidence") or event.metadata.get("evidence", [])
            if not evidence:
                weak_points.append({
                    "event_id": event.id,
                    "position": i,
                    "weakness_type": "unsupported_decision",
                    "description": "Decision without supporting evidence",
                    "severity": "medium",
                })

        # State changes near error
        if i > 0 and event.event_type in (EventType.ERROR, EventType.REFUSAL):
            prev_event = causal_chain[i - 1]
            if prev_event.event_type == EventType.DECISION:
                weak_points.append({
                    "event_id": prev_event.id,
                    "position": i - 1,
                    "weakness_type": "pre_error_decision",
                    "description": "Decision immediately preceding error",
                    "severity": "high",
                })

    return weak_points


def _generate_mitigation_suggestions(
    failure_category: FailureCategory,
    weak_points: list[dict[str, Any]]
) -> list[str]:
    """Generate mitigation suggestions based on failure analysis."""
    suggestions = []

    # Category-specific suggestions
    if failure_category == FailureCategory.TOOL_FAILURE:
        suggestions.append("Add error handling and retry logic for tool calls")
        suggestions.append("Validate tool inputs before execution")
        suggestions.append("Consider fallback tools for critical operations")

    elif failure_category == FailureCategory.GUARDRAIL_BLOCK:
        suggestions.append("Review and adjust safety/policy constraints")
        suggestions.append("Add pre-validation for sensitive operations")
        suggestions.append("Provide clearer guidance to avoid guardrails")

    elif failure_category == FailureCategory.LOGIC_ERROR:
        suggestions.append("Add verification steps for complex reasoning")
        suggestions.append("Implement loop detection and prevention")
        suggestions.append("Break down complex decisions into smaller steps")

    elif failure_category == FailureCategory.STATE_CORRUPTION:
        suggestions.append("Add state validation at critical checkpoints")
        suggestions.append("Implement state rollback mechanisms")
        suggestions.append("Log state changes for debugging")

    # Weak point-specific suggestions
    for wp in weak_points:
        if wp["weakness_type"] == "low_confidence_decision":
            suggestions.append(f"Improve confidence for decision at event {wp['event_id']} by gathering more evidence")
        elif wp["weakness_type"] == "unsupported_decision":
            suggestions.append(f"Add evidence verification for decision at event {wp['event_id']}")
        elif wp["weakness_type"] == "pre_error_decision":
            suggestions.append(f"Review decision logic at event {wp['event_id']} for potential issues")

    return list(set(suggestions))  # Remove duplicates


def attribute_errors(events: list[TraceEvent]) -> list[ErrorAttribution]:
    """Analyze errors and attribute them to their root causes.

    Args:
        events: List of trace events from a session

    Returns:
        List of ErrorAttribution objects, one for each error found
    """
    if not events:
        return []

    # Find all error events
    error_events = [e for e in events if _is_error_event(e)]

    attributions = []
    for error_event in error_events:
        # Trace causal chain
        causal_chain = _trace_causal_chain(error_event, events)

        # Identify root cause (first event in chain)
        root_cause_id = causal_chain[0].id if causal_chain else error_event.id

        # Classify failure category
        failure_category = _classify_failure_category(error_event)

        # Calculate attribution strength
        attribution_strength = _calculate_attribution_strength(causal_chain, error_event)

        # Identify weak points
        weak_points = _identify_weak_points(causal_chain)

        # Generate attribution reasoning
        if not causal_chain:
            reasoning = "No causal chain found - error appears isolated"
        elif len(causal_chain) == 1:
            reasoning = "Error occurred without preceding causal events"
        else:
            reasoning = f"Error traced back through {len(causal_chain)} events to root cause"
            if attribution_strength == AttributionStrength.DEFINITIVE:
                reasoning += " with explicit causal dependencies"
            elif attribution_strength == AttributionStrength.STRONG:
                reasoning += " with strong evidence"
            else:
                reasoning += " with moderate confidence"

        # Generate mitigation suggestions
        mitigation_suggestions = _generate_mitigation_suggestions(
            failure_category, weak_points
        )

        # Build contributing factors
        contributing_factors = []
        for wp in weak_points:
            contributing_factors.append({
                "event_id": wp["event_id"],
                "factor_type": wp["weakness_type"],
                "description": wp["description"],
                "severity": wp.get("severity", "unknown"),
            })

        attributions.append(ErrorAttribution(
            error_event_id=error_event.id,
            root_cause_event_id=root_cause_id,
            failure_category=failure_category,
            attribution_strength=attribution_strength,
            causal_chain=[e.id for e in causal_chain],
            contributing_factors=contributing_factors,
            attribution_reasoning=reasoning,
            mitigation_suggestions=mitigation_suggestions,
        ))

    return attributions


def find_root_causes(events: list[TraceEvent]) -> list[dict[str, Any]]:
    """Find root causes for all failures in a session.

    Args:
        events: List of trace events from a session

    Returns:
        List of root cause analyses with failure information
    """
    attributions = attribute_errors(events)

    root_causes = []
    for attr in attributions:
        root_causes.append({
            "error_event_id": attr.error_event_id,
            "root_cause_event_id": attr.root_cause_event_id,
            "failure_category": attr.failure_category.value,
            "attribution_strength": attr.attribution_strength.value,
            "chain_length": len(attr.causal_chain),
            "reasoning": attr.attribution_reasoning,
            "has_mitigation": len(attr.mitigation_suggestions) > 0,
        })

    return root_causes


def analyze_failure_patterns(events: list[TraceEvent]) -> dict[str, Any]:
    """Analyze patterns of failures across a session.

    Args:
        events: List of trace events from a session

    Returns:
        Dictionary with failure pattern analysis
    """
    attributions = attribute_errors(events)

    if not attributions:
        return {
            "total_errors": 0,
            "error_categories": {},
            "attribution_strengths": {},
            "common_weaknesses": [],
            "recommendations": [],
        }

    # Count by category
    category_counts = {}
    for attr in attributions:
        cat = attr.failure_category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Count by attribution strength
    strength_counts = {}
    for attr in attributions:
        strength = attr.attribution_strength.value
        strength_counts[strength] = strength_counts.get(strength, 0) + 1

    # Find common weaknesses
    all_weaknesses = []
    for attr in attributions:
        for factor in attr.contributing_factors:
            all_weaknesses.append(factor["factor_type"])

    weakness_counts = {}
    for weakness in all_weaknesses:
        weakness_counts[weakness] = weakness_counts.get(weakness, 0) + 1

    common_weaknesses = [
        {"weakness_type": w, "count": c}
        for w, c in sorted(weakness_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # Generate session-level recommendations
    recommendations = []

    # High error rate recommendations
    if len(attributions) > 3:
        recommendations.append("Session has multiple failures - review overall agent strategy")

    # Category-specific recommendations
    if category_counts.get("tool_failure", 0) > 1:
        recommendations.append("Multiple tool failures suggest tool selection or usage issues")

    if category_counts.get("guardrail_block", 0) > 1:
        recommendations.append("Frequent guardrail blocks indicate constraint conflicts")

    if category_counts.get("logic_error", 0) > 1:
        recommendations.append("Repeated logic errors suggest fundamental reasoning issues")

    # Attribution quality recommendations
    weak_attribution_count = strength_counts.get("weak", 0) + strength_counts.get("speculative", 0)
    if weak_attribution_count > len(attributions) / 2:
        recommendations.append("Many failures have uncertain root causes - improve trace instrumentation")

    return {
        "total_errors": len(attributions),
        "error_categories": category_counts,
        "attribution_strengths": strength_counts,
        "common_weaknesses": common_weaknesses[:5],  # Top 5
        "recommendations": recommendations,
    }


def build_failure_chain(
    error_event: TraceEvent,
    all_events: list[TraceEvent]
) -> FailureChain:
    """Build a detailed failure chain for a specific error.

    Args:
        error_event: The error event to analyze
        all_events: All events in the session for context

    Returns:
        FailureChain object with detailed chain analysis
    """
    # Trace causal chain
    causal_chain = _trace_causal_chain(error_event, all_events)

    # Classify failure
    failure_category = _classify_failure_category(error_event)

    # Calculate attribution strength
    attribution_strength = _calculate_attribution_strength(causal_chain, error_event)

    # Identify weak points
    weak_points = _identify_weak_points(causal_chain)

    # Calculate duration
    total_duration = 0.0
    if len(causal_chain) >= 2:
        total_duration = (causal_chain[-1].timestamp - causal_chain[0].timestamp).total_seconds()

    # Build chain events with details
    chain_events = []
    for i, event in enumerate(causal_chain):
        chain_events.append({
            "sequence": i,
            "event_id": event.id,
            "event_type": str(event.event_type),
            "name": event.name or str(event.event_type),
            "timestamp": event.timestamp.isoformat(),
            "is_error": _is_error_event(event),
        })

    return FailureChain(
        error_event_id=error_event.id,
        chain_events=chain_events,
        chain_length=len(causal_chain),
        total_duration=total_duration,
        weak_points=weak_points,
        failure_category=failure_category,
        attribution_strength=attribution_strength,
    )
