"""FastAPI application factory with session CRUD, trace query, and SSE streaming.

This module provides the main FastAPI application for the Agent Debugger API,
including session management, trace queries, checkpoint access, and real-time
SSE streaming for live debugging sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint
from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events import TraceEvent
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.config import get_config
from auth.middleware import get_tenant_from_api_key
from collector.buffer import get_event_buffer
from collector.intelligence import TraceIntelligence
from collector.replay import build_replay
from collector.replay import build_tree
from collector.server import configure_storage
from collector.server import router as collector_router
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from storage.engine import create_db_engine, create_session_maker
from storage import Base
from storage import TraceRepository
from redaction.pipeline import RedactionPipeline


class SessionListResponse(BaseModel):
    """Response model for session list."""

    sessions: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseModel):
    """Response model for session details."""

    session: dict[str, Any]


class TraceListResponse(BaseModel):
    """Response model for trace list."""

    traces: list[dict[str, Any]]
    session_id: str


class DecisionTreeResponse(BaseModel):
    """Response model for decision tree."""

    session_id: str
    events: list[dict[str, Any]]


class CheckpointListResponse(BaseModel):
    """Response model for checkpoint list."""

    checkpoints: list[dict[str, Any]]
    session_id: str


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    deleted: bool
    session_id: str


class TraceBundleResponse(BaseModel):
    """Response model for a normalized session trace bundle."""

    session: dict[str, Any]
    events: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    tree: dict[str, Any] | None
    analysis: dict[str, Any]


class ReplayResponse(BaseModel):
    """Response model for replay requests."""

    session_id: str
    mode: str
    focus_event_id: str | None
    start_index: int
    events: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    nearest_checkpoint: dict[str, Any] | None
    breakpoints: list[dict[str, Any]]
    failure_event_ids: list[str]


class AnalysisResponse(BaseModel):
    """Response model for trace analysis."""

    session_id: str
    analysis: dict[str, Any]


class LiveSummaryResponse(BaseModel):
    """Response model for live monitoring summaries."""

    session_id: str
    live_summary: dict[str, Any]


class TraceSearchResponse(BaseModel):
    """Response model for trace search results."""

    query: str
    session_id: str | None
    event_type: str | None
    total: int
    results: list[dict[str, Any]]


engine = create_db_engine()
async_session_maker = create_session_maker(engine)
trace_intelligence = TraceIntelligence()


async def get_db_session() -> AsyncSession:
    """Dependency to get database session.

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with async_session_maker() as session:
        yield session


async def get_tenant_id(request: Request, db: AsyncSession = Depends(get_db_session)) -> str:
    """Get tenant_id — from API key in cloud mode, 'local' in local mode.

    Args:
        request: The FastAPI request object
        db: Database session for API key validation

    Returns:
        The tenant_id for the current request
    """
    config = get_config()
    if config.mode == "local":
        return "local"
    return await get_tenant_from_api_key(request, db)


def get_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
) -> TraceRepository:
    """Dependency to get TraceRepository instance.

    Args:
        session: Database session from dependency
        tenant_id: Tenant ID from auth dependency

    Returns:
        TraceRepository instance scoped to tenant_id
    """
    return TraceRepository(session, tenant_id=tenant_id)


async def _persist_session_start(session: Session) -> None:
    async with async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        existing = await repo.get_session(session.id)
        if existing is None:
            await repo.create_session(session)


async def _persist_session_update(session: Session) -> None:
    async with async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        await repo.update_session(
            session.id,
            agent_name=session.agent_name,
            framework=session.framework,
            ended_at=session.ended_at,
            status=session.status,
            total_tokens=session.total_tokens,
            total_cost_usd=session.total_cost_usd,
            tool_calls=session.tool_calls,
            llm_calls=session.llm_calls,
            errors=session.errors,
            config=session.config,
            tags=session.tags,
        )


def _get_redaction_pipeline() -> RedactionPipeline:
    """Get redaction pipeline based on config."""
    from agent_debugger_sdk.config import get_config
    config = get_config()
    return RedactionPipeline(
        redact_prompts=config.redact_prompts,
        redact_pii=False,  # Could be another config option
        max_payload_kb=config.max_payload_kb,
    )


async def _persist_event(event: TraceEvent) -> None:
    # Apply redaction before storage
    pipeline = _get_redaction_pipeline()
    event = pipeline.apply(event)
    async with async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        await repo.add_event(event)


async def _persist_checkpoint(checkpoint: Checkpoint) -> None:
    async with async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_checkpoint(checkpoint)


