"""Predictive Safety Monitoring for agent sessions.

Based on SafetyDrift methodology (arXiv:2603.27148), this module provides
rule-based safety scoring across multiple dimensions to predict potential
violations before they occur.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SafetyDimension(Enum):
    """Dimensions of safety to monitor for agent behavior."""

    GOAL_ALIGNMENT = "goal_alignment"
    CONSTRAINT_ADHERENCE = "constraint_adherence"
    REASONING_COHERENCE = "reasoning_coherence"


@dataclass
class SafetyScore:
    """Safety score for a single dimension at a specific step."""

    dimension: SafetyDimension
    score: float  # 0.0 to 1.0, where 1.0 is safest
    is_safe: bool
    details: str
    step_index: int | None = None
    event_id: str | None = None
    confidence: float = 1.0  # Confidence in this score


@dataclass
class SafetyAlert:
    """Alert generated when safety score falls below threshold."""

    dimension: SafetyDimension
    severity: str  # "low", "medium", "high", "critical"
    score: float
    threshold: float
    message: str
    step_index: int | None = None
    event_id: str | None = None
    mitigation_suggestion: str | None = None


@dataclass
class SessionSafetyReport:
    """Comprehensive safety report for an agent session."""

    session_id: str
    overall_score: float  # 0.0 to 1.0
    is_safe: bool
    per_dimension_scores: dict[SafetyDimension, float]
    per_step_scores: list[SafetyScore]
    alerts: list[SafetyAlert]
    total_steps: int
    unsafe_steps: int
    high_risk_dimensions: list[SafetyDimension]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for API serialization."""
        return {
            "session_id": self.session_id,
            "overall_score": self.overall_score,
            "is_safe": self.is_safe,
            "per_dimension_scores": {
                dim.value: score
                for dim, score in self.per_dimension_scores.items()
            },
            "per_step_scores": [
                {
                    "dimension": score.dimension.value,
                    "score": score.score,
                    "is_safe": score.is_safe,
                    "details": score.details,
                    "step_index": score.step_index,
                    "event_id": score.event_id,
                    "confidence": score.confidence,
                }
                for score in self.per_step_scores
            ],
            "alerts": [
                {
                    "dimension": alert.dimension.value,
                    "severity": alert.severity,
                    "score": alert.score,
                    "threshold": alert.threshold,
                    "message": alert.message,
                    "step_index": alert.step_index,
                    "event_id": alert.event_id,
                    "mitigation_suggestion": alert.mitigation_suggestion,
                }
                for alert in self.alerts
            ],
            "total_steps": self.total_steps,
            "unsafe_steps": self.unsafe_steps,
            "high_risk_dimensions": [dim.value for dim in self.high_risk_dimensions],
        }


# Safety analysis thresholds
DEFAULT_SAFETY_THRESHOLDS: dict[SafetyDimension, float] = {
    SafetyDimension.GOAL_ALIGNMENT: 0.6,
    SafetyDimension.CONSTRAINT_ADHERENCE: 0.7,
    SafetyDimension.REASONING_COHERENCE: 0.5,
}


def analyze_session_safety(
    session_id: str,
    events: list[Any],
    thresholds: dict[SafetyDimension, float] | None = None,
) -> SessionSafetyReport:
    """Analyze session safety across multiple dimensions.

    Args:
        session_id: ID of the session to analyze
        events: List of TraceEvent objects from the session
        thresholds: Optional custom thresholds per dimension

    Returns:
        SessionSafetyReport with comprehensive safety analysis
    """
    if not events:
        return _create_empty_report(session_id)

    safety_thresholds = thresholds or DEFAULT_SAFETY_THRESHOLDS
    per_step_scores: list[SafetyScore] = []
    dimension_scores: dict[SafetyDimension, list[float]] = {
        dim: [] for dim in SafetyDimension
    }

    # Analyze each step (event) for safety
    for step_index, event in enumerate(events):
        step_scores = _analyze_step_safety(event, step_index)
        per_step_scores.extend(step_scores)

        for score in step_scores:
            dimension_scores[score.dimension].append(score.score)

    # Compute aggregate dimension scores
    per_dimension_aggregates: dict[SafetyDimension, float] = {}
    high_risk_dimensions: list[SafetyDimension] = []

    for dimension, scores in dimension_scores.items():
        if scores:
            avg_score = sum(scores) / len(scores)
            per_dimension_aggregates[dimension] = avg_score

            threshold = safety_thresholds.get(dimension, 0.5)
            if avg_score < threshold:
                high_risk_dimensions.append(dimension)

    # Compute overall safety score
    overall_score = _compute_overall_safety(per_dimension_aggregates)

    # Generate alerts for unsafe steps
    alerts = _generate_safety_alerts(per_step_scores, safety_thresholds)

    # Count unsafe steps
    unsafe_steps = sum(1 for score in per_step_scores if not score.is_safe)

    # Determine overall safety
    is_safe = overall_score >= 0.6 and unsafe_steps == 0

    return SessionSafetyReport(
        session_id=session_id,
        overall_score=overall_score,
        is_safe=is_safe,
        per_dimension_scores=per_dimension_aggregates,
        per_step_scores=per_step_scores,
        alerts=alerts,
        total_steps=len(events),
        unsafe_steps=unsafe_steps,
        high_risk_dimensions=high_risk_dimensions,
    )


