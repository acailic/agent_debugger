"""Research-feature computation services.

Pure functions behind the research endpoints (frame lifetime traces,
conformal uncertainty scoring, risk assessment). Kept deterministic and
side-effect free so they can be unit-tested without a database.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent

logger = logging.getLogger(__name__)

HIGH_UNCERTAINTY_BOUND = 0.5
MEDIUM_UNCERTAINTY_BOUND = 0.3
HIGH_RISK_EVENT_TYPES = {"error", "refusal", "policy_violation"}


def calculate_frame_depth(event: TraceEvent, all_events: list[TraceEvent]) -> int:
    """Calculate the depth of a frame in the call hierarchy."""
    depth = 0
    current = event
    while current.parent_id:
        parent = next((e for e in all_events if e.id == current.parent_id), None)
        if not parent:
            break
        depth += 1
        current = parent
    return depth


def build_frame_tree(events: list[TraceEvent]) -> dict[str, Any]:
    """Build hierarchical tree structure from events."""
    children_map: dict[str | None, list[TraceEvent]] = {}
    for event in events:
        children_map.setdefault(event.parent_id, []).append(event)

    def build_node(event_id: str) -> dict[str, Any]:
        children = children_map.get(event_id, [])
        return {
            "event_id": event_id,
            "children": [build_node(child.id) for child in children],
        }

    roots = [e for e in events if e.parent_id is None]
    if not roots:
        return {}

    return build_node(roots[0].id)


def build_frames_report(session_id: str, events: list[TraceEvent]) -> dict[str, Any]:
    """Build the frame-lifetime-trace report for a session."""
    frames = []
    for event in events:
        frames.append(
            {
                "event_id": event.id,
                "function_name": event.name,
                "event_type": str(event.event_type),
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "duration_ms": getattr(event, "duration_ms", None),
                "parent_id": event.parent_id,
                "depth": calculate_frame_depth(event, events),
            }
        )

    return {
        "session_id": session_id,
        "frames": frames,
        "summary": {
            "total_frames": len(frames),
            "max_depth": max((f["depth"] for f in frames), default=0),
            "total_duration_ms": sum(
                (f["duration_ms"] for f in frames if f["duration_ms"]), 0
            ),
        },
    }


def build_uncertainty_report(session_id: str, events: list[TraceEvent]) -> dict[str, Any]:
    """Build the conformal uncertainty analysis for a session."""
    uncertainty_scores = []
    for event in events:
        confidence = getattr(event, "confidence", None)
        if confidence is not None:
            uncertainty_scores.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "confidence": confidence,
                    "uncertainty": 1.0 - confidence,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                }
            )

    avg_uncertainty = (
        sum(score["uncertainty"] for score in uncertainty_scores) / len(uncertainty_scores)
        if uncertainty_scores
        else 0.0
    )
    high_uncertainty_count = sum(
        1 for score in uncertainty_scores if score["uncertainty"] > HIGH_UNCERTAINTY_BOUND
    )

    return {
        "session_id": session_id,
        "uncertainty_scores": uncertainty_scores,
        "summary": {
            "average_uncertainty": avg_uncertainty,
            "high_uncertainty_count": high_uncertainty_count,
            "total_decisions": len(uncertainty_scores),
            "risk_level": (
                "high"
                if avg_uncertainty > HIGH_UNCERTAINTY_BOUND
                else "medium"
                if avg_uncertainty > MEDIUM_UNCERTAINTY_BOUND
                else "low"
            ),
        },
    }


def build_prediction_intervals(
    session_id: str,
    events: list[TraceEvent],
    confidence_level: float,
) -> dict[str, Any]:
    """Build conformal prediction intervals for a session's decisions."""
    prediction_intervals = []
    for event in events:
        confidence = getattr(event, "confidence", None)
        if confidence is not None:
            margin = (1.0 - confidence) * confidence_level
            prediction_intervals.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "lower_bound": max(0.0, confidence - margin),
                    "upper_bound": min(1.0, confidence + margin),
                    "confidence_level": confidence_level,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                }
            )

    return {
        "session_id": session_id,
        "confidence_level": confidence_level,
        "prediction_intervals": prediction_intervals,
        "coverage_statistics": {
            "total_intervals": len(prediction_intervals),
            "average_width": sum(
                (p["upper_bound"] - p["lower_bound"]) for p in prediction_intervals
            )
            / len(prediction_intervals)
            if prediction_intervals
            else 0.0,
        },
    }


def generate_risk_recommendations(risk_level: str, high_risk_ratio: float) -> list[str]:
    """Generate recommendations based on risk assessment."""
    recommendations = []

    if risk_level == "high":
        recommendations.append("Review high-uncertainty decisions before deployment")
        recommendations.append("Consider additional validation or human review")
        recommendations.append("Investigate failure patterns in similar sessions")
    elif risk_level == "medium":
        recommendations.append("Monitor decision confidence trends")
        recommendations.append("Review medium-risk events for potential improvements")
    else:
        recommendations.append("Session appears low-risk, continue normal operations")
        recommendations.append("Maintain current decision patterns")

    if high_risk_ratio > 0.15:
        recommendations.append("High proportion of risky events detected - consider model retraining")

    return recommendations


def build_risk_assessment(session_id: str, events: list[TraceEvent]) -> dict[str, Any]:
    """Build the calibrated risk assessment for a session."""
    high_risk_events = []
    medium_risk_events = []
    low_risk_events = []

    for event in events:
        confidence = getattr(event, "confidence", 1.0)
        if confidence is None:
            confidence = 1.0

        uncertainty = 1.0 - confidence

        if (
            uncertainty > HIGH_UNCERTAINTY_BOUND
            or event.event_type.value in HIGH_RISK_EVENT_TYPES
        ):
            risk_bucket = high_risk_events
        elif uncertainty > MEDIUM_UNCERTAINTY_BOUND:
            risk_bucket = medium_risk_events
        else:
            risk_bucket = low_risk_events

        risk_bucket.append(
            {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "risk_level": "high" if risk_bucket is high_risk_events
                else "medium" if risk_bucket is medium_risk_events
                else "low",
                "uncertainty": uncertainty,
                "confidence": confidence,
            }
        )

    total_events = len(events)
    high_risk_ratio = len(high_risk_events) / total_events if total_events > 0 else 0.0

    overall_risk = (
        "high"
        if high_risk_ratio > 0.2
        else "medium"
        if high_risk_ratio > 0.1 or len(medium_risk_events) > total_events * 0.3
        else "low"
    )

    return {
        "session_id": session_id,
        "overall_risk": overall_risk,
        "risk_distribution": {
            "high": len(high_risk_events),
            "medium": len(medium_risk_events),
            "low": len(low_risk_events),
        },
        "high_risk_events": high_risk_events[:10],  # Limit to top 10
        "recommendations": generate_risk_recommendations(overall_risk, high_risk_ratio),
    }
