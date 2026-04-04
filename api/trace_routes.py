"""Trace, analysis, and search API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.analytics_db import record_event
from api.config import (
    MAX_ALERTS_PER_REQUEST,
    MAX_EVENTS_FOR_ANALYSIS,
    MAX_QUERY_LENGTH,
    MAX_SEARCH_RESULTS,
)
from api.dependencies import get_repository
from api.exceptions import NotFoundError
from api.schemas import (
    AgentBaselineSchema,
    AlertBulkUpdate,
    AlertFilters,
    AlertListFilteredResponse,
    AlertSeverityCount,
    AlertStatusUpdate,
    AlertSummarySchema,
    AlertTrendingPointSchema,
    AlertTrendingSchema,
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
    agent_sessions = await repo.list_sessions(limit=MAX_EVENTS_FOR_ANALYSIS, agent_name=agent_name)

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


def _empty_baseline(agent_name: str) -> AgentBaselineSchema:
    """Create a baseline schema with zeroed metrics."""
    now = datetime.now(timezone.utc)
    return AgentBaselineSchema(
        agent_name=agent_name,
        session_count=0,
        computed_at=now,
        time_window_days=7,
        avg_decision_confidence=0.0,
        low_confidence_rate=0.0,
        avg_tool_duration_ms=0.0,
        error_rate=0.0,
        avg_tokens_per_session=0.0,
        avg_cost_per_session=0.0,
        tool_loop_rate=0.0,
        refusal_rate=0.0,
        avg_session_replay_value=0.0,
        avg_duration_seconds=0.0,
    )


def _baseline_from_dict(d: dict[str, Any]) -> AgentBaselineSchema:
    """Convert an AgentBaseline.to_dict() payload to the public API schema."""
    return AgentBaselineSchema(
        agent_name=d["agent_name"],
        session_count=d["session_count"],
        computed_at=datetime.fromisoformat(d["computed_at"]),
        time_window_days=d.get("time_window_days", 7),
        avg_decision_confidence=d.get("avg_decision_confidence", 0.0),
        low_confidence_rate=d.get("low_confidence_rate", 0.0),
        avg_tool_duration_ms=d.get("avg_tool_duration_ms", 0.0),
        error_rate=d.get("error_rate", 0.0),
        avg_tokens_per_session=d.get("avg_tokens_per_session", 0.0),
        avg_cost_per_session=d.get("avg_cost_per_session", 0.0),
        tool_loop_rate=d.get("tool_loop_rate", 0.0),
        refusal_rate=d.get("refusal_rate", 0.0),
        avg_session_replay_value=d.get("avg_session_replay_value", 0.0),
        multi_agent_metrics=d.get("multi_agent_metrics"),
        total_llm_calls=d.get("total_llm_calls", 0),
        total_tool_calls=d.get("total_tool_calls", 0),
        total_tokens=d.get("total_tokens", 0),
        total_cost_usd=d.get("total_cost_usd", 0.0),
        avg_llm_calls_per_session=d.get("avg_llm_calls_per_session", 0.0),
        avg_tool_calls_per_session=d.get("avg_tool_calls_per_session", 0.0),
        avg_duration_seconds=d.get("avg_duration_seconds", 0.0),
    )


@router.get("/api/agents/{agent_name}/baseline", response_model=AgentBaselineSchema)
async def get_agent_baseline(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> AgentBaselineSchema:
    """Get baseline metrics for an agent (last 7 days)."""
    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    if not agent_sessions:
        return _empty_baseline(agent_name)

    baseline = compute_baseline_from_sessions(agent_name, agent_sessions, events_by_session)
    return _baseline_from_dict(baseline.to_dict())


@router.get("/api/agents/{agent_name}/drift", response_model=DriftResponseSchema)
async def get_agent_drift(
    agent_name: str,
    repo: TraceRepository = Depends(get_repository),
) -> DriftResponseSchema:
    """Detect drift between baseline (7 days) and recent (24h) behavior."""
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)

    agent_sessions, events_by_session = await _load_agent_sessions_with_events(repo, agent_name)

    if not agent_sessions:
        return DriftResponseSchema(
            agent_name=agent_name,
            baseline_session_count=0,
            recent_session_count=0,
            baseline=_empty_baseline(agent_name),
            current=_empty_baseline(agent_name),
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
            baseline=_empty_baseline(agent_name),
            current=_empty_baseline(agent_name),
            alerts=[],
            message="Need at least 1 baseline session for drift detection",
        )

    baseline = compute_baseline_from_sessions(agent_name, baseline_sessions, events_by_session)
    current = compute_baseline_from_sessions(agent_name, recent_sessions, events_by_session)
    alerts = detect_drift(baseline, current)

    return DriftResponseSchema(
        agent_name=agent_name,
        baseline_session_count=len(baseline_sessions),
        recent_session_count=len(recent_sessions),
        baseline=_baseline_from_dict(baseline.to_dict()),
        current=_baseline_from_dict(current.to_dict()),
        alerts=[
            DriftAlertSchema(
                metric=a.metric,
                metric_label=a.metric_label,
                baseline_value=a.baseline_value,
                current_value=a.current_value,
                change_percent=a.change_percent,
                severity=a.severity,
                description=a.description,
                likely_cause=a.likely_cause,
            )
            for a in alerts
        ],
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
                status=alert.status,
                acknowledged_at=alert.acknowledged_at,
                resolved_at=alert.resolved_at,
                dismissed_at=alert.dismissed_at,
                resolution_note=alert.resolution_note,
            )
            for alert in alerts
        ],
        total=len(alerts),
    )


# ------------------------------------------------------------------
# Alert Lifecycle Management Endpoints (must come before /api/alerts/{alert_id})
# ------------------------------------------------------------------


@router.get("/api/alerts/summary", response_model=AlertSummarySchema)
async def get_alert_summary(
    repo: TraceRepository = Depends(get_repository),
) -> AlertSummarySchema:
    """Get alert summary statistics grouped by severity, type, and status.

    Args:
        repo: TraceRepository instance

    Returns:
        AlertSummarySchema with counts by severity, type, and status
    """
    summary = await repo._alert_repo.get_alert_lifecycle_summary()

    return AlertSummarySchema(
        by_status=summary["by_status"],
        by_type=summary["by_type"],
        by_severity=AlertSeverityCount(**summary["by_severity"]),
        total=summary["total"],
    )


@router.get("/api/alerts/trending", response_model=AlertTrendingSchema)
async def get_alert_trending(
    days: int = Query(default=7, ge=1, le=90),
    repo: TraceRepository = Depends(get_repository),
) -> AlertTrendingSchema:
    """Get alert volume trend grouped by day.

    Args:
        days: Number of days to look back (default 7, max 90)
        repo: TraceRepository instance

    Returns:
        AlertTrendingSchema with list of daily counts
    """
    trending = await repo._alert_repo.get_alert_trending(days=days)

    return AlertTrendingSchema(
        trending=[AlertTrendingPointSchema(**point) for point in trending],
        days=days,
    )


@router.post("/api/alerts/bulk-status")
async def bulk_update_alert_status(
    update: AlertBulkUpdate,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Bulk update status for multiple alerts.

    Args:
        update: Bulk update request with alert_ids and status
        repo: TraceRepository instance

    Returns:
        Dictionary with updated count

    Raises:
        ValueError: if status is invalid
    """
    updated_count = await repo._alert_repo.bulk_update_status(update.alert_ids, update.status)

    try:
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise

    return {
        "updated": updated_count,
        "status": update.status,
    }


