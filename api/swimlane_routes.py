"""Multi-agent swimlane debugger API routes.

Provides endpoints for swimlane visualization, message flow tracing,
coordination analysis, and emergent behavior detection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from agent_debugger_sdk.core.swimlane import (
    EmergentBehavior,
    IssueReport,
    analyze_multi_agent_session,
    detect_coordination_issues,
    detect_emergent_behaviors,
    get_message_flows,
    get_swimlane_data,
)
from api.dependencies import get_repository
from api.services import (
    load_session_artifacts,
    require_session,
)
from storage import TraceRepository

router = APIRouter(tags=["swimlane"])


@router.get("/api/sessions/{session_id}/swimlane")
async def get_swimlane_visualization(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get swimlane visualization data for a multi-agent session.

    Returns horizontal swimlanes for each agent with their temporal
    event sequences and inter-agent communication flows.

    Args:
        session_id: Session identifier

    Returns:
        Swimlane data with lanes, events, and message flows
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Generate swimlane data
    swimlane_data = get_swimlane_data(session_id, events)

    return {
        "session_id": session_id,
        "swimlane_data": swimlane_data,
    }


@router.get("/api/sessions/{session_id}/messages")
async def get_inter_agent_messages(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get inter-agent message flows for a session.

    Returns detailed message flow information showing communication
    patterns between agents.

    Args:
        session_id: Session identifier

    Returns:
        Message flow data with flows between agents
    """
    # Verify session exists
    await require_session(repo, session_id)

    # Load events
    events, _ = await load_session_artifacts(repo, session_id)

    # Get message flows
    message_flows = get_message_flows(session_id, events)

    # Analyze flow patterns
    flow_summary = _analyze_message_flows(message_flows)

    return {
        "session_id": session_id,
        "message_flows": message_flows,
        "flow_summary": flow_summary,
    }


