"""Analytics API routes for tracking user debugging efficiency metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from api.analytics_db import get_aggregates, get_daily_breakdown, record_event
from api.dependencies import get_repository

router = APIRouter(tags=["analytics"])

# Time saved per event type (in minutes)
# why_button_click: 15min manual -> 30sec = 14.5 min saved
# failure_matched: 20min manual -> 2min = 18 min saved
# replay_highlights_used: 10min manual -> 1.5min = 8.5 min saved
TIME_SAVED_MINUTES = {
    "why_button_clicks": 14.5,
    "failures_matched": 18.0,
    "replay_highlights_used": 8.5,
}


class RecordEventRequest(BaseModel):
    """Request body for recording an analytics event."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: str = Field(..., min_length=1, max_length=100, description="Type of event to record")
    session_id: str | None = Field(None, max_length=100, description="Optional session ID associated with the event")
    agent_name: str | None = Field(None, max_length=200, description="Optional agent name associated with the event")
    properties: dict[str, Any] | None = Field(None, description="Optional additional properties")


class RecordEventResponse(BaseModel):
    """Response for event recording."""

    recorded: bool = True
    event_type: str


class AdoptionRateSchema(BaseModel):
    """Adoption rates for key features."""

    why_button: float = Field(..., description="Ratio of sessions where Why button was clicked")
    failure_memory: float = Field(..., description="Ratio of sessions where failures were matched")
    replay_highlights: float = Field(..., description="Ratio of sessions where replay highlights were used")


class DerivedMetricsSchema(BaseModel):
    """Derived metrics calculated from raw totals."""

    adoption_rate: AdoptionRateSchema
    estimated_time_saved_minutes: float = Field(..., description="Estimated debugging time saved in minutes")


