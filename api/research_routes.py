"""Research feature API routes.

Provides endpoints for three research-inspired features:
1. Frame Lifetime Trace (function-level tracing) - #197
2. Backward Failure Attribution (ErrorProbe) - #186
3. Conformal Prediction Scoring (CROP) - #185

The computation lives in :mod:`api.services.research`; these handlers only
resolve the session and shape the HTTP response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_repository
from api.services import require_session
from api.services.research import (
    build_frame_tree,
    build_frames_report,
    build_prediction_intervals,
    build_risk_assessment,
    build_uncertainty_report,
)
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
    events = await repo.get_event_tree(session_id)
    return build_frames_report(session_id, events)


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
    return {"session_id": session_id, "tree": build_frame_tree(events)}


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
    return build_uncertainty_report(session_id, events)


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
    return build_prediction_intervals(session_id, events, confidence_level)


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
    return build_risk_assessment(session_id, events)
