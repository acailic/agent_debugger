"""Trace, analysis, and search API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.analytics_db import record_event
from api.config import (
    MAX_ALERTS_PER_REQUEST,
    MAX_EVENTS_FOR_ANALYSIS,
    MAX_QUERY_LENGTH,
    MAX_SEARCH_RESULTS,
)
from api.dependencies import get_repository
from api.schemas import (
    AgentBaselineSchema,
    AnalysisResponse,
    AnomalyAlertListResponse,
    AnomalyAlertSchema,
    DriftAlertSchema,
    DriftResponseSchema,
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
    sessions = await repo.list_sessions(limit=MAX_EVENTS_FOR_ANALYSIS)
    agent_sessions = [s for s in sessions if s.agent_name == agent_name]

    # Parallelize event loading with asyncio.gather
    events_results = await asyncio.gather(*[repo.get_events(s.id) for s in agent_sessions])
    events_by_session = {s.id: events for s, (events, _) in zip(agent_sessions, events_results)}

    return agent_sessions, events_by_session


@router.get("/api/sessions/{session_id}/trace", response_model=TraceBundleResponse)
async def get_trace_bundle(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> TraceBundleResponse:
    session = await require_session(repo, session_id)
    try:
        events, checkpoints, analysis, replay_value = await analyze_session(
            repo,
            session_id,
            persist_replay_value=True,
        )
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
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
    try:
        _, _, analysis, _ = await analyze_session(repo, session_id, persist_replay_value=True)
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    # Record analytics event (fire-and-forget)
    record_event("why_button_clicked", session_id=session_id)
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
    query: str = Query(min_length=1, max_length=MAX_QUERY_LENGTH),
    session_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_SEARCH_RESULTS),
    repo: TraceRepository = Depends(get_repository),
) -> TraceSearchResponse:
    results = await repo.search_events(
        query,
        session_id=session_id,
        event_type=event_type,
        limit=limit,
    )
    # Record analytics event (fire-and-forget)
    record_event(
        "search_performed",
        properties={
            "query_type": "event_type" if event_type else "text",
            "has_results": len(results) > 0,
        },
    )
    return TraceSearchResponse(
        query=query,
        session_id=session_id,
        event_type=event_type,
        total=len(results),
        results=[normalize_event(event) for event in results],
    )


@router.get("/api/agents/{agent_name}/baseline", response_model=AgentBaselineSchema)
async def get_agent_baseline(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> AgentBaselineSchema:
    """Get baseline metrics for an agent (last 7 days)."""
    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    if not agent_sessions:
        return AgentBaselineSchema(
            agent_name=agent_name,
            session_count=0,
            total_llm_calls=0,
            total_tool_calls=0,
            total_tokens=0,
            total_cost_usd=0.0,
            avg_llm_calls_per_session=0.0,
            avg_tool_calls_per_session=0.0,
            avg_tokens_per_session=0.0,
            avg_cost_per_session=0.0,
            error_rate=0.0,
            avg_duration_seconds=0.0,
        )

    baseline = compute_baseline_from_sessions(agent_name, agent_sessions, events_by_session)
    baseline_dict = baseline.to_dict()
    return AgentBaselineSchema(
        agent_name=baseline_dict["agent_name"],
        session_count=baseline_dict["session_count"],
        total_llm_calls=baseline_dict.get("total_llm_calls", 0),
        total_tool_calls=baseline_dict.get("total_tool_calls", 0),
        total_tokens=baseline_dict.get("total_tokens", 0),
        total_cost_usd=baseline_dict.get("total_cost_usd", 0.0),
        avg_llm_calls_per_session=baseline_dict.get("avg_llm_calls_per_session", 0.0),
        avg_tool_calls_per_session=baseline_dict.get("avg_tool_calls_per_session", 0.0),
        avg_tokens_per_session=baseline_dict.get("avg_tokens_per_session", 0.0),
        avg_cost_per_session=baseline_dict.get("avg_cost_per_session", 0.0),
        error_rate=baseline_dict.get("error_rate", 0.0),
        avg_duration_seconds=baseline_dict.get("avg_duration_seconds", 0.0),
    )


@router.get("/api/agents/{agent_name}/drift", response_model=DriftResponseSchema)
async def get_agent_drift(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> DriftResponseSchema:
    """Detect drift between baseline (7 days) and recent (24h) behavior."""
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)

    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    def _make_empty_baseline() -> AgentBaselineSchema:
        return AgentBaselineSchema(
            agent_name=agent_name,
            session_count=0,
            total_llm_calls=0,
            total_tool_calls=0,
            total_tokens=0,
            total_cost_usd=0.0,
            avg_llm_calls_per_session=0.0,
            avg_tool_calls_per_session=0.0,
            avg_tokens_per_session=0.0,
            avg_cost_per_session=0.0,
            error_rate=0.0,
            avg_duration_seconds=0.0,
        )

    if not agent_sessions:
        return DriftResponseSchema(
            agent_name=agent_name,
            baseline_session_count=0,
            recent_session_count=0,
            baseline=_make_empty_baseline(),
            current=_make_empty_baseline(),
            alerts=[],
            message="No sessions found",
        )

    # Handle both naive and aware datetimes (SQLite may strip timezone info)
    def _is_baseline(session_started_at: datetime) -> bool:
        """Check if session is in baseline window (older than 24h)."""
        dt = session_started_at
        # If naive, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < recent_cutoff

    baseline_sessions = [s for s in agent_sessions if _is_baseline(s.started_at)]
    recent_sessions = [s for s in agent_sessions if not _is_baseline(s.started_at)]

    if len(baseline_sessions) < 1:
        return DriftResponseSchema(
            agent_name=agent_name,
            baseline_session_count=len(baseline_sessions),
            recent_session_count=len(recent_sessions),
            baseline=_make_empty_baseline(),
            current=_make_empty_baseline(),
            alerts=[],
            message="Need at least 1 baseline session for drift detection",
        )

    baseline = compute_baseline_from_sessions(agent_name, baseline_sessions, events_by_session)
    current = compute_baseline_from_sessions(agent_name, recent_sessions, events_by_session)
    alerts = detect_drift(baseline, current)

    def _dict_to_baseline(b: dict[str, Any]) -> AgentBaselineSchema:
        return AgentBaselineSchema(
            agent_name=b["agent_name"],
            session_count=b["session_count"],
            total_llm_calls=b.get("total_llm_calls", 0),
            total_tool_calls=b.get("total_tool_calls", 0),
            total_tokens=b.get("total_tokens", 0),
            total_cost_usd=b.get("total_cost_usd", 0.0),
            avg_llm_calls_per_session=b.get("avg_llm_calls_per_session", 0.0),
            avg_tool_calls_per_session=b.get("avg_tool_calls_per_session", 0.0),
            avg_tokens_per_session=b.get("avg_tokens_per_session", 0.0),
            avg_cost_per_session=b.get("avg_cost_per_session", 0.0),
            error_rate=b.get("error_rate", 0.0),
            avg_duration_seconds=b.get("avg_duration_seconds", 0.0),
        )

    alert_schemas = [
        DriftAlertSchema(
            metric=alert.metric,
            metric_label=alert.metric_label,
            baseline_value=alert.baseline_value,
            current_value=alert.current_value,
            change_percent=alert.change_percent,
            severity=alert.severity,
            description=alert.description,
        )
        for alert in alerts
    ]

    return DriftResponseSchema(
        agent_name=agent_name,
        baseline_session_count=len(baseline_sessions),
        recent_session_count=len(recent_sessions),
        baseline=_dict_to_baseline(baseline.to_dict()),
        current=_dict_to_baseline(current.to_dict()),
        alerts=alert_schemas,
    )


# ------------------------------------------------------------------
# Anomaly Alert Endpoints
# ------------------------------------------------------------------


@router.get("/api/sessions/{session_id}/alerts", response_model=AnomalyAlertListResponse)
async def get_session_alerts(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=MAX_ALERTS_PER_REQUEST),
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
