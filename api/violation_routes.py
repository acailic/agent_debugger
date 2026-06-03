"""Violation detection API routes for cross-trace analysis.

Provides endpoints for detecting violations across multiple agent sessions,
including clustering, search, and sparse failure detection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.params import Query as FastAPIQuery

from agent_debugger_sdk.core.violation_detector import (
    cluster_sessions,
    compute_session_embedding,
    detect_sparse_failures,
    search_violations_across_traces,
)
from api.dependencies import get_repository
from api.services import (
    load_session_artifacts,
)
from storage import TraceRepository

router = APIRouter(tags=["violations"])


def _resolve_param(value: Any) -> Any:
    """Resolve a parameter value, handling FastAPI Query objects.

    When endpoints are called directly (not through HTTP), Query() defaults
    are not resolved and remain as Query objects. This helper extracts the
    actual default value in those cases.

    Args:
        value: The parameter value (might be a Query object)

    Returns:
        The actual value to use
    """
    if isinstance(value, FastAPIQuery):
        return value.default
    return value


@router.post("/api/violations/cluster")
async def cluster_sessions_endpoint(
    agent_name: str | None = Query(None, description="Filter by agent name"),
    session_ids: list[str] | None = Query(None, description="Specific session IDs to cluster"),
    similarity_threshold: float = Query(0.7, description="Minimum similarity for clustering"),
    min_cluster_size: int = Query(2, description="Minimum sessions per cluster"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Cluster sessions and identify outliers.

    Groups similar agent sessions and identifies behavioral outliers
    that may indicate violations or unusual behavior.

    Args:
        agent_name: Optional filter by agent name
        session_ids: Optional list of specific session IDs
        similarity_threshold: Minimum similarity for clustering (0.0-1.0)
        min_cluster_size: Minimum sessions to form a cluster

    Returns:
        Clustering results with session groups and outliers
    """
    # Load sessions
    # Resolve parameters (handle Query objects from direct calls)
    resolved_agent_name = _resolve_param(agent_name)
    resolved_session_ids = _resolve_param(session_ids)

    if resolved_session_ids is not None:
        sessions_to_load = resolved_session_ids
    else:
        # List sessions, optionally filtered by agent
        all_sessions = await repo.list_sessions(
            agent_name=resolved_agent_name,
            limit=100,
        )
        sessions_to_load = [s.id for s in all_sessions]

    # Load events for each session
    sessions_data: dict[str, list[Any]] = {}
    for session_id in sessions_to_load:
        try:
            events, _ = await load_session_artifacts(repo, session_id)
            sessions_data[session_id] = events
        except Exception:
            # Skip sessions that fail to load
            continue

    if not sessions_data:
        return {
            "clusters": [],
            "outliers": [],
            "total_sessions_analyzed": 0,
            "message": "No sessions available for clustering",
        }

    # Perform clustering
    clusters = cluster_sessions(
        sessions=sessions_data,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )

    # Identify global outliers
    from agent_debugger_sdk.core.violation_detector import TraceClusterer

    clusterer = TraceClusterer(sessions_data)
    global_outliers = clusterer.identify_global_outliers()

    return {
        "clusters": [cluster.to_dict() for cluster in clusters],
        "global_outliers": global_outliers,
        "total_sessions_analyzed": len(sessions_data),
        "clustering_params": {
            "similarity_threshold": similarity_threshold,
            "min_cluster_size": min_cluster_size,
        },
    }


