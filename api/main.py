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

from agent_debugger_sdk.core.context import configure_event_pipeline
from collector.buffer import get_event_buffer
from collector.server import router as collector_router
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from storage import Base
from storage import TraceRepository


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


DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./agent_debugger.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncSession:
    """Dependency to get database session.

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with async_session_maker() as session:
        yield session


def get_repository(session: AsyncSession = Depends(get_db_session)) -> TraceRepository:
    """Dependency to get TraceRepository instance.

    Args:
        session: Database session from dependency

    Returns:
        TraceRepository instance
    """
    return TraceRepository(session)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Configure event pipeline to connect SDK to EventBuffer
    configure_event_pipeline(get_event_buffer())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        lifespan=lifespan,
        title="Agent Debugger API",
        description="API for debugging and visualizing AI agent executions",
        version="1.0.0",
    )

    # Read CORS origins from environment variable for production configurability
    # Default to wildcard for development convenience
    cors_origins_str = os.environ.get("AGENT_DEBUGGER_CORS_ORIGINS", "*")
    cors_origins = [origin.strip() for origin in cors_origins_str.split(",")] if cors_origins_str != "*" else ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(collector_router)

    @app.get("/api/sessions", response_model=SessionListResponse)
    async def list_sessions(
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
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
        sessions = await repo.list_sessions(limit=limit, offset=offset)
        total = await repo.count_sessions()
        return SessionListResponse(
            sessions=[s.to_dict() for s in sessions],
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
        offset: int = Query(default=0, ge=0),
        repo: TraceRepository = Depends(get_repository),
    ) -> TraceListResponse:
        """Get all traces for a session.

        Args:
            session_id: Unique session identifier
            limit: Maximum number of traces to return
            offset: Number of traces to skip
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

        traces = await repo.list_events(session_id, limit=limit, offset=offset)
        return TraceListResponse(
            traces=[t.to_dict() for t in traces],
            session_id=session_id,
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
