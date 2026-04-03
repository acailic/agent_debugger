"""Failure memory search API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.config import MAX_SESSION_SEARCH_RESULTS
from api.dependencies import get_repository
from storage import TraceRepository

router = APIRouter(tags=["search"])


class SearchHighlight(BaseModel):
    """Represents a highlighted match in search results."""

    event_id: str
    event_type: str
    field_name: str
    matched_text: str
    relevance: float


class SearchResult(BaseModel):
    id: str
    session_id: str
    agent_name: str
    framework: str
    status: str
    total_cost_usd: float
    started_at: str
    ended_at: str | None
    errors: int
    tags: list[str] = Field(default_factory=list)
    fix_note: str | None
    similarity: float
    highlights: list[SearchHighlight] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]
    filters_applied: dict[str, Any] = Field(default_factory=dict)


class NaturalLanguageSearchRequest(BaseModel):
    """Request model for natural language search with filters."""

    query: str = Field(..., min_length=2, max_length=500, description="Natural language search query")
    status: str | None = Field(None, description="Filter by session status")
    event_type: str | None = Field(None, description="Filter by event type present in session")
    agent_name: str | None = Field(None, description="Filter by agent name")
    tags: list[str] | None = Field(None, description="Filter by tags (sessions must have at least one)")
    started_after: str | None = Field(None, description="ISO datetime filter - sessions started after")
    started_before: str | None = Field(None, description="ISO datetime filter - sessions started before")
    min_errors: int | None = Field(None, ge=0, description="Minimum error count")
    limit: int = Field(default=20, ge=1, le=MAX_SESSION_SEARCH_RESULTS, description="Maximum results")
    interpret_nl: bool = Field(
        default=True,
        description="Whether to interpret natural language patterns in the query",
    )


class NaturalLanguageSearchResponse(BaseModel):
    """Response model for natural language search."""

    query: str
    interpreted_query: str
    total: int
    results: list[SearchResult]
    filters_applied: dict[str, Any]


@router.get("/api/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=2),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=MAX_SESSION_SEARCH_RESULTS),
    repo: TraceRepository = Depends(get_repository),
) -> SearchResponse:
    """Search sessions by semantic similarity to a text query.

    Legacy endpoint for simple text search. Use POST /api/search for advanced filtering.
    """
    sessions = await repo.search_sessions(q, status=status, limit=limit)
    results = [
        SearchResult(
            id=s.id,
            session_id=s.id,
            agent_name=s.agent_name or "",
            framework=s.framework or "",
            status=str(s.status),
            total_cost_usd=s.total_cost_usd,
            started_at=s.started_at.isoformat() if s.started_at else "",
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            errors=s.errors,
            tags=s.tags or [],
            fix_note=s.fix_note,
            similarity=getattr(s, "search_similarity", 0.0),
            highlights=[
                SearchHighlight(**h) for h in getattr(s, "search_highlights", [])
            ],
        )
        for s in sessions
    ]
    return SearchResponse(
        query=q,
        total=len(results),
        results=results,
        filters_applied={"status": status} if status else {},
    )


@router.post("/api/search", response_model=NaturalLanguageSearchResponse)
async def search_sessions_nl(
    request: NaturalLanguageSearchRequest,
    repo: TraceRepository = Depends(get_repository),
) -> NaturalLanguageSearchResponse:
    """Search sessions using natural language queries with advanced filters.

    Supports natural language queries like:
    - "find sessions where the agent got stuck in a loop"
    - "show me sessions with tool execution failures"
    - "agent my-agent with high cost and errors"

    The query is interpreted to extract relevant filters, and explicit filters
    in the request body override interpreted ones.

    Returns ranked sessions with relevance scores and highlight snippets
    showing which events matched the query.
    """
    # Start with the user's query
    search_query = request.query
    filters_applied: dict[str, Any] = {}

    # Interpret natural language if enabled
    if request.interpret_nl:
        from storage.search import SessionSearchService

        interpreted = SessionSearchService(repo.session, repo.tenant_id).interpret_nl_query(
            search_query
        )
        search_query = interpreted.pop("query", search_query)

        # Apply interpreted filters unless explicitly overridden
        for key, value in interpreted.items():
            if key not in {"query"} and value is not None:
                filters_applied[key] = value

    # Apply explicit filters from request (override interpreted ones)
    if request.status is not None:
        filters_applied["status"] = request.status
    if request.event_type is not None:
        filters_applied["event_type"] = request.event_type
    if request.agent_name is not None:
        filters_applied["agent_name"] = request.agent_name
    if request.tags:
        filters_applied["tags"] = request.tags
    if request.min_errors is not None:
        filters_applied["min_errors"] = request.min_errors

    # Parse datetime filters
    started_after = None
    started_before = None
    if request.started_after:
        try:
            started_after = datetime.fromisoformat(request.started_after.replace("Z", "+00:00"))
            filters_applied["started_after"] = request.started_after
        except ValueError:
            pass  # Invalid datetime, ignore filter
    if request.started_before:
        try:
            started_before = datetime.fromisoformat(request.started_before.replace("Z", "+00:00"))
            filters_applied["started_before"] = request.started_before
        except ValueError:
            pass  # Invalid datetime, ignore filter

    # Perform search with all filters
    sessions = await repo.search_sessions(
        search_query,
        status=filters_applied.get("status"),
        event_type=filters_applied.get("event_type"),
        agent_name=filters_applied.get("agent_name"),
        tags=filters_applied.get("tags"),
        started_after=started_after,
        started_before=started_before,
        min_errors=filters_applied.get("min_errors"),
        limit=request.limit,
    )

    # Build results
    results = [
        SearchResult(
            id=s.id,
            session_id=s.id,
            agent_name=s.agent_name or "",
            framework=s.framework or "",
            status=str(s.status),
            total_cost_usd=s.total_cost_usd,
            started_at=s.started_at.isoformat() if s.started_at else "",
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            errors=s.errors,
            tags=s.tags or [],
            fix_note=s.fix_note,
            similarity=getattr(s, "search_similarity", 0.0),
            highlights=[
                SearchHighlight(**h) for h in getattr(s, "search_highlights", [])
            ],
        )
        for s in sessions
    ]

    return NaturalLanguageSearchResponse(
        query=request.query,
        interpreted_query=search_query,
        total=len(results),
        results=results,
        filters_applied=filters_applied,
    )
