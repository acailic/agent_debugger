"""FastAPI endpoints for trace ingestion.

This module provides the HTTP API for the trace collector, including
endpoints for ingesting trace events, creating sessions, and health checks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.events import AgentTurnEvent
from agent_debugger_sdk.core.events import BehaviorAlertEvent
from agent_debugger_sdk.core.events import DecisionEvent
from agent_debugger_sdk.core.events import ErrorEvent
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import LLMRequestEvent
from agent_debugger_sdk.core.events import LLMResponseEvent
from agent_debugger_sdk.core.events import PolicyViolationEvent
from agent_debugger_sdk.core.events import PromptPolicyEvent
from agent_debugger_sdk.core.events import RefusalEvent
from agent_debugger_sdk.core.events import SafetyCheckEvent
from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events import ToolCallEvent
from agent_debugger_sdk.core.events import ToolResultEvent
from agent_debugger_sdk.core.events import TraceEvent
from auth.middleware import get_tenant_from_api_key
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from storage import TraceRepository

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
    upstream_event_ids: list[str] = []


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


async def _persist_event_if_configured(event: TraceEvent, tenant_id: str = "local") -> None:
    """Persist an ingested event when storage is configured."""
    if _session_maker is None:
        return

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
        "event_type": event_type,
        "name": event_data.name,
        "data": event_data.data,
        "metadata": event_data.metadata,
        "upstream_event_ids": event_data.upstream_event_ids,
    }
    if timestamp is not None:
        base_kwargs["timestamp"] = timestamp

    if event_type == EventType.TOOL_CALL:
        return ToolCallEvent(
            **base_kwargs,
            tool_name=event_data.data.get("tool_name", ""),
            arguments=event_data.data.get("arguments", {}),
        )
    if event_type == EventType.TOOL_RESULT:
        return ToolResultEvent(
            **base_kwargs,
            tool_name=event_data.data.get("tool_name", ""),
            result=event_data.data.get("result"),
            error=event_data.data.get("error"),
            duration_ms=event_data.data.get("duration_ms", 0.0),
        )
    if event_type == EventType.LLM_REQUEST:
        return LLMRequestEvent(
            **base_kwargs,
            model=event_data.data.get("model", ""),
            messages=event_data.data.get("messages", []),
            tools=event_data.data.get("tools", []),
            settings=event_data.data.get("settings", {}),
        )
    if event_type == EventType.LLM_RESPONSE:
        return LLMResponseEvent(
            **base_kwargs,
            model=event_data.data.get("model", ""),
            content=event_data.data.get("content", ""),
            tool_calls=event_data.data.get("tool_calls", []),
            usage=event_data.data.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            cost_usd=event_data.data.get("cost_usd", 0.0),
            duration_ms=event_data.data.get("duration_ms", 0.0),
        )
    if event_type == EventType.DECISION:
        return DecisionEvent(
            **base_kwargs,
            reasoning=event_data.data.get("reasoning", ""),
            confidence=event_data.data.get("confidence", 0.5),
            evidence=event_data.data.get("evidence", []),
            evidence_event_ids=event_data.data.get("evidence_event_ids", []),
            alternatives=event_data.data.get("alternatives", []),
            chosen_action=event_data.data.get("chosen_action", ""),
        )
    if event_type == EventType.SAFETY_CHECK:
        return SafetyCheckEvent(
            **base_kwargs,
            policy_name=event_data.data.get("policy_name", ""),
            outcome=event_data.data.get("outcome", "pass"),
            risk_level=event_data.data.get("risk_level", "low"),
            rationale=event_data.data.get("rationale", ""),
            blocked_action=event_data.data.get("blocked_action"),
            evidence=event_data.data.get("evidence", []),
        )
    if event_type == EventType.REFUSAL:
        return RefusalEvent(
            **base_kwargs,
            reason=event_data.data.get("reason", ""),
            policy_name=event_data.data.get("policy_name", ""),
            risk_level=event_data.data.get("risk_level", "medium"),
            blocked_action=event_data.data.get("blocked_action"),
            safe_alternative=event_data.data.get("safe_alternative"),
        )
    if event_type == EventType.POLICY_VIOLATION:
        return PolicyViolationEvent(
            **base_kwargs,
            policy_name=event_data.data.get("policy_name", ""),
            severity=event_data.data.get("severity", "medium"),
            violation_type=event_data.data.get("violation_type", ""),
            details=event_data.data.get("details", {}),
        )
    if event_type == EventType.PROMPT_POLICY:
        return PromptPolicyEvent(
            **base_kwargs,
            template_id=event_data.data.get("template_id", ""),
            policy_parameters=event_data.data.get("policy_parameters", {}),
            speaker=event_data.data.get("speaker", ""),
            state_summary=event_data.data.get("state_summary", ""),
            goal=event_data.data.get("goal", ""),
        )
    if event_type == EventType.AGENT_TURN:
        return AgentTurnEvent(
            **base_kwargs,
            agent_id=event_data.data.get("agent_id", ""),
            speaker=event_data.data.get("speaker", ""),
            turn_index=event_data.data.get("turn_index", 0),
            goal=event_data.data.get("goal", ""),
            content=event_data.data.get("content", ""),
        )
    if event_type == EventType.BEHAVIOR_ALERT:
        return BehaviorAlertEvent(
            **base_kwargs,
            alert_type=event_data.data.get("alert_type", ""),
            severity=event_data.data.get("severity", "medium"),
            signal=event_data.data.get("signal", ""),
            related_event_ids=event_data.data.get("related_event_ids", []),
        )
    if event_type == EventType.ERROR:
        return ErrorEvent(
            **base_kwargs,
            error_type=event_data.data.get("error_type", ""),
            error_message=event_data.data.get("error_message", ""),
            stack_trace=event_data.data.get("stack_trace"),
        )
    return TraceEvent(**base_kwargs)


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
