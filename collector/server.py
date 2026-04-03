"""FastAPI endpoints for trace ingestion.

This module provides the HTTP API for the trace collector, including
endpoints for ingesting trace events, creating sessions, and health checks.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    TraceEvent,
)
from agent_debugger_sdk.core.scorer import get_importance_scorer
from auth.middleware import get_tenant_from_api_key
from redaction.pipeline import RedactionPipeline
from storage import TraceRepository

from .buffer import get_event_buffer

# Input size limits for security (DoS prevention)
MAX_DATA_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
MAX_METADATA_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
MAX_NAME_LENGTH = 255


class TraceEventIngest(BaseModel):
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
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"name must be {MAX_NAME_LENGTH} characters or less")
        return v

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: dict[str, Any]) -> dict[str, Any]:
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
        try:
            size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            size = len(str(v).encode("utf-8"))
        if size > MAX_METADATA_SIZE_BYTES:
            raise ValueError(f"metadata must be {MAX_METADATA_SIZE_BYTES} bytes or less")
        return v


class TraceEventResponse(BaseModel):
    event_id: str
    status: str = "queued"


class SessionCreate(BaseModel):
    id: str | None = None
    agent_name: str
    framework: str
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class SessionResponse(BaseModel):
    id: str
    agent_name: str
    framework: str
    status: str
    started_at: str


class HealthResponse(BaseModel):
    status: str


router = APIRouter(
    prefix="/api",
    tags=["collector"],
)

_session_maker: async_sessionmaker[AsyncSession] | None = None


@dataclass(frozen=True)
class CollectorDependencies:
    session_maker: async_sessionmaker[AsyncSession] | None
    buffer: Any
    scorer: Any
    tenant_resolver: Callable[[Request, AsyncSession], Awaitable[str]]
    redaction_pipeline_factory: Callable[[], RedactionPipeline]


def configure_storage(session_maker: async_sessionmaker[AsyncSession] | None) -> None:
    global _session_maker
    _session_maker = session_maker


def _resolve_dependencies(
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    buffer: Any | None = None,
    scorer: Any | None = None,
    tenant_resolver: Callable[[Request, AsyncSession], Awaitable[str]] | None = None,
    redaction_pipeline_factory: Callable[[], RedactionPipeline] | None = None,
) -> CollectorDependencies:
    return CollectorDependencies(
        session_maker=_session_maker if session_maker is None else session_maker,
        buffer=get_event_buffer() if buffer is None else buffer,
        scorer=get_importance_scorer() if scorer is None else scorer,
        tenant_resolver=_get_tenant_id if tenant_resolver is None else tenant_resolver,
        redaction_pipeline_factory=(
            _get_redaction_pipeline if redaction_pipeline_factory is None else redaction_pipeline_factory
        ),
    )


async def _get_tenant_id(request: Request, db: AsyncSession) -> str:
    config = get_config()
    if config.mode == "local":
        client_host = getattr(getattr(request, "client", None), "host", None)
        if client_host and client_host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Local mode only accepts requests from localhost",
            )
        return "local"
    return await get_tenant_from_api_key(request, db)


def _get_redaction_pipeline() -> RedactionPipeline:
    return RedactionPipeline.from_config()


async def _persist_event_if_configured(
    event: TraceEvent,
    tenant_id: str = "local",
    *,
    dependencies: CollectorDependencies | None = None,
    db_session: AsyncSession | None = None,
) -> None:
    deps = dependencies or _resolve_dependencies()
    if deps.session_maker is None and db_session is None:
        return

    pipeline = deps.redaction_pipeline_factory()
    event = pipeline.apply(event)

    if db_session is not None:
        repo = TraceRepository(db_session, tenant_id=tenant_id)
        existing = await repo.get_session(event.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {event.session_id} not found",
            )
        await repo.add_event(event)
        await repo.commit()
        return

    assert deps.session_maker is not None
    async with deps.session_maker() as session:
        repo = TraceRepository(session, tenant_id=tenant_id)
        existing = await repo.get_session(event.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {event.session_id} not found",
            )
        await repo.add_event(event)
        await repo.commit()


def _parse_event_type(event_type_str: str) -> EventType:
    try:
        return EventType(event_type_str)
    except ValueError:
        valid_types = [e.value for e in EventType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type. Must be one of: {valid_types}",
        )


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _build_event(event_data: TraceEventIngest, event_type: EventType) -> TraceEvent:
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


async def _ingest_trace(
    event_data: TraceEventIngest,
    request: Request,
    *,
    dependencies: CollectorDependencies | None = None,
) -> TraceEventResponse:
    deps = dependencies or _resolve_dependencies()

    event_type = _parse_event_type(event_data.event_type)
    event = _build_event(event_data, event_type)
    event.importance = deps.scorer.score(event)

    if deps.session_maker is not None:
        async with deps.session_maker() as db:
            tenant_id = await deps.tenant_resolver(request, db)
            await _persist_event_if_configured(event, tenant_id=tenant_id, dependencies=deps, db_session=db)
    else:
        await _persist_event_if_configured(event, dependencies=deps)

    await deps.buffer.publish(event.session_id, event)

    return TraceEventResponse(event_id=event.id, status="queued")


@router.post("/traces", response_model=TraceEventResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_trace(
    event_data: TraceEventIngest,
    request: Request,
) -> TraceEventResponse:
    return await _ingest_trace(event_data, request)


async def _create_session(
    session_data: SessionCreate,
    request: Request,
    *,
    dependencies: CollectorDependencies | None = None,
) -> SessionResponse:
    deps = dependencies or _resolve_dependencies()
    session = Session(
        id=session_data.id or str(uuid.uuid4()),
        agent_name=session_data.agent_name,
        framework=session_data.framework,
        config=session_data.config,
        tags=session_data.tags,
    )
    if deps.session_maker is not None:
        async with deps.session_maker() as db_session:
            tenant_id = await deps.tenant_resolver(request, db_session)
            repo = TraceRepository(db_session, tenant_id=tenant_id)
            existing = await repo.get_session(session.id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Session {session.id} already exists",
                )
            try:
                session = await repo.create_session(session)
                await repo.commit()
            except IntegrityError as exc:
                await repo.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Session {session.id} already exists",
                ) from exc

    return SessionResponse(
        id=session.id,
        agent_name=session.agent_name,
        framework=session.framework,
        status=session.status,
        started_at=session.started_at.isoformat(),
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    request: Request,
) -> SessionResponse:
    return await _create_session(session_data, request)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
