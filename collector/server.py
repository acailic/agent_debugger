"""FastAPI endpoints for trace ingestion.

This module provides the HTTP API for the trace collector, including
endpoints for ingesting trace events, creating sessions, and health checks.
"""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import TraceEvent
from agent_debugger_sdk.core.session import get_session_manager
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel

from .buffer import get_event_buffer
from .scorer import get_importance_scorer


class TraceEventIngest(BaseModel):
    """Request model for ingesting trace events."""

    session_id: str
    parent_id: str | None = None
    event_type: str
    timestamp: str | None = None
    name: str = ""
    data: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class TraceEventResponse(BaseModel):
    """Response model for trace event ingestion."""

    event_id: str
    status: str = "queued"


class SessionCreate(BaseModel):
    """Request model for creating a session."""

    agent_name: str
    framework: str
    config: dict[str, Any] = {}
    tags: list[str] = []


class SessionResponse(BaseModel):
    """Response model for session creation."""

    id: str
    agent_name: str
    framework: str
    status: str
    started_at: str


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str


router = APIRouter(
    prefix="/api",
    tags=["collector"],
)


def _parse_event_type(event_type_str: str) -> EventType:
    """Parse event type string to EventType enum.

    Args:
        event_type_str: String representation of event type

    Returns:
        EventType enum value

    Raises:
        HTTPException: If event type is invalid
    """
    try:
        return EventType(event_type_str)
    except ValueError:
        valid_types = [e.value for e in EventType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type. Must be one of: {valid_types}",
        )


@router.post("/traces", response_model=TraceEventResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_trace(event_data: TraceEventIngest) -> TraceEventResponse:
    """Ingest a trace event.

    Queues the event for processing and returns immediately with 202 Accepted.

    Args:
        event_data: Trace event data to ingest

    Returns:
        TraceEventResponse with event ID and status
    """
    buffer = get_event_buffer()
    scorer = get_importance_scorer()

    event_type = _parse_event_type(event_data.event_type)

    event = TraceEvent(
        session_id=event_data.session_id,
        parent_id=event_data.parent_id,
        event_type=event_type,
        name=event_data.name,
        data=event_data.data,
        metadata=event_data.metadata,
    )

    event.importance = scorer.score(event)

    await buffer.publish(event.session_id, event)

    return TraceEventResponse(event_id=event.id, status="queued")


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(session_data: SessionCreate) -> SessionResponse:
    """Create a new debugging session.

    Args:
        session_data: Session creation parameters

    Returns:
        SessionResponse with session details
    """
    manager = get_session_manager()

    session = manager.create_session(
        agent_name=session_data.agent_name,
        framework=session_data.framework,
        config=session_data.config,
        tags=session_data.tags,
    )

    return SessionResponse(
        id=session.id,
        agent_name=session.agent_name,
        framework=session.framework,
        status=session.status,
        started_at=session.started_at.isoformat(),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        HealthResponse with status
    """
    return HealthResponse(status="ok")
