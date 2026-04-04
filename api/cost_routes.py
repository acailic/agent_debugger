"""Cost aggregation API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.dependencies import get_repository
from api.exceptions import NotFoundError
from storage import TraceRepository

router = APIRouter(tags=["cost"])

# Mapping from range param to days (same pattern as analytics_routes.py)
RANGE_TO_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


class FrameworkCostItem(BaseModel):
    framework: str
    session_count: int
    total_cost_usd: float
    avg_cost_per_session: float
    total_tokens: int


class CostSummaryResponse(BaseModel):
    total_cost_usd: float
    session_count: int
    avg_cost_per_session: float
    by_framework: list[FrameworkCostItem]
    daily_cost: list[dict] = Field(default_factory=list, description="Daily cost breakdown for sparkline")
    period_start: str | None = Field(default=None, description="Start date of period in ISO format")
    period_end: str | None = Field(default=None, description="End date of period in ISO format")


class DailyCostItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    session_count: int
    total_cost_usd: float
    total_tokens: int
    avg_cost_usd: float


class SessionCostResponse(BaseModel):
    session_id: str
    total_cost_usd: float
    total_tokens: int
    llm_calls: int
    tool_calls: int


class TopSessionItem(BaseModel):
    session_id: str
    agent_name: str
    framework: str
    total_cost_usd: float
    total_tokens: int
    llm_calls: int
    tool_calls: int
    started_at: str | None
    status: str


class TopSessionsResponse(BaseModel):
    sessions: list[TopSessionItem]
    total: int


@router.get("/api/cost/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    range: Literal["7d", "30d", "90d"] | None = Query(default=None, description="Time range for cost summary"),
    repo: TraceRepository = Depends(get_repository),
) -> CostSummaryResponse:
    """Get aggregate cost statistics across all sessions.

    Supports optional time-range filtering (7d, 30d, 90d) for focused analysis.
    Returns daily breakdown for sparkline visualization and period boundaries.
    """
    days = RANGE_TO_DAYS.get(range) if range else None

    # Get summary
    summary = await repo.get_cost_summary(days=days)

    # Get daily breakdown if range is specified
    daily_cost = []
    if days is not None:
        daily_cost = await repo.get_daily_cost_breakdown(days=days)

    return CostSummaryResponse(
        total_cost_usd=summary["total_cost_usd"],
        session_count=summary["session_count"],
        avg_cost_per_session=summary["avg_cost_per_session"],
        by_framework=summary["by_framework"],
        daily_cost=daily_cost,
        period_start=summary.get("period_start"),
        period_end=summary.get("period_end"),
    )


@router.get("/api/cost/top-sessions", response_model=TopSessionsResponse)
async def get_top_sessions(
    range: Literal["7d", "30d", "90d"] | None = Query(default=None, description="Time range for top sessions"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of sessions to return"),
    repo: TraceRepository = Depends(get_repository),
) -> TopSessionsResponse:
    """Get top sessions by cost, optionally filtered by time range.

    Returns sessions ordered by total_cost_usd descending, useful for
    identifying expensive sessions that may need optimization attention.
    """
    days = RANGE_TO_DAYS.get(range) if range else None
    sessions = await repo.get_top_sessions_by_cost(days=days, limit=limit)

    return TopSessionsResponse(
        sessions=[TopSessionItem(**s) for s in sessions],
        total=len(sessions),
    )


@router.get("/api/cost/sessions/{session_id}", response_model=SessionCostResponse)
async def get_session_cost(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> SessionCostResponse:
    """Get cost breakdown for a specific session."""
    session = await repo.get_session(session_id)
    if session is None:
        raise NotFoundError(f"Session {session_id} not found")
    return SessionCostResponse(
        session_id=session.id,
        total_cost_usd=session.total_cost_usd,
        total_tokens=session.total_tokens,
        llm_calls=session.llm_calls,
        tool_calls=session.tool_calls,
    )