class DailyBreakdownItem(BaseModel):
    """Single day's metrics for sparkline visualization."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    sessions: int = Field(..., description="Number of sessions created")
    clicks: int = Field(..., description="Number of why button clicks")


class MetricsSchema(BaseModel):
    """Raw metric totals for the period."""

    sessions_created: int
    why_button_clicks: int
    failures_matched: int
    replay_highlights_used: int
    nl_queries_made: int
    searches_performed: int


class AnalyticsResponse(BaseModel):
    """Response for GET /api/analytics endpoint."""

    range: str = Field(..., description="Time range requested (e.g., '30d')")
    period_start: str = Field(..., description="Start date of period in YYYY-MM-DD format")
    period_end: str = Field(..., description="End date of period in YYYY-MM-DD format")
    metrics: MetricsSchema
    derived: DerivedMetricsSchema
    daily_breakdown: list[DailyBreakdownItem]


# Mapping from range param to days
RANGE_TO_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


def _calculate_adoption_rate(clicks: int, sessions: int) -> float:
    """Calculate adoption rate as a ratio, handling division by zero."""
    if sessions == 0:
        return 0.0
    return round(clicks / sessions, 2)


def _calculate_time_saved(aggregates: dict[str, int]) -> float:
    """Calculate total estimated time saved in minutes."""
    total = 0.0
    for metric, minutes_per_event in TIME_SAVED_MINUTES.items():
        total += aggregates.get(metric, 0) * minutes_per_event
    return round(total, 1)


@router.get("/api/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    range: Literal["7d", "30d", "90d"] = Query(default="30d", description="Time range for analytics"),
) -> AnalyticsResponse:
    """Get aggregated analytics for the specified time range.

    Returns metrics about debugging efficiency including raw counts,
    derived adoption rates, and estimated time saved.
    """
    days = RANGE_TO_DAYS[range]
    today = datetime.now(timezone.utc)
    period_end = today.strftime("%Y-%m-%d")
    period_start = (today - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get raw aggregates
    aggregates = get_aggregates(days=days)

    # Get daily breakdown for sparkline
    daily_data = get_daily_breakdown(days=days)

    # Calculate derived metrics
    sessions = aggregates.get("sessions_created", 0)

    adoption_rate = AdoptionRateSchema(
        why_button=_calculate_adoption_rate(aggregates.get("why_button_clicks", 0), sessions),
        failure_memory=_calculate_adoption_rate(aggregates.get("failures_matched", 0), sessions),
        replay_highlights=_calculate_adoption_rate(aggregates.get("replay_highlights_used", 0), sessions),
    )

    time_saved = _calculate_time_saved(aggregates)

    # Transform daily breakdown to simplified format for sparkline
    daily_breakdown = [
        DailyBreakdownItem(
            date=day["date"],
            sessions=day.get("sessions_created", 0),
            clicks=day.get("why_button_clicks", 0),
        )
        for day in daily_data
    ]

    return AnalyticsResponse(
        range=range,
        period_start=period_start,
        period_end=period_end,
        metrics=MetricsSchema(
            sessions_created=aggregates.get("sessions_created", 0),
            why_button_clicks=aggregates.get("why_button_clicks", 0),
            failures_matched=aggregates.get("failures_matched", 0),
            replay_highlights_used=aggregates.get("replay_highlights_used", 0),
            nl_queries_made=aggregates.get("nl_queries_made", 0),
            searches_performed=aggregates.get("searches_performed", 0),
        ),
        derived=DerivedMetricsSchema(
            adoption_rate=adoption_rate,
            estimated_time_saved_minutes=time_saved,
        ),
        daily_breakdown=daily_breakdown,
    )


@router.post("/api/analytics/events", response_model=RecordEventResponse)
async def record_analytics_event(request: RecordEventRequest) -> RecordEventResponse:
    """Record an analytics event.

    This is an internal endpoint for recording events from the SDK or UI.
    Events are recorded fire-and-forget style and don't block the caller.
    """
    record_event(
        event_type=request.event_type,
        session_id=request.session_id,
        agent_name=request.agent_name,
        properties=request.properties,
    )
    return RecordEventResponse(recorded=True, event_type=request.event_type)


# =============================================================================
# Pattern Detection API Routes
# =============================================================================


class PatternSchema(BaseModel):
    """Schema for detected patterns."""

    id: str = Field(..., description="Pattern ID")
    pattern_type: str = Field(..., description="Type of pattern")
    agent_name: str = Field(..., description="Agent affected by pattern")
    severity: str = Field(..., description="Severity level")
    status: str = Field(..., description="Pattern status")
    description: str = Field(..., description="Pattern description")
    affected_sessions: list[str] = Field(..., description="Affected session IDs")
    session_count: int = Field(..., description="Number of affected sessions")
    detected_at: str = Field(..., description="When pattern was detected")
    baseline_value: float | None = Field(None, description="Baseline metric value")
    current_value: float | None = Field(None, description="Current metric value")
    threshold: float | None = Field(None, description="Threshold exceeded")
    change_percent: float | None = Field(None, description="Percentage change")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PatternsListResponse(BaseModel):
    """Response schema for listing patterns."""

    patterns: list[PatternSchema]
    total: int
    filters_applied: dict[str, Any] = Field(default_factory=dict)


class PatternDetailResponse(BaseModel):
    """Response schema for pattern details."""

    pattern: PatternSchema


class HealthReportSchema(BaseModel):
    """Schema for agent health report."""

    generated_at: str
    overall_health_score: float
    agent_summary: str
    total_patterns: int
    patterns_by_severity: dict[str, int]
    patterns_by_type: dict[str, int]
    critical_patterns: list[dict[str, Any]]
    top_issues: list[dict[str, Any]]
    recommendations: list[str]
    affected_agents: list[str]
    trend_metrics: dict[str, Any]


@router.get("/api/analytics/patterns", response_model=PatternsListResponse)
async def get_patterns(
    agent_name: str | None = Query(default=None, description="Filter by agent name"),
    pattern_type: str | None = Query(default=None, description="Filter by pattern type"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    status: str | None = Query(default="active", description="Filter by status"),
    hours: int | None = Query(default=None, description="Only return patterns from last N hours"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results to return"),
    repo=Depends(get_repository),
) -> PatternsListResponse:
    """Get detected patterns across sessions.

    Returns patterns matching the specified filters, ordered by detection time.
    Supports filtering by agent, pattern type, severity, status, and time range.
    """
    # Use the pattern repository through the session
    from storage.repositories.pattern_repo import PatternRepository

    pattern_repo = PatternRepository(repo.session, repo.tenant_id)

    patterns = await pattern_repo.get_recent_patterns(
        pattern_type=pattern_type,
        severity=severity,
        status=status,
        hours=hours,
        limit=limit,
    )

    # Convert to schema
    pattern_schemas = [
        PatternSchema(
            id=p.id,
            pattern_type=p.pattern_type,
            agent_name=p.agent_name,
            severity=p.severity,
            status=p.status,
            description=p.description,
            affected_sessions=p.affected_sessions,
            session_count=p.session_count,
            detected_at=p.detected_at.isoformat(),
            baseline_value=p.baseline_value,
            current_value=p.current_value,
            threshold=p.threshold,
            change_percent=p.change_percent,
            metadata=p.pattern_data,
        )
        for p in patterns
    ]

    # Build filters applied dict
    filters_applied = {}
    if agent_name:
        # Filter in-memory (or we could add agent filter to get_recent_patterns)
        pattern_schemas = [p for p in pattern_schemas if p.agent_name == agent_name]
        filters_applied["agent_name"] = agent_name

    return PatternsListResponse(
        patterns=pattern_schemas,
        total=len(pattern_schemas),
        filters_applied=filters_applied,
    )


@router.get("/api/analytics/patterns/{pattern_id}", response_model=PatternDetailResponse)
async def get_pattern_detail(
    pattern_id: str,
    repo=Depends(get_repository),
) -> PatternDetailResponse:
    """Get detailed information about a specific pattern.

    Returns full pattern details including affected sessions list.
    """
    from storage.repositories.pattern_repo import PatternRepository

    pattern_repo = PatternRepository(repo.session, repo.tenant_id)

    pattern = await pattern_repo.get_pattern(pattern_id)
    if pattern is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")

    pattern_schema = PatternSchema(
        id=pattern.id,
        pattern_type=pattern.pattern_type,
        agent_name=pattern.agent_name,
        severity=pattern.severity,
        status=pattern.status,
        description=pattern.description,
        affected_sessions=pattern.affected_sessions,
        session_count=pattern.session_count,
        detected_at=pattern.detected_at.isoformat(),
        baseline_value=pattern.baseline_value,
        current_value=pattern.current_value,
        threshold=pattern.threshold,
        change_percent=pattern.change_percent,
        metadata=pattern.pattern_data,
    )

    return PatternDetailResponse(pattern=pattern_schema)


@router.get("/api/analytics/health-report", response_model=HealthReportSchema)
async def get_health_report(
    agent_name: str | None = Query(default=None, description="Filter by agent name"),
    hours: int | None = Query(default=24, ge=1, le=168, description="Look at patterns from last N hours"),
    repo=Depends(get_repository),
) -> HealthReportSchema:
    """Generate agent health report from detected patterns.

    Analyzes patterns from the specified time window and generates
    a comprehensive health report with:
    - Overall health score (0-100)
    - Pattern summary by type and severity
    - Critical patterns requiring attention
    - Top issues with recommendations
    - Actionable next steps
    """
    from collector.patterns import generate_health_report
    from storage.repositories.pattern_repo import PatternRepository

    pattern_repo = PatternRepository(repo.session, repo.tenant_id)

    # Get recent patterns
    patterns = await pattern_repo.get_recent_patterns(hours=hours, status="active")

    # Filter by agent if specified
    if agent_name:
        patterns = [p for p in patterns if p.agent_name == agent_name]

    # Convert PatternModel to Pattern objects
    from collector.patterns.pattern_detector import Pattern as DetectorPattern

    detector_patterns = [
        DetectorPattern(
            pattern_type=p.pattern_type,
            agent_name=p.agent_name,
            severity=p.severity,
            description=p.description,
            affected_sessions=p.affected_sessions,
            detected_at=p.detected_at,
            baseline_value=p.baseline_value,
            current_value=p.current_value,
            threshold=p.threshold,
            change_percent=p.change_percent,
            metadata=p.pattern_data,
        )
        for p in patterns
    ]

    # Generate health report
    report = generate_health_report(detector_patterns)

    return HealthReportSchema(
        generated_at=report.generated_at.isoformat(),
        overall_health_score=report.overall_health_score,
        agent_summary=report.agent_summary,
        total_patterns=report.total_patterns,
        patterns_by_severity=report.patterns_by_severity,
        patterns_by_type=report.patterns_by_type,
        critical_patterns=report.critical_patterns,
        top_issues=report.top_issues,
        recommendations=report.recommendations,
        affected_agents=report.affected_agents,
        trend_metrics=report.trend_metrics,
    )
