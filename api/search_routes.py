"""Failure memory search API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.app_context import require_session_maker
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


class FixNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class FixNoteResponse(BaseModel):
    session_id: str
    fix_note: str


@router.get("/api/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=2),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    """Search sessions by semantic similarity to a text query."""
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
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


@router.post("/api/sessions/{session_id}/fix-note", response_model=FixNoteResponse)
async def add_fix_note(session_id: str, body: FixNoteRequest) -> FixNoteResponse:
    """Add or update a fix note for a session."""
    async with require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        session = await repo.add_fix_note(session_id, body.note)
        await db_session.commit()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return FixNoteResponse(session_id=session_id, fix_note=body.note)
