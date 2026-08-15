"""Safety and redundancy analysis services."""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent
from storage import TraceRepository

logger = logging.getLogger(__name__)

def analyze_session_safety_report(
    events: list[TraceEvent],
    session_id: str,
    *,
    custom_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive safety analysis report for a session.

    Args:
        events: List of trace events from the session
        session_id: Session ID to analyze
        custom_thresholds: Optional custom safety thresholds per dimension

    Returns:
        Dictionary containing safety report data
    """
    from agent_debugger_sdk.core import SafetyDimension, analyze_session_safety

    # Convert custom thresholds if provided
    thresholds = None
    if custom_thresholds:
        thresholds = {
            SafetyDimension(dim): score
            for dim, score in custom_thresholds.items()
        }

    # Generate safety report
    safety_report = analyze_session_safety(
        session_id=session_id,
        events=events,
        thresholds=thresholds,
    )

    return {
        "session_id": session_id,
        "safety_report": safety_report.to_dict(),
    }


async def analyze_redundancy(
    repo: TraceRepository,
    session_id: str,
) -> dict[str, Any]:
    """Analyze a session for redundant, harmful, and essential steps.

    Args:
        repo: Trace repository
        session_id: Session ID to analyze

    Returns:
        Dict with session_id, scores (list of RedundancyScore), and summary stats
    """
    from agent_debugger_sdk.core import calculate_session_redundancy_summary, score_session

    # Load session events
    events = await repo.get_event_tree(session_id)

    if not events:
        return {
            "session_id": session_id,
            "scores": [],
            "summary": {
                "total_steps": 0,
                "essential_count": 0,
                "redundant_count": 0,
                "harmful_count": 0,
                "unknown_count": 0,
                "avg_score": 0.0,
                "redundancy_rate": 0.0,
            },
        }

    # Score each step for redundancy
    scores = score_session(events)

    # Calculate summary statistics
    summary = calculate_session_redundancy_summary(scores)

    return {
        "session_id": session_id,
        "scores": [score.to_dict() for score in scores],
        "summary": summary,
    }
