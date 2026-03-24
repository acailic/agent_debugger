"""Trace, analysis, and search API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_repository
from api.schemas import (
    AnalysisResponse,
    AnomalyAlertListResponse,
    AnomalyAlertSchema,
    LiveSummaryResponse,
    TraceBundleResponse,
    TraceSearchResponse,
)
from api.services import (
    analyze_session,
    build_live_summary,
    normalize_checkpoint,
    normalize_event,
    normalize_session,
    require_session,
)
from collector.baseline import compute_baseline_from_sessions, detect_drift
from collector.replay import build_tree
from storage import TraceRepository

router = APIRouter(tags=["traces"])


async def _load_agent_sessions_with_events(
    repo: TraceRepository,
    agent_name: str,
) -> tuple[list[Any], dict[str, list[Any]]]:
    """Load sessions and their events for a specific agent."""
    sessions = await repo.list_sessions(limit=1000)
    agent_sessions = [s for s in sessions if s.agent_name == agent_name]
    events_by_session = {}
    for session in agent_sessions:
        events, _ = await repo.get_events(session.id)
        events_by_session[session.id] = events
    return agent_sessions, events_by_session


@router.get("/api/sessions/{session_id}/trace", response_model=TraceBundleResponse)
async def get_trace_bundle(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> TraceBundleResponse:
    session = await require_session(repo, session_id)
    events, checkpoints, analysis, replay_value = await analyze_session(
        repo,
        session_id,
        persist_replay_value=True,
    )
    await repo.commit()
    # Update session with computed replay_value without re-fetching
    session.replay_value = replay_value
    return TraceBundleResponse(
        session=normalize_session(session),
        events=[normalize_event(event) for event in events],
        checkpoints=[normalize_checkpoint(checkpoint) for checkpoint in checkpoints],
        tree=build_tree(events),
        analysis=analysis,
    )


@router.get("/api/sessions/{session_id}/analysis", response_model=AnalysisResponse)
async def get_session_analysis(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> AnalysisResponse:
    await require_session(repo, session_id)
    _, _, analysis, _ = await analyze_session(repo, session_id, persist_replay_value=True)
    await repo.commit()
    return AnalysisResponse(session_id=session_id, analysis=analysis)


@router.get("/api/sessions/{session_id}/live", response_model=LiveSummaryResponse)
async def get_session_live_summary(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> LiveSummaryResponse:
    await require_session(repo, session_id)
    return LiveSummaryResponse(
        session_id=session_id,
        live_summary=await build_live_summary(repo, session_id),
    )


@router.get("/api/traces/search", response_model=TraceSearchResponse)
async def search_traces(
    query: str = Query(min_length=1),
    session_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    repo: TraceRepository = Depends(get_repository),
) -> TraceSearchResponse:
    results = await repo.search_events(
        query,
        session_id=session_id,
        event_type=event_type,
        limit=limit,
    )
    return TraceSearchResponse(
        query=query,
        session_id=session_id,
        event_type=event_type,
        total=len(results),
        results=[normalize_event(event) for event in results],
    )


@router.get("/api/agents/{agent_name}/baseline")
async def get_agent_baseline(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Get baseline metrics for an agent (last 7 days)."""
    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    if not agent_sessions:
        return {"agent_name": agent_name, "session_count": 0, "error": "No sessions found"}

    baseline = compute_baseline_from_sessions(agent_name, agent_sessions, events_by_session)
    return baseline.to_dict()


@router.get("/api/agents/{agent_name}/drift")
async def get_agent_drift(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Detect drift between baseline (7 days) and recent (24h) behavior."""
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)

    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    if not agent_sessions:
        return {"agent_name": agent_name, "alerts": [], "error": "No sessions found"}

    baseline_sessions = [s for s in agent_sessions if s.started_at < recent_cutoff]
    recent_sessions = [s for s in agent_sessions if s.started_at >= recent_cutoff]

    if len(baseline_sessions) < 3:
        return {
            "agent_name": agent_name,
            "alerts": [],
            "baseline_session_count": len(baseline_sessions),
            "recent_session_count": len(recent_sessions),
            "message": "Need at least 3 baseline sessions for drift detection",
        }

    baseline = compute_baseline_from_sessions(agent_name, baseline_sessions, events_by_session)
    current = compute_baseline_from_sessions(agent_name, recent_sessions, events_by_session)
    alerts = detect_drift(baseline, current)

    return {
        "agent_name": agent_name,
        "baseline": baseline.to_dict(),
        "current": current.to_dict(),
        "alerts": [a.to_dict() for a in alerts],
    }


# ------------------------------------------------------------------
# Anomaly Alert Endpoints
# ------------------------------------------------------------------


@router.get("/api/sessions/{session_id}/alerts", response_model=AnomalyAlertListResponse)
async def get_session_alerts(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    repo: TraceRepository = Depends(get_repository),
) -> AnomalyAlertListResponse:
    """Get all anomaly alerts for a session.

    Args:
        session_id: Session ID to get alerts for
        limit: Maximum number of alerts to return
        repo: TraceRepository instance

    Returns:
        List of anomaly alerts for the session
    """
    await require_session(repo, session_id)
    alerts = await repo.list_anomaly_alerts(session_id, limit=limit)

    return AnomalyAlertListResponse(
        session_id=session_id,
        alerts=[
            AnomalyAlertSchema(
                id=alert.id,
                session_id=alert.session_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                signal=alert.signal,
                event_ids=alert.event_ids or [],
                detection_source=alert.detection_source,
                detection_config=alert.detection_config or {},
                created_at=alert.created_at,
            )
            for alert in alerts
        ],
        total=len(alerts),
    )


@router.get("/api/alerts/{alert_id}", response_model=AnomalyAlertSchema)
async def get_alert(
    alert_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> AnomalyAlertSchema:
    """Get a single anomaly alert by ID.

    Args:
        alert_id: Unique identifier of the alert
        repo: TraceRepository instance

    Returns:
        AnomalyAlertSchema if found

    Raises:
        HTTPException: 404 if alert not found
    """
    alert = await repo.get_anomaly_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return AnomalyAlertSchema(
        id=alert.id,
        session_id=alert.session_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        signal=alert.signal,
        event_ids=alert.event_ids or [],
        detection_source=alert.detection_source,
        detection_config=alert.detection_config or {},
        created_at=alert.created_at,
    )
