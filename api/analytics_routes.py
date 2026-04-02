"""Analytics API routes for tracking user debugging efficiency metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from api.analytics_db import get_aggregates, get_daily_breakdown, record_event

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