@router.get("/api/alerts", response_model=AlertListFilteredResponse)
async def list_alerts_filtered(
    agent_name: str | None = Query(default=None),
    severity: float | None = Query(default=None, ge=0.0, le=1.0),
    alert_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    repo: TraceRepository = Depends(get_repository),
) -> AlertListFilteredResponse:
    """List alerts with rich filtering options.

    Args:
        agent_name: Optional agent name to filter by
        severity: Optional minimum severity to filter by
        alert_type: Optional alert type to filter by
        status: Optional status to filter by
        from_date: Optional start date for created_at filter
        to_date: Optional end date for created_at filter
        limit: Maximum number of alerts to return
        repo: TraceRepository instance

    Returns:
        AlertListFilteredResponse with filtered alerts
    """
    alerts = await repo._alert_repo.list_alerts_filtered(
        agent_name=agent_name,
        severity=severity,
        alert_type=alert_type,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )

    filters = AlertFilters(
        agent_name=agent_name,
        severity=severity,
        alert_type=alert_type,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )

    return AlertListFilteredResponse(
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
                status=alert.status,
                acknowledged_at=alert.acknowledged_at,
                resolved_at=alert.resolved_at,
                dismissed_at=alert.dismissed_at,
                resolution_note=alert.resolution_note,
            )
            for alert in alerts
        ],
        total=len(alerts),
        filters=filters,
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
        NotFoundError: if alert not found
    """
    alert = await repo.get_anomaly_alert(alert_id)
    if not alert:
        raise NotFoundError(f"Alert {alert_id} not found")

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
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        dismissed_at=alert.dismissed_at,
        resolution_note=alert.resolution_note,
    )


@router.put("/api/alerts/{alert_id}/status", response_model=AnomalyAlertSchema)
async def update_alert_status(
    alert_id: str,
    update: AlertStatusUpdate,
    repo: TraceRepository = Depends(get_repository),
) -> AnomalyAlertSchema:
    """Update the status of a single alert.

    Args:
        alert_id: Unique identifier of the alert
        update: Status update request with status and optional note
        repo: TraceRepository instance

    Returns:
        Updated AnomalyAlertSchema

    Raises:
        NotFoundError: if alert not found
        ValueError: if status is invalid
    """
    alert = await repo._alert_repo.update_alert_status(alert_id, update.status, update.note)
    if not alert:
        raise NotFoundError(f"Alert {alert_id} not found")

    try:
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise

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
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        dismissed_at=alert.dismissed_at,
        resolution_note=alert.resolution_note,
    )