def _normalize_session(session: Session, analysis_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = session.to_dict()
    if analysis_summary:
        normalized.update(analysis_summary)
    return normalized


def _normalize_event(event: TraceEvent) -> dict[str, Any]:
    return event.to_dict()


def _normalize_checkpoint(checkpoint: Checkpoint) -> dict[str, Any]:
    return checkpoint.to_dict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Database — config-driven
    from storage.engine import get_database_url
    if "sqlite" in get_database_url():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Buffer — config-driven
    from collector import create_buffer
    buffer_backend = "redis" if os.environ.get("REDIS_URL") else "memory"
    buffer = create_buffer(backend=buffer_backend)

    # Wire pipeline
    configure_event_pipeline(
        buffer,
        persist_event=_persist_event,
        persist_checkpoint=_persist_checkpoint,
        persist_session_start=_persist_session_start,
        persist_session_update=_persist_session_update,
    )

    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    from agent_debugger_sdk.config import get_config
    config = get_config()

    # Database — config-driven
    from storage.engine import create_db_engine, create_session_maker
    engine = create_db_engine()
    session_maker = create_session_maker(engine)

    app = FastAPI(
        lifespan=lifespan,
        title="Agent Debugger API",
        description="API for debugging and visualizing AI agent executions",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(collector_router)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/api/sessions", response_model=SessionListResponse)
    async def list_sessions(
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        sort_by: str = Query(default="started_at", pattern="^(started_at|replay_value)$"),
        repo: TraceRepository = Depends(get_repository),
    ) -> SessionListResponse:
        """List debugging sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            repo: TraceRepository instance

        Returns:
            SessionListResponse with paginated sessions
        """
        total = await repo.count_sessions()
        if sort_by == "replay_value":
            sessions = await repo.list_sessions(limit=total, offset=0)
            ranked_sessions: list[dict[str, Any]] = []
            for session in sessions:
                events = await repo.get_event_tree(session.id)
                checkpoints = await repo.list_checkpoints(session.id)
                analysis = trace_intelligence.analyze_session(events, checkpoints)
                ranked_sessions.append(
                    _normalize_session(
                        session,
                        {
                            "replay_value": analysis["session_replay_value"],
                            "retention_tier": analysis["retention_tier"],
                            "failure_count": analysis["session_summary"]["failure_count"],
                            "behavior_alert_count": analysis["session_summary"]["behavior_alert_count"],
                            "representative_event_id": analysis["representative_failure_ids"][0] if analysis["representative_failure_ids"] else None,
                        },
                    )
                )
            ranked_sessions.sort(
                key=lambda session_data: (
                    session_data.get("replay_value") or 0.0,
                    session_data["started_at"],
                ),
                reverse=True,
            )
            paginated_sessions = ranked_sessions[offset : offset + limit]
        else:
            sessions = await repo.list_sessions(limit=limit, offset=offset)
            paginated_sessions = [_normalize_session(session) for session in sessions]

        return SessionListResponse(
            sessions=paginated_sessions,
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    async def get_session(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> SessionDetailResponse:
        """Get session details by ID.

        Args:
            session_id: Unique session identifier
            repo: TraceRepository instance

        Returns:
            SessionDetailResponse with session data

        Raises:
            HTTPException: If session not found
        """
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        return SessionDetailResponse(session=session.to_dict())

    @app.delete("/api/sessions/{session_id}", response_model=DeleteResponse)
    async def delete_session(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> DeleteResponse:
        """Delete a session by ID.

        Args:
            session_id: Unique session identifier
            repo: TraceRepository instance

        Returns:
            DeleteResponse with deletion status

        Raises:
            HTTPException: If session not found
        """
        deleted = await repo.delete_session(session_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        return DeleteResponse(deleted=True, session_id=session_id)

    @app.get("/api/sessions/{session_id}/traces", response_model=TraceListResponse)
    async def get_session_traces(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=10000),
        repo: TraceRepository = Depends(get_repository),
    ) -> TraceListResponse:
        """Get all traces for a session.

        Args:
            session_id: Unique session identifier
            limit: Maximum number of traces to return
            repo: TraceRepository instance

        Returns:
            TraceListResponse with trace events

        Raises:
            HTTPException: If session not found
        """
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        traces = await repo.list_events(session_id, limit=limit)
        return TraceListResponse(
            traces=[t.to_dict() for t in traces],
            session_id=session_id,
        )

    @app.get("/api/sessions/{session_id}/trace", response_model=TraceBundleResponse)
    async def get_trace_bundle(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> TraceBundleResponse:
        """Return a normalized trace bundle used by the frontend."""
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        events = await repo.get_event_tree(session_id)
        checkpoints = await repo.list_checkpoints(session_id)
        analysis = trace_intelligence.analyze_session(events, checkpoints)
        return TraceBundleResponse(
            session=_normalize_session(session),
            events=[_normalize_event(event) for event in events],
            checkpoints=[_normalize_checkpoint(checkpoint) for checkpoint in checkpoints],
            tree=build_tree(events),
            analysis=analysis,
        )

    @app.get("/api/sessions/{session_id}/tree", response_model=DecisionTreeResponse)
    async def get_decision_tree(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> DecisionTreeResponse:
        """Get the decision tree for a session.

        Returns all events in hierarchical order for tree reconstruction.

        Args:
            session_id: Unique session identifier
            repo: TraceRepository instance

        Returns:
            DecisionTreeResponse with all events ordered by timestamp

        Raises:
            HTTPException: If session not found
        """
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        events = await repo.get_event_tree(session_id)
        return DecisionTreeResponse(
            session_id=session_id,
            events=[e.to_dict() for e in events],
        )

    @app.get("/api/sessions/{session_id}/checkpoints", response_model=CheckpointListResponse)
    async def list_checkpoints(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> CheckpointListResponse:
        """List all checkpoints for a session.

        Args:
            session_id: Unique session identifier
            repo: TraceRepository instance

        Returns:
            CheckpointListResponse with checkpoints

        Raises:
            HTTPException: If session not found
        """
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        checkpoints = await repo.list_checkpoints(session_id)
        return CheckpointListResponse(
            checkpoints=[c.to_dict() for c in checkpoints],
            session_id=session_id,
        )

    @app.get("/api/sessions/{session_id}/stream")
    async def stream_session_events(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> StreamingResponse:
        """Stream session events via Server-Sent Events (SSE).

        Provides real-time updates for a debugging session.

        Args:
            session_id: Unique session identifier
            repo: TraceRepository instance

        Returns:
            StreamingResponse with text/event-stream content type

        Raises:
            HTTPException: If session not found
        """
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        return StreamingResponse(
            _event_generator(session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/sessions/{session_id}/analysis", response_model=AnalysisResponse)
    async def get_session_analysis(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> AnalysisResponse:
        """Analyze a session for replay value, recurrence, and behavior signals."""
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        events = await repo.get_event_tree(session_id)
        checkpoints = await repo.list_checkpoints(session_id)
        return AnalysisResponse(
            session_id=session_id,
            analysis=trace_intelligence.analyze_session(events, checkpoints),
        )

    @app.get("/api/sessions/{session_id}/live", response_model=LiveSummaryResponse)
    async def get_session_live_summary(
        session_id: str,
        repo: TraceRepository = Depends(get_repository),
    ) -> LiveSummaryResponse:
        """Return a live monitoring summary for the current persisted session state."""
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        events = await repo.get_event_tree(session_id)
        checkpoints = await repo.list_checkpoints(session_id)
        return LiveSummaryResponse(
            session_id=session_id,
            live_summary=trace_intelligence.build_live_summary(events, checkpoints),
        )

    @app.get("/api/traces/search", response_model=TraceSearchResponse)
    async def search_traces(
        query: str = Query(min_length=1),
        session_id: str | None = Query(default=None),
        event_type: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        repo: TraceRepository = Depends(get_repository),
    ) -> TraceSearchResponse:
        """Search trace events across sessions or within a single session."""
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
            results=[_normalize_event(event) for event in results],
        )

    @app.get("/api/sessions/{session_id}/replay", response_model=ReplayResponse)
    async def replay_session(
        session_id: str,
        mode: str = Query(default="full", pattern="^(full|focus|failure)$"),
        focus_event_id: str | None = Query(default=None),
        breakpoint_event_types: str | None = Query(default=None),
        breakpoint_tool_names: str | None = Query(default=None),
        breakpoint_confidence_below: float | None = Query(default=None, ge=0.0, le=1.0),
        breakpoint_safety_outcomes: str | None = Query(default=None),
        repo: TraceRepository = Depends(get_repository),
    ) -> ReplayResponse:
        """Replay a session from the nearest checkpoint plus suffix."""
        session = await repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        events = await repo.get_event_tree(session_id)
        checkpoints = await repo.list_checkpoints(session_id)
        if not events:
            return ReplayResponse(
                session_id=session_id,
                mode=mode,
                focus_event_id=focus_event_id,
                start_index=0,
                events=[],
                checkpoints=[],
                nearest_checkpoint=None,
                breakpoints=[],
                failure_event_ids=[],
            )

        replay_data = build_replay(
            events,
            checkpoints,
            mode=mode,
            focus_event_id=focus_event_id,
            breakpoint_event_types={item for item in (breakpoint_event_types or "").split(",") if item},
            breakpoint_tool_names={item for item in (breakpoint_tool_names or "").split(",") if item},
            breakpoint_confidence_below=breakpoint_confidence_below,
            breakpoint_safety_outcomes={item for item in (breakpoint_safety_outcomes or "").split(",") if item},
        )

        return ReplayResponse(
            session_id=session_id,
            mode=replay_data["mode"],
            focus_event_id=replay_data["focus_event_id"],
            start_index=replay_data["start_index"],
            events=replay_data["events"],
            checkpoints=replay_data["checkpoints"],
            nearest_checkpoint=replay_data["nearest_checkpoint"],
            breakpoints=replay_data["breakpoints"],
            failure_event_ids=replay_data["failure_event_ids"],
        )

    return app


async def _event_generator(session_id: str):
    """Generate SSE events for a session.

    Subscribes to the event buffer and yields events as they arrive.
    Includes keepalive mechanism to prevent connection timeouts.

    Args:
        session_id: Session ID to stream events for

    Yields:
        SSE formatted event strings
    """
    buffer = get_event_buffer()
    queue = await buffer.subscribe(session_id)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        await buffer.unsubscribe(session_id, queue)


app = create_app()
