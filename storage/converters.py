"""ORM conversion utilities for sessions, events, and checkpoints.

This module provides pure conversion functions between domain models (Session,
TraceEvent, Checkpoint) and ORM models (SessionModel, EventModel, CheckpointModel).
"""

from __future__ import annotations

from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from storage.models import CheckpointModel, EventModel, SessionModel


def event_to_orm(event: TraceEvent, tenant_id: str) -> EventModel:
    """Convert a TraceEvent dataclass to an EventModel ORM instance.

    Args:
        event: TraceEvent instance to convert
        tenant_id: Tenant identifier for data isolation

    Returns:
        EventModel instance
    """
    data = event.to_storage_data()

    event_metadata = dict(event.metadata)
    event_metadata["upstream_event_ids"] = list(event.upstream_event_ids)

    return EventModel(
        id=event.id,
        tenant_id=tenant_id,
        session_id=event.session_id,
        parent_id=event.parent_id,
        event_type=str(event.event_type),
        timestamp=event.timestamp,
        name=event.name,
        data=data,
        event_metadata=event_metadata,
        importance=event.importance,
    )


def orm_to_event(db_event: EventModel) -> TraceEvent:
    """Convert an EventModel ORM instance to the appropriate TraceEvent subclass.

    Args:
        db_event: EventModel instance to convert

    Returns:
        Appropriate TraceEvent subclass instance
    """
    data = dict(db_event.data or {})
    event_type = EventType(db_event.event_type) if db_event.event_type else EventType.AGENT_START
    event_metadata = dict(db_event.event_metadata or {})
    upstream_event_ids = event_metadata.pop("upstream_event_ids", [])

    base_kwargs = {
        "id": db_event.id,
        "session_id": db_event.session_id,
        "parent_id": db_event.parent_id,
        "timestamp": db_event.timestamp,
        "name": db_event.name,
        "metadata": event_metadata,
        "importance": db_event.importance,
        "upstream_event_ids": upstream_event_ids,
    }
    return TraceEvent.from_data(event_type, base_kwargs, data)


def orm_to_session(db_session: SessionModel) -> Session:
    """Convert a SessionModel ORM instance to a Session dataclass.

    Args:
        db_session: SessionModel instance to convert

    Returns:
        Session dataclass instance
    """
    return Session(
        id=db_session.id,
        agent_name=db_session.agent_name,
        framework=db_session.framework,
        started_at=db_session.started_at,
        ended_at=db_session.ended_at,
        status=SessionStatus(db_session.status),
        total_tokens=db_session.total_tokens,
        total_cost_usd=db_session.total_cost_usd,
        tool_calls=db_session.tool_calls,
        llm_calls=db_session.llm_calls,
        errors=db_session.errors,
        replay_value=db_session.replay_value,
        config=db_session.config,
        tags=db_session.tags,
        fix_note=db_session.fix_note,
    )


def orm_to_checkpoint(db_checkpoint: CheckpointModel) -> Checkpoint:
    """Convert a CheckpointModel ORM instance to a Checkpoint dataclass.

    Args:
        db_checkpoint: CheckpointModel instance to convert

    Returns:
        Checkpoint dataclass instance
    """
    return Checkpoint(
        id=db_checkpoint.id,
        session_id=db_checkpoint.session_id,
        event_id=db_checkpoint.event_id,
        sequence=db_checkpoint.sequence,
        state=db_checkpoint.state,
        memory=db_checkpoint.memory,
        timestamp=db_checkpoint.timestamp,
        importance=db_checkpoint.importance,
    )