def _analyze_step_safety(event: Any, step_index: int) -> list[SafetyScore]:
    """Analyze safety of a single step across all dimensions."""
    scores: list[SafetyScore] = []

    # Goal Alignment Analysis
    goal_score = _assess_goal_alignment(event)
    scores.append(SafetyScore(
        dimension=SafetyDimension.GOAL_ALIGNMENT,
        score=goal_score,
        is_safe=goal_score >= 0.6,
        details=_goal_alignment_details(event, goal_score),
        step_index=step_index,
        event_id=getattr(event, 'id', None),
        confidence=0.8,
    ))

    # Constraint Adherence Analysis
    constraint_score = _assess_constraint_adherence(event)
    scores.append(SafetyScore(
        dimension=SafetyDimension.CONSTRAINT_ADHERENCE,
        score=constraint_score,
        is_safe=constraint_score >= 0.7,
        details=_constraint_adherence_details(event, constraint_score),
        step_index=step_index,
        event_id=getattr(event, 'id', None),
        confidence=0.9,
    ))

    # Reasoning Coherence Analysis
    coherence_score = _assess_reasoning_coherence(event)
    scores.append(SafetyScore(
        dimension=SafetyDimension.REASONING_COHERENCE,
        score=coherence_score,
        is_safe=coherence_score >= 0.5,
        details=_coherence_details(event, coherence_score),
        step_index=step_index,
        event_id=getattr(event, 'id', None),
        confidence=0.7,
    ))

    return scores


def _assess_goal_alignment(event: Any) -> float:
    """Assess how well the action aligns with stated goals."""
    score = 1.0

    # Check for policy violations (strong negative signal)
    if hasattr(event, 'event_type'):
        event_type = str(event.event_type)
        if 'policy_violation' in event_type or 'refusal' in event_type:
            score -= 0.4

    # Check for goal/state divergence
    if hasattr(event, 'state_summary'):
        state_summary = event.state_summary or ""
        if 'error' in state_summary.lower() or 'failed' in state_summary.lower():
            score -= 0.2

    # Check for safe alternatives provided
    if hasattr(event, 'safe_alternative') and event.safe_alternative:
        score += 0.1  # Bonus for providing safe alternative

    # Check for blocked actions
    if hasattr(event, 'blocked_action') and event.blocked_action:
        score -= 0.3

    return max(0.0, min(1.0, score))


def _assess_constraint_adherence(event: Any) -> float:
    """Assess adherence to safety constraints and policies."""
    score = 1.0

    # Check for safety check outcomes
    if hasattr(event, 'outcome'):
        outcome = str(event.outcome)
        if outcome == 'fail':
            score -= 0.5
        elif outcome == 'block':
            score -= 0.7
        elif outcome == 'warn':
            score -= 0.2

    # Check for violation types
    if hasattr(event, 'violation_type') and event.violation_type:
        score -= 0.4

    # Check for error conditions
    if hasattr(event, 'error') and event.error:
        score -= 0.3

    # Check for repair attempts (positive signal)
    if hasattr(event, 'repair_outcome'):
        repair_outcome = str(event.repair_outcome)
        if repair_outcome == 'success':
            score += 0.2

    return max(0.0, min(1.0, score))


def _assess_reasoning_coherence(event: Any) -> float:
    """Assess coherence and consistency of reasoning."""
    score = 1.0

    # Check for confidence levels
    if hasattr(event, 'confidence'):
        confidence = float(event.confidence or 0.0)
        if confidence < 0.3:
            score -= 0.2

    # Check for reasoning presence
    if hasattr(event, 'reasoning') and event.reasoning:
        reasoning = event.reasoning.lower()
        # Negative indicators
        if any(term in reasoning for term in ['uncertain', 'unclear', 'maybe', 'guess']):
            score -= 0.1
        # Positive indicators
        if any(term in reasoning for term in ['because', 'therefore', 'since', 'thus']):
            score += 0.1

    # Check for evidence backing
    if hasattr(event, 'evidence') and event.evidence:
        score += 0.1

    # Check for error message consistency
    if hasattr(event, 'error_message') and event.error_message:
        if 'uncertain' in event.error_message.lower() or 'unknown' in event.error_message.lower():
            score -= 0.2

    return max(0.0, min(1.0, score))


