"""Cost aggregation API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_repository
from api.exceptions import NotFoundError
from storage import TraceRepository

router = APIRouter(tags=["cost"])


class CostSummaryResponse(BaseModel):
    total_cost_usd: float
    session_count: int
    avg_cost_per_session: float
    by_framework: list[dict]


class SessionCostResponse(BaseModel):
    session_id: str
    total_cost_usd: float
    total_tokens: int
    llm_calls: int
    tool_calls: int


@router.get("/api/cost/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    repo: TraceRepository = Depends(get_repository),
) -> CostSummaryResponse:
    """Get aggregate cost statistics across all sessions."""
    summary = await repo.get_cost_summary()
    return CostSummaryResponse(**summary)


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
