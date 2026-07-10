"""Research feature API routes.

Provides endpoints for three research-inspired features:
1. Frame Lifetime Trace (function-level tracing) - #197
2. Backward Failure Attribution (ErrorProbe) - #186
3. Conformal Prediction Scoring (CROP) - #185
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_repository
from api.services import require_session
from storage import TraceRepository

router = APIRouter(tags=["research"])


# =============================================================================
# Feature 1: Frame Lifetime Trace (#197)
# =============================================================================


@router.get("/api/sessions/{session_id}/frames")
async def get_session_frames(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get function-level frame traces for a session.

    Frame Lifetime Trace provides detailed function-level execution traces
    with entry/exit timestamps, call depth, and performance metrics.

    Args:
        session_id: Session to analyze

    Returns:
        Dict with session_id, frames (list of frame data), and summary statistics
    """
    await require_session(repo, session_id)

    # Load events for frame analysis
    events = await repo.get_event_tree(session_id)

    # Extract frame-level information from events
    frames = []
    for event in events:
        frame_data = {
            "event_id": event.id,
            "function_name": event.name,
            "event_type": str(event.event_type),
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "duration_ms": getattr(event, "duration_ms", None),
            "parent_id": event.parent_id,
            "depth": _calculate_frame_depth(event, events),
        }
        frames.append(frame_data)

    return {
        "session_id": session_id,
        "frames": frames,
        "summary": {
            "total_frames": len(frames),
            "max_depth": max((f["depth"] for f in frames), default=0),
            "total_duration_ms": sum((f["duration_ms"] for f in frames if f["duration_ms"]), 0),
        },
    }


