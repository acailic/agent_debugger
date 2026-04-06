"""API routes for cross-session failure clustering.

Provides endpoints for querying failure clusters that span multiple sessions,
enabling identification of recurring issues and patterns.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api import app_context
from api.schemas import SessionSchema
from collector.clustering.cross_session import CrossSessionClusterAnalyzer
from collector.intelligence.compute import compute_event_ranking
from storage.repository import TraceRepository

router = APIRouter(prefix="/api", tags=["clusters"])


async def get_repository() -> TraceRepository:
    """Dependency to get a repository instance."""
    session: AsyncSession = await app_context.get_session_maker().__aenter__()
    return TraceRepository(session, tenant_id="local")


@router.get("/clusters", response_model=dict[str, Any])
async def get_cross_session_clusters(
    limit: int = Query(default=50, ge=1, le=200),
    min_count: int = Query(default=2, ge=1),
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get all cross-session failure clusters with session counts.

    Args:
        limit: Maximum number of clusters to return
        min_count: Minimum number of sessions required to form a cluster
        repo: TraceRepository instance (injected)

    Returns:
        Dictionary with clusters list and metadata
    """
    # Get all sessions with failures
    sessions = await repo.list_sessions(limit=500)

    # Compute rankings for each session
    analyzer = CrossSessionClusterAnalyzer()
    session_rankings: dict[str, dict[str, Any]] = {}

    for session in sessions:
        events = await repo.list_events(session.id, limit=1000)
        if not events:
            continue

        # Compute event rankings
        from collections import Counter

        fingerprints = [getattr(e, "fingerprint", f"{e.event_type}:{e.name}") for e in events]
        counts = Counter(fingerprints)

        rankings = []
        failure_fingerprints = []

        for event in events:
            fp = getattr(event, "fingerprint", f"{event.event_type}:{event.name}")
            ranking = compute_event_ranking(
                event,
                fp,
                counts,
                len(events),
                set(),
                lambda e: 0.8 if e.event_type.value in {"error", "refusal", "policy_violation"} else 0.5,
                all_events=events,
            )
            rankings.append(ranking)

            # Track failure fingerprints
            if ranking["severity"] > 0.7:
                failure_fingerprints.append((fp, ranking["composite"]))

        session_rankings[session.id] = {
            "failure_fingerprints": failure_fingerprints,
            "replay_value": 0.5,  # Simplified
        }

    # Analyze cross-session clusters
    clusters = analyzer.analyze(sessions, session_rankings)

    # Filter by min_count
    clusters = [c for c in clusters if c.count >= min_count][:limit]

    return {
        "clusters": [c.to_dict() for c in clusters],
        "total": len(clusters),
        "min_count": min_count,
    }


@router.get("/clusters/{fingerprint}/sessions", response_model=dict[str, Any])
async def get_cluster_sessions(
    fingerprint: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get sessions belonging to a specific failure cluster.

    Args:
        fingerprint: The failure fingerprint to query
        repo: TraceRepository instance (injected)

    Returns:
        Dictionary with sessions list and cluster metadata
    """
    # Get all sessions and find those with the matching fingerprint
    sessions = await repo.list_sessions(limit=500)

    matching_sessions = []
    for session in sessions:
        events = await repo.list_events(session.id, limit=1000)
        for event in events:
            fp = getattr(event, "fingerprint", f"{event.event_type}:{event.name}")
            if fp == fingerprint:
                matching_sessions.append(session)
                break

    if not matching_sessions:
        raise HTTPException(status_code=404, detail=f"No clusters found for fingerprint: {fingerprint}")

    # Convert to schema
    session_schemas = [
        SessionSchema(
            id=s.id,
            agent_name=s.agent_name,
            framework=s.framework,
            started_at=s.started_at,
            ended_at=s.ended_at,
            status=s.status,
            total_tokens=s.total_tokens,
            total_cost_usd=s.total_cost_usd,
            tool_calls=s.tool_calls,
            llm_calls=s.llm_calls,
            errors=s.errors,
            replay_value=s.replay_value,
            config=s.config,
            tags=s.tags,
            fix_note=s.fix_note,
            retention_tier=getattr(s, "retention_tier", None),
            failure_count=getattr(s, "failure_count", None),
            behavior_alert_count=getattr(s, "behavior_alert_count", None),
            representative_event_id=getattr(s, "representative_event_id", None),
        )
        for s in matching_sessions
    ]

    return {
        "fingerprint": fingerprint,
        "sessions": session_schemas,
        "total": len(session_schemas),
    }