@router.post("/api/sessions/{session_id}/coordination-analysis")
async def analyze_coordination(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Detect coordination issues in a multi-agent session.

    Analyzes agent interactions to detect deadlocks, communication gaps,
    circular dependencies, and other coordination problems.

    Args:
        session_id: Session identifier

    Returns:
        Coordination analysis with detected issues and suggestions
    """
    # Load session and events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Build multi-agent session
    session = analyze_multi_agent_session(events)
    session.session_id = session_id

    # Detect coordination issues
    issues = detect_coordination_issues(session)

    # Generate summary
    summary = _generate_coordination_summary(issues)

    return {
        "session_id": session_id,
        "coordination_issues": [issue.to_dict() for issue in issues],
        "summary": summary,
    }


@router.post("/api/sessions/{session_id}/emergent-behaviors")
async def analyze_emergent_behaviors(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Detect emergent behaviors in a multi-agent session.

    Analyzes agent interactions to detect behaviors that emerge from
    collective dynamics rather than individual agent design.

    Args:
        session_id: Session identifier

    Returns:
        Emergent behavior analysis with detected behaviors
    """
    # Load session and events
    await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Build multi-agent session
    session = analyze_multi_agent_session(events)
    session.session_id = session_id

    # Detect emergent behaviors
    behaviors = detect_emergent_behaviors(session)

    # Generate summary
    summary = _generate_emergent_behavior_summary(behaviors)

    return {
        "session_id": session_id,
        "emergent_behaviors": [behavior.to_dict() for behavior in behaviors],
        "summary": summary,
    }


@router.get("/api/sessions/{session_id}/multi-agent-analysis")
async def get_multi_agent_analysis(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get comprehensive multi-agent analysis for a session.

    Combines swimlane visualization, message flows, coordination analysis,
    and emergent behavior detection into a single comprehensive response.

    Args:
        session_id: Session identifier

    Returns:
        Comprehensive multi-agent analysis
    """
    # Load session and events
    session = await require_session(repo, session_id)
    events, _ = await load_session_artifacts(repo, session_id)

    # Build multi-agent session
    multi_session = analyze_multi_agent_session(events)
    multi_session.session_id = session_id

    # Run all analyses
    coordination_issues = detect_coordination_issues(multi_session)
    emergent_behaviors = detect_emergent_behaviors(multi_session)

    # Generate summaries
    coordination_summary = _generate_coordination_summary(coordination_issues)
    emergent_summary = _generate_emergent_behavior_summary(emergent_behaviors)

    return {
        "session_id": session_id,
        "session_info": {
            "agent_name": session.agent_name,
            "framework": session.framework,
            "started_at": session.started_at,
            "status": session.status,
        },
        "swimlane_data": multi_session.to_dict(),
        "coordination_analysis": {
            "issues": [issue.to_dict() for issue in coordination_issues],
            "summary": coordination_summary,
        },
        "emergent_behavior_analysis": {
            "behaviors": [behavior.to_dict() for behavior in emergent_behaviors],
            "summary": emergent_summary,
        },
    }


# =============================================================================
# Internal helper functions
# =============================================================================


def _analyze_message_flows(message_flows: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze message flow patterns.

    Args:
        message_flows: List of message flow dictionaries

    Returns:
        Flow analysis summary
    """
    if not message_flows:
        return {
            "total_flows": 0,
            "flow_types": {},
            "agent_pairs": {},
            "most_active_pair": None,
        }

    # Count flows by type
    flow_types: dict[str, int] = {}
    agent_pairs: dict[str, int] = {}

    for flow in message_flows:
        flow_type = flow.get("flow_type", "unknown")
        flow_types[flow_type] = flow_types.get(flow_type, 0) + 1

        # Track agent pairs
        from_agent = flow.get("from_agent_id", "")
        to_agent = flow.get("to_agent_id", "")
        if from_agent and to_agent:
            pair_key = f"{from_agent}->{to_agent}"
            agent_pairs[pair_key] = agent_pairs.get(pair_key, 0) + 1

    # Find most active pair
    most_active_pair = None
    if agent_pairs:
        most_active_pair = max(agent_pairs.items(), key=lambda x: x[1])

    return {
        "total_flows": len(message_flows),
        "flow_types": flow_types,
        "agent_pairs": agent_pairs,
        "most_active_pair": {
            "pair": most_active_pair[0] if most_active_pair else None,
            "count": most_active_pair[1] if most_active_pair else 0,
        } if most_active_pair else None,
    }


def _generate_coordination_summary(issues: list[IssueReport]) -> dict[str, Any]:
    """Generate coordination analysis summary.

    Args:
        issues: List of coordination issues

    Returns:
        Summary statistics and breakdown
    """
    if not issues:
        return {
            "total_issues": 0,
            "by_severity": {},
            "by_type": {},
            "critical_issues": [],
        }

    # Count by severity and type
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for issue in issues:
        severity = str(issue.severity)
        issue_type = str(issue.issue_type)

        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_type[issue_type] = by_type.get(issue_type, 0) + 1

    # Extract critical issues
    critical_issues = [
        issue.to_dict() for issue in issues
        if issue.severity.value == "critical"
    ]

    return {
        "total_issues": len(issues),
        "by_severity": by_severity,
        "by_type": by_type,
        "critical_issues": critical_issues,
    }


def _generate_emergent_behavior_summary(behaviors: list[EmergentBehavior]) -> dict[str, Any]:
    """Generate emergent behavior analysis summary.

    Args:
        behaviors: List of emergent behaviors

    Returns:
        Summary statistics and breakdown
    """
    if not behaviors:
        return {
            "total_behaviors": 0,
            "by_type": {},
            "high_confidence_behaviors": [],
            "avg_confidence": 0.0,
        }

    # Count by type
    by_type: dict[str, int] = {}

    total_confidence = 0.0
    for behavior in behaviors:
        behavior_type = str(behavior.behavior_type)
        by_type[behavior_type] = by_type.get(behavior_type, 0) + 1
        total_confidence += behavior.confidence

    # Extract high confidence behaviors
    high_confidence = [
        behavior.to_dict() for behavior in behaviors
        if behavior.confidence >= 0.7
    ]

    return {
        "total_behaviors": len(behaviors),
        "by_type": by_type,
        "high_confidence_behaviors": high_confidence,
        "avg_confidence": total_confidence / len(behaviors) if behaviors else 0.0,
    }