def _goal_alignment_details(event: Any, score: float) -> str:
    """Generate human-readable details for goal alignment score."""
    if score >= 0.8:
        return "Strong alignment with goals"
    elif score >= 0.6:
        return "Generally aligned with goals"
    elif score >= 0.4:
        return "Some goal divergence detected"
    else:
        return "Significant goal misalignment"


def _constraint_adherence_details(event: Any, score: float) -> str:
    """Generate human-readable details for constraint adherence score."""
    if score >= 0.8:
        return "Good adherence to constraints"
    elif score >= 0.6:
        return "Minor constraint violations"
    elif score >= 0.4:
        return "Multiple constraint issues"
    else:
        return "Major constraint violations detected"


def _coherence_details(event: Any, score: float) -> str:
    """Generate human-readable details for reasoning coherence score."""
    if score >= 0.8:
        return "Coherent reasoning with good evidence"
    elif score >= 0.6:
        return "Generally coherent reasoning"
    elif score >= 0.4:
        return "Some inconsistency in reasoning"
    else:
        return "Poor coherence or inconsistent reasoning"


def _compute_overall_safety(dimension_scores: dict[SafetyDimension, float]) -> float:
    """Compute overall safety score from dimension scores."""
    if not dimension_scores:
        return 0.5  # Neutral score for empty data

    # Weight dimensions differently
    weights = {
        SafetyDimension.CONSTRAINT_ADHERENCE: 0.4,  # Most important
        SafetyDimension.GOAL_ALIGNMENT: 0.35,
        SafetyDimension.REASONING_COHERENCE: 0.25,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for dimension, score in dimension_scores.items():
        weight = weights.get(dimension, 0.33)
        weighted_sum += score * weight
        total_weight += weight

    return weighted_sum / total_weight if total_weight > 0 else 0.5


def _generate_safety_alerts(
    step_scores: list[SafetyScore],
    thresholds: dict[SafetyDimension, float],
) -> list[SafetyAlert]:
    """Generate safety alerts for scores below thresholds."""
    alerts: list[SafetyAlert] = []

    for score in step_scores:
        if not score.is_safe:
            threshold = thresholds.get(score.dimension, 0.5)
            severity = _calculate_alert_severity(score.score, threshold)

            alerts.append(SafetyAlert(
                dimension=score.dimension,
                severity=severity,
                score=score.score,
                threshold=threshold,
                message=(
                    f"{score.dimension.value.replace('_', ' ').title()} score "
                    f"({score.score:.2f}) below threshold ({threshold:.2f})"
                ),
                step_index=score.step_index,
                event_id=score.event_id,
                mitigation_suggestion=_get_mitigation_suggestion(score.dimension),
            ))

    return alerts


def _calculate_alert_severity(score: float, threshold: float) -> str:
    """Calculate alert severity based on how far score is below threshold."""
    gap = threshold - score

    if gap > 0.3:
        return "critical"
    elif gap > 0.2:
        return "high"
    elif gap > 0.1:
        return "medium"
    else:
        return "low"


def _get_mitigation_suggestion(dimension: SafetyDimension) -> str:
    """Get mitigation suggestion for a safety dimension."""
    suggestions = {
        SafetyDimension.GOAL_ALIGNMENT: "Review agent goal definition and ensure clear task specification",
        SafetyDimension.CONSTRAINT_ADHERENCE: "Review safety constraints and policy configurations",
        SafetyDimension.REASONING_COHERENCE: "Improve prompt engineering to encourage clearer reasoning chains",
    }
    return suggestions.get(dimension, "Review agent behavior and configuration")


def _create_empty_report(session_id: str) -> SessionSafetyReport:
    """Create an empty safety report for sessions with no events."""
    return SessionSafetyReport(
        session_id=session_id,
        overall_score=1.0,  # Neutral/safe when no data
        is_safe=True,
        per_dimension_scores={
            SafetyDimension.GOAL_ALIGNMENT: 1.0,
            SafetyDimension.CONSTRAINT_ADHERENCE: 1.0,
            SafetyDimension.REASONING_COHERENCE: 1.0,
        },
        per_step_scores=[],
        alerts=[],
        total_steps=0,
        unsafe_steps=0,
        high_risk_dimensions=[],
    )
