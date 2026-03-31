"""Failure memory search API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.config import MAX_SESSION_SEARCH_RESULTS
from api.dependencies import get_repository
from storage import TraceRepository

router = APIRouter(tags=["search"])


class SearchResult(BaseModel):
    session_id: str
    agent_name: str
    framework: str
    status: str
    total_cost_usd: float
    started_at: str
    ended_at: str | None
    errors: int
    fix_note: str | None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


@router.get("/api/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=2),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=MAX_SESSION_SEARCH_RESULTS),
    repo: TraceRepository = Depends(get_repository),
) -> SearchResponse:
    """Search sessions by semantic similarity to a text query."""
    sessions = await repo.search_sessions(q, status=status, limit=limit)
    results = [
        SearchResult(
            session_id=s.id,
            agent_name=s.agent_name or "",
            framework=s.framework or "",
            status=str(s.status),
            total_cost_usd=s.total_cost_usd,
            started_at=s.started_at.isoformat() if s.started_at else "",
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            errors=s.errors,
            fix_note=s.fix_note,
            similarity=getattr(s, "search_similarity", 0.0),
        )
        for s in sessions
    ]
    return SearchResponse(query=q, total=len(results), results=results)
