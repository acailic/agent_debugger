"""FastAPI endpoints for trace ingestion.

This module provides the HTTP API for the trace collector, including
endpoints for ingesting trace events, creating sessions, and health checks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    TraceEvent,
)
from auth.middleware import get_tenant_from_api_key
from redaction.pipeline import RedactionPipeline
from storage import TraceRepository

from .buffer import get_event_buffer
from .scorer import get_importance_scorer

# Input size limits for security (DoS prevention)
MAX_DATA_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
MAX_METADATA_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
MAX_NAME_LENGTH = 255


class TraceEventIngest(BaseModel):
    """Request model for ingesting trace events."""

    session_id: str
    parent_id: str | None = None
    event_type: str
    timestamp: str | None = None
    name: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    upstream_event_ids: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name_length(cls, v: str) -> str:
        """Validate name field length to prevent abuse."""
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"name must be {MAX_NAME_LENGTH} characters or less")
        return v

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate data dict size to prevent DoS attacks."""
        import json

        try:
            size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            size = len(str(v).encode("utf-8"))
        if size > MAX_DATA_SIZE_BYTES:
            raise ValueError(f"data must be {MAX_DATA_SIZE_BYTES} bytes or less")
        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate metadata dict size to prevent DoS attacks."""
        import json

        try:
            size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            size = len(str(v).encode("utf-8"))
        if size > MAX_METADATA_SIZE_BYTES:
            raise ValueError(f"metadata must be {MAX_METADATA_SIZE_BYTES} bytes or less")
        return v


class TraceEventResponse(BaseModel):
    """Response model for trace event ingestion."""

    event_id: str
    status: str = "queued"


class SessionCreate(BaseModel):
    """Request model for creating a session."""

    id: str | None = None
    agent_name: str
    framework: str
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


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

_session_maker: async_sessionmaker[AsyncSession] | None = None


def configure_storage(session_maker: async_sessionmaker[AsyncSession] | None) -> None:
    """Configure database access for collector routes."""
    global _session_maker
    _session_maker = session_maker


async def _get_tenant_id(request: Request, db: AsyncSession) -> str:
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


def _get_redaction_pipeline() -> RedactionPipeline:
    """Get redaction pipeline based on config."""
    return RedactionPipeline.from_config()


async def _persist_event_if_configured(event: TraceEvent, tenant_id: str = "local") -> None:
    """Persist an ingested event when storage is configured."""
    if _session_maker is None:
        return

    # Apply redaction before storage
    pipeline = _get_redaction_pipeline()
    event = pipeline.apply(event)

    async with _session_maker() as session:
        repo = TraceRepository(session, tenant_id=tenant_id)
        existing = await repo.get_session(event.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {event.session_id} not found",
            )
        await repo.add_event(event)


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


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    """Parse an ISO timestamp when provided by the caller."""
    if timestamp is None:
        return None
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _build_event(event_data: TraceEventIngest, event_type: EventType) -> TraceEvent:
    """Build a typed event so scoring and persistence can use structured fields."""
    timestamp = _parse_timestamp(event_data.timestamp)
    base_kwargs: dict[str, Any] = {
        "session_id": event_data.session_id,
        "parent_id": event_data.parent_id,
        "name": event_data.name,
        "metadata": event_data.metadata,
        "upstream_event_ids": event_data.upstream_event_ids,
    }
    if timestamp is not None:
        base_kwargs["timestamp"] = timestamp

    return TraceEvent.from_data(event_type, base_kwargs, event_data.data)


@router.post("/traces", response_model=TraceEventResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_trace(
    event_data: TraceEventIngest,
    request: Request,
) -> TraceEventResponse:
    """Ingest a trace event.

    Queues the event for processing and returns immediately with 202 Accepted.

    Args:
        event_data: Trace event data to ingest
        request: FastAPI request object for auth

    Returns:
        TraceEventResponse with event ID and status
    """
    buffer = get_event_buffer()
    scorer = get_importance_scorer()

    event_type = _parse_event_type(event_data.event_type)

    event = _build_event(event_data, event_type)

    event.importance = scorer.score(event)

    # Get tenant_id for persistence
    if _session_maker is not None:
        async with _session_maker() as db:
            tenant_id = await _get_tenant_id(request, db)
            await _persist_event_if_configured(event, tenant_id=tenant_id)
    else:
        await _persist_event_if_configured(event)

    await buffer.publish(event.session_id, event)

    return TraceEventResponse(event_id=event.id, status="queued")


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    request: Request,
) -> SessionResponse:
    """Create a new debugging session.

    Args:
        session_data: Session creation parameters
        request: FastAPI request object for auth

    Returns:
        SessionResponse with session details
    """
    session = Session(
        id=session_data.id or str(__import__("uuid").uuid4()),
        agent_name=session_data.agent_name,
        framework=session_data.framework,
        config=session_data.config,
        tags=session_data.tags,
    )
    if _session_maker is not None:
        async with _session_maker() as db_session:
            tenant_id = await _get_tenant_id(request, db_session)
            repo = TraceRepository(db_session, tenant_id=tenant_id)
            session = await repo.create_session(session)

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