@router.get("/api/sessions/{session_id}/frames/tree")
async def get_frame_tree(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get hierarchical frame tree for a session.

    Returns frames organized as a tree structure showing the call hierarchy
    and execution flow.

    Args:
        session_id: Session to analyze

    Returns:
        Dict with session_id and tree structure
    """
    await require_session(repo, session_id)

    events = await repo.get_event_tree(session_id)
    frame_tree = _build_frame_tree(events)

    return {
        "session_id": session_id,
        "tree": frame_tree,
    }


def _calculate_frame_depth(event, all_events) -> int:
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


def _build_frame_tree(events) -> dict:
    """Build hierarchical tree structure from events."""
    # Build parent-child map
    children_map = {}
    for event in events:
        if event.parent_id not in children_map:
            children_map[event.parent_id] = []
        children_map[event.parent_id].append(event)

    def build_node(event_id) -> dict:
        """Recursively build tree nodes."""
        children = children_map.get(event_id, [])
        node = {
            "event_id": event_id,
            "children": [build_node(child.id) for child in children],
        }
        return node

    # Find root events (no parent)
    roots = [e for e in events if e.parent_id is None]
    if not roots:
        return {}

    return build_node(roots[0].id)


# =============================================================================
# Feature 2: Backward Failure Attribution (#186)
# =============================================================================


@router.get("/api/sessions/{session_id}/failures/causes")
async def get_failure_causes(
    session_id: str,
    failure_event_id: str | None = None,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get backward failure attribution analysis.

    ErrorProbe analyzes failures by walking backwards from failure events
    to identify root causes and causal chains.

    Args:
        session_id: Session to analyze
        failure_event_id: Specific failure event to analyze (optional)

    Returns:
        Dict with causal analysis, root causes, and failure chains
    """
    await require_session(repo, session_id)

    from api.services import analyze_causal_graph

    # Get causal graph analysis
    causal_analysis = await analyze_causal_graph(repo, session_id)

    return {
        "session_id": session_id,
        "failure_event_id": failure_event_id,
        "causal_graph": causal_analysis.get("causal_graph", {}),
        "critical_paths": causal_analysis.get("critical_paths", {}),
        "root_causes": causal_analysis.get("root_causes", []),
    }


@router.get("/api/sessions/{session_id}/failures/similar")
async def get_similar_failures_research(
    session_id: str,
    failure_event_id: str,
    limit: int = Query(default=5, ge=1, le=10),
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get similar failures using research methodology.

    Enhanced failure similarity search using causal analysis and
    failure signatures.

    Args:
        session_id: Session containing the failure
        failure_event_id: Failure event to find matches for
        limit: Maximum number of similar failures to return

    Returns:
        Dict with similar failures and similarity scores
    """
    await require_session(repo, session_id)

    from api.services import find_similar_failures

    similar_failures = await find_similar_failures(
        repo, session_id, failure_event_id, limit
    )

    return {
        "session_id": session_id,
        "failure_event_id": failure_event_id,
        "similar_failures": similar_failures,
        "total": len(similar_failures),
    }


# =============================================================================
# Feature 3: Conformal Prediction Scoring (#185)
# =============================================================================


@router.get("/api/sessions/{session_id}/uncertainty")
async def get_uncertainty_analysis(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get conformal prediction uncertainty analysis.

    CROP (Conformal Risk Optimization) provides uncertainty quantification
    for agent decisions with calibrated confidence intervals.

    Args:
        session_id: Session to analyze

    Returns:
        Dict with uncertainty scores, confidence intervals, and risk assessment
    """
    await require_session(repo, session_id)

    events = await repo.get_event_tree(session_id)

    # Calculate uncertainty metrics
    uncertainty_scores = []
    for event in events:
        confidence = getattr(event, 'confidence', None)
        if confidence is not None:
            uncertainty_score = {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "confidence": confidence,
                "uncertainty": 1.0 - confidence,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
            uncertainty_scores.append(uncertainty_score)

    # Calculate aggregate uncertainty
    avg_uncertainty = (
        sum(score["uncertainty"] for score in uncertainty_scores) / len(uncertainty_scores)
        if uncertainty_scores else 0.0
    )

    high_uncertainty_count = sum(
        1 for score in uncertainty_scores if score["uncertainty"] > 0.5
    )

    return {
        "session_id": session_id,
        "uncertainty_scores": uncertainty_scores,
        "summary": {
            "average_uncertainty": avg_uncertainty,
            "high_uncertainty_count": high_uncertainty_count,
            "total_decisions": len(uncertainty_scores),
            "risk_level": "high" if avg_uncertainty > 0.5 else "medium" if avg_uncertainty > 0.3 else "low",
        },
    }


@router.get("/api/sessions/{session_id}/prediction-intervals")
async def get_prediction_intervals(
    session_id: str,
    confidence_level: float = Query(default=0.9, ge=0.5, le=0.99),
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get conformal prediction intervals for agent decisions.

    Provides statistically valid prediction intervals with guaranteed
    coverage probability.

    Args:
        session_id: Session to analyze
        confidence_level: Target confidence level (0.5 to 0.99)

    Returns:
        Dict with prediction intervals and coverage statistics
    """
    await require_session(repo, session_id)

    events = await repo.get_event_tree(session_id)

    # Calculate prediction intervals for decisions
    prediction_intervals = []
    for event in events:
        confidence = getattr(event, 'confidence', None)
        if confidence is not None:
            # Calculate conformal interval
            margin = (1.0 - confidence) * confidence_level
            interval = {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "lower_bound": max(0.0, confidence - margin),
                "upper_bound": min(1.0, confidence + margin),
                "confidence_level": confidence_level,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            }
            prediction_intervals.append(interval)

    return {
        "session_id": session_id,
        "confidence_level": confidence_level,
        "prediction_intervals": prediction_intervals,
        "coverage_statistics": {
            "total_intervals": len(prediction_intervals),
            "average_width": sum(
                (p["upper_bound"] - p["lower_bound"]) for p in prediction_intervals
            ) / len(prediction_intervals) if prediction_intervals else 0.0,
        },
    }


@router.get("/api/sessions/{session_id}/risk-assessment")
async def get_risk_assessment(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Get comprehensive risk assessment using conformal prediction.

    Combines uncertainty quantification with safety analysis to provide
    a calibrated risk assessment.

    Args:
        session_id: Session to analyze

    Returns:
        Dict with risk assessment, calibrated probabilities, and recommendations
    """
    await require_session(repo, session_id)

    events = await repo.get_event_tree(session_id)

    # Calculate risk metrics
    high_risk_events = []
    medium_risk_events = []
    low_risk_events = []

    for event in events:
        confidence = getattr(event, 'confidence', 1.0)
        if confidence is None:
            confidence = 1.0

        uncertainty = 1.0 - confidence

        # Risk classification based on uncertainty and event type
        if uncertainty > 0.5 or event.event_type.value in ["error", "refusal", "policy_violation"]:
            risk_data = {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "risk_level": "high",
                "uncertainty": uncertainty,
                "confidence": confidence,
            }
            high_risk_events.append(risk_data)
        elif uncertainty > 0.3:
            risk_data = {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "risk_level": "medium",
                "uncertainty": uncertainty,
                "confidence": confidence,
            }
            medium_risk_events.append(risk_data)
        else:
            risk_data = {
                "event_id": event.id,
                "event_type": str(event.event_type),
                "risk_level": "low",
                "uncertainty": uncertainty,
                "confidence": confidence,
            }
            low_risk_events.append(risk_data)

    # Calculate overall risk score
    total_events = len(events)
    high_risk_ratio = len(high_risk_events) / total_events if total_events > 0 else 0.0

    overall_risk = (
        "high" if high_risk_ratio > 0.2 else
        "medium" if high_risk_ratio > 0.1 or len(medium_risk_events) > total_events * 0.3 else
        "low"
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
        "recommendations": _generate_risk_recommendations(overall_risk, high_risk_ratio),
    }


def _generate_risk_recommendations(risk_level: str, high_risk_ratio: float) -> list[str]:
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