@router.post("/api/violations/search")
async def search_violations_endpoint(
    nl_query: str = Query(..., description="Natural language description of violation to search"),
    agent_name: str | None = Query(None, description="Filter by agent name"),
    session_ids: list[str] | None = Query(None, description="Specific session IDs to search"),
    max_results: int = Query(50, description="Maximum violation reports to return"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Search for NL violation description patterns across sessions.

    Searches through session traces for events matching a natural language
    description of a violation or pattern of concern.

    Args:
        nl_query: Natural language description (e.g., "unsafe data handling")
        agent_name: Optional filter by agent name
        session_ids: Optional list of specific session IDs
        max_results: Maximum number of violation reports

    Returns:
        Violation reports with supporting evidence from multiple traces
    """
    # Load sessions
    # Resolve parameters (handle Query objects from direct calls)
    resolved_agent_name = _resolve_param(agent_name)
    resolved_session_ids = _resolve_param(session_ids)

    if resolved_session_ids is not None:
        sessions_to_load = resolved_session_ids
    else:
        # List sessions, optionally filtered by agent
        all_sessions = await repo.list_sessions(
            agent_name=resolved_agent_name,
            limit=100,
        )
        sessions_to_load = [s.id for s in all_sessions]

    # Load events for each session
    sessions_data: dict[str, list[Any]] = {}
    for session_id in sessions_to_load:
        try:
            events, _ = await load_session_artifacts(repo, session_id)
            sessions_data[session_id] = events
        except Exception:
            # Skip sessions that fail to load
            continue

    if not sessions_data:
        return {
            "violations": [],
            "query": nl_query,
            "total_sessions_searched": 0,
            "message": "No sessions available for search",
        }

    # Search for violations
    violations = search_violations_across_traces(
        sessions=sessions_data,
        nl_query=nl_query,
        max_results=max_results,
    )

    return {
        "violations": [v.to_dict() for v in violations],
        "query": nl_query,
        "total_sessions_searched": len(sessions_data),
        "total_violations_found": len(violations),
    }


@router.get("/api/violations/sparse")
async def detect_sparse_failures_endpoint(
    agent_name: str | None = Query(None, description="Filter by agent name"),
    session_ids: list[str] | None = Query(None, description="Specific session IDs to analyze"),
    min_occurrences: int = Query(2, description="Minimum sessions showing pattern"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Detect sparse failures across multiple traces.

    Identifies failure patterns that are only visible when comparing
    multiple sessions together - failures that occur sporadically
    across traces but form a pattern when aggregated.

    Args:
        agent_name: Optional filter by agent name
        session_ids: Optional list of specific session IDs
        min_occurrences: Minimum sessions showing pattern to report

    Returns:
        Sparse failure patterns with cross-trace evidence
    """
    # Load sessions
    # Resolve parameters (handle Query objects from direct calls)
    resolved_agent_name = _resolve_param(agent_name)
    resolved_session_ids = _resolve_param(session_ids)

    if resolved_session_ids is not None:
        sessions_to_load = resolved_session_ids
    else:
        # List sessions, optionally filtered by agent
        all_sessions = await repo.list_sessions(
            agent_name=resolved_agent_name,
            limit=100,
        )
        sessions_to_load = [s.id for s in all_sessions]

    # Load events for each session
    sessions_data: dict[str, list[Any]] = {}
    for session_id in sessions_to_load:
        try:
            events, _ = await load_session_artifacts(repo, session_id)
            sessions_data[session_id] = events
        except Exception:
            # Skip sessions that fail to load
            continue

    if not sessions_data:
        return {
            "sparse_failures": [],
            "total_sessions_analyzed": 0,
            "total_patterns_found": 0,
            "min_occurrences": min_occurrences,
            "message": "No sessions available for analysis",
        }

    # Detect sparse failures
    sparse_failures = detect_sparse_failures(
        sessions=sessions_data,
        min_occurrences=min_occurrences,
    )

    return {
        "sparse_failures": [f.to_dict() for f in sparse_failures],
        "total_sessions_analyzed": len(sessions_data),
        "total_patterns_found": len(sparse_failures),
        "min_occurrences": min_occurrences,
    }


@router.get("/api/violations/{violation_id}")
async def get_violation_details(
    violation_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get detailed information about a specific violation.

    Args:
        violation_id: ID of the violation to retrieve

    Returns:
        Detailed violation information with full evidence
    """
    # Note: In a real implementation, you'd store violations in the database
    # For now, return a placeholder response
    return {
        "violation_id": violation_id,
        "message": "Violation details endpoint - implement persistent storage for full functionality",
        "note": "This endpoint requires violation persistence to be implemented",
    }


@router.get("/api/violations/dashboard")
async def get_violation_dashboard(
    agent_name: str | None = Query(None, description="Filter by agent name"),
    days: int = Query(7, description="Time range in days"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get violation dashboard summary.

    Provides a high-level summary of violations detected across sessions
    for dashboard display and monitoring.

    Args:
        agent_name: Optional filter by agent name
        days: Time range in days to analyze

    Returns:
        Dashboard summary with violation statistics and trends
    """
    # Resolve parameters
    resolved_agent_name = _resolve_param(agent_name)

    # List sessions from recent time period
    all_sessions = await repo.list_sessions(
        agent_name=resolved_agent_name,
        limit=200,
    )

    # Load events for analysis (limit to avoid overwhelming the API)
    sessions_data: dict[str, list[Any]] = {}
    for session in all_sessions[:50]:  # Limit to 50 sessions for dashboard
        try:
            events, _ = await load_session_artifacts(repo, session.id)
            sessions_data[session.id] = events
        except Exception:
            continue

    if not sessions_data:
        return {
            "total_sessions_analyzed": 0,
            "violation_summary": {
                "by_type": {},
                "by_severity": {},
                "total_violations": 0,
            },
            "cluster_summary": {
                "total_clusters": 0,
                "total_outliers": 0,
            },
            "sparse_failure_summary": {
                "total_patterns": 0,
                "most_common_failure_types": [],
            },
            "time_range_days": days,
        }

    # Perform analyses
    from agent_debugger_sdk.core.violation_detector import TraceClusterer

    clusterer = TraceClusterer(sessions_data)
    clusters = clusterer.cluster_sessions()
    outliers = clusterer.identify_global_outliers()

    sparse_failures = detect_sparse_failures(sessions_data)

    # Compute summary statistics
    violation_by_type: dict[str, int] = {}
    violation_by_severity: dict[str, int] = {}

    # Search for some common violation patterns
    common_queries = [
        "unsafe data handling",
        "performance issues",
        "error handling problems",
        "unusual behavior",
    ]

    for query in common_queries:
        violations = search_violations_across_traces(
            sessions=sessions_data,
            nl_query=query,
            max_results=10,
        )
        for v in violations:
            vtype = str(v.violation_type)
            vseverity = str(v.severity)
            violation_by_type[vtype] = violation_by_type.get(vtype, 0) + 1
            violation_by_severity[vseverity] = violation_by_severity.get(vseverity, 0) + 1

    # Get most common failure types
    failure_counter: dict[str, int] = {}
    for failure in sparse_failures:
        failure_type = failure.failure_type
        failure_counter[failure_type] = failure_counter.get(failure_type, 0) + len(failure.session_ids)

    most_common_failures = sorted(
        failure_counter.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "total_sessions_analyzed": len(sessions_data),
        "violation_summary": {
            "by_type": violation_by_type,
            "by_severity": violation_by_severity,
            "total_violations": sum(violation_by_type.values()),
        },
        "cluster_summary": {
            "total_clusters": len(clusters),
            "total_outliers": len(outliers),
            "average_cluster_size": sum(len(c.session_ids) for c in clusters) / len(clusters) if clusters else 0,
        },
        "sparse_failure_summary": {
            "total_patterns": len(sparse_failures),
            "most_common_failure_types": [
                {"failure_type": ft, "occurrence_count": count}
                for ft, count in most_common_failures
            ],
        },
        "time_range_days": days,
        "generated_at": "now",
    }


@router.get("/api/violations/session/{session_id}/embedding")
async def get_session_embedding(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get embedding for a specific session.

    Args:
        session_id: Session to compute embedding for

    Returns:
        Session embedding for similarity comparison
    """
    # Load session events
    events, _ = await load_session_artifacts(repo, session_id)

    # Compute embedding
    embedding = compute_session_embedding(session_id, events)

    return {
        "session_id": session_id,
        "embedding": embedding.to_dict(),
    }


@router.post("/api/violations/session/{session_id}/similar")
async def find_similar_sessions(
    session_id: str,
    limit: int = Query(10, description="Maximum similar sessions to return"),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Find sessions similar to a given session.

    Args:
        session_id: Reference session to find similarities for
        limit: Maximum similar sessions to return

    Returns:
        List of similar sessions with similarity scores
    """
    # Load reference session
    ref_events, _ = await load_session_artifacts(repo, session_id)
    ref_embedding = compute_session_embedding(session_id, ref_events)

    # Load other sessions
    all_sessions = await repo.list_sessions(limit=100)
    other_sessions = [s for s in all_sessions if s.id != session_id]

    similarities: list[dict[str, Any]] = []

    for session in other_sessions[:limit * 2]:  # Check more sessions to get top results
        try:
            events, _ = await load_session_artifacts(repo, session.id)
            embedding = compute_session_embedding(session.id, events)

            similarity = ref_embedding.similarity(embedding)

            similarities.append({
                "session_id": session.id,
                "agent_name": session.agent_name,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "similarity_score": similarity,
            })
        except Exception:
            continue

    # Sort by similarity and return top results
    similarities.sort(key=lambda x: x["similarity_score"], reverse=True)

    return {
        "reference_session_id": session_id,
        "similar_sessions": similarities[:limit],
        "total_compared": len(similarities),
    }
