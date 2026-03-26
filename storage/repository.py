"""Data access layer for sessions, events, and checkpoints.

This module provides the TraceRepository class with async methods for CRUD operations
on session management, event queries, checkpoint management, and search functionality.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from storage.models import AnomalyAlertModel, CheckpointModel, EventModel, SessionModel


@dataclass
class AnomalyAlertCreate:
    """Dataclass for creating anomaly alert records.

    Provides a typed alternative to passing raw dicts when creating alerts.
    """

    id: str
    session_id: str
    alert_type: str
    severity: float
    signal: str
    event_ids: list[str]
    detection_source: str
    detection_config: dict[str, Any]
    created_at: datetime | None = None


class TraceRepository:
    """Data access layer for sessions, events, and checkpoints.

    Provides async methods for CRUD operations using SQLAlchemy async session.
    All queries are scoped to a specific tenant_id for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession, tenant_id: str = "local"):
        """Initialize the repository with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation (default: "local")
        """
        self.session = session
        self.tenant_id = tenant_id

    async def create_session(self, session: Session) -> Session:
        """Create a new session record.

        Args:
            session: Session dataclass instance to persist

        Returns:
            The created Session instance
        """
        db_session = SessionModel(
            id=session.id,
            tenant_id=self.tenant_id,
            agent_name=session.agent_name,
            framework=session.framework,
            started_at=session.started_at,
            ended_at=session.ended_at,
            status=session.status,
            total_tokens=session.total_tokens,
            total_cost_usd=session.total_cost_usd,
            tool_calls=session.tool_calls,
            llm_calls=session.llm_calls,
            errors=session.errors,
            replay_value=session.replay_value,
            config=session.config,
            tags=session.tags,
        )
        self.session.add(db_session)
        return self._orm_to_session(db_session)

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            Session if found, None otherwise
        """
        result = await self.session.execute(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.tenant_id == self.tenant_id,
            )
        )
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return None
        return self._orm_to_session(db_session)

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        sort_by: str = "started_at",
    ) -> list[Session]:
        """List sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of Session instances
        """
        stmt = select(SessionModel).where(SessionModel.tenant_id == self.tenant_id)
        if sort_by == "replay_value":
            stmt = stmt.order_by(SessionModel.replay_value.desc(), SessionModel.started_at.desc())
        else:
            stmt = stmt.order_by(SessionModel.started_at.desc())

        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [self._orm_to_session(db) for db in result.scalars()]

    async def count_sessions(self) -> int:
        """Count total number of sessions.

        Returns:
            Total count of sessions in the database for the current tenant
        """
        result = await self.session.execute(
            select(func.count(SessionModel.id))
            .select_from(SessionModel)
            .where(SessionModel.tenant_id == self.tenant_id)
        )
        return result.scalar_one()

    async def update_session(self, session_id: str, **updates: Any) -> Session | None:
        """Update a session with the given field values.

        Args:
            session_id: Unique identifier of the session
            **updates: Field names and values to update

        Returns:
            Updated Session if found, None otherwise
        """
        valid_fields = {
            "agent_name",
            "framework",
            "ended_at",
            "status",
            "total_tokens",
            "total_cost_usd",
            "tool_calls",
            "llm_calls",
            "errors",
            "replay_value",
            "config",
            "tags",
            "fix_note",
        }
        filtered_updates = {k: v for k, v in updates.items() if k in valid_fields}
        if not filtered_updates:
            return await self.get_session(session_id)

        result = await self.session.execute(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.tenant_id == self.tenant_id,
            )
        )
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return None

        for field, value in filtered_updates.items():
            setattr(db_session, field, value)
        return self._orm_to_session(db_session)

    async def add_fix_note(self, session_id: str, note: str) -> Session | None:
        """Add or update a fix note for a session.

        Args:
            session_id: Unique identifier of the session
            note: The fix note text to add

        Returns:
            Updated Session if found, None otherwise
        """
        return await self.update_session(session_id, fix_note=note)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.tenant_id == self.tenant_id,
            )
        )
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return False

        await self.session.delete(db_session)
        return True

    async def add_event(self, event: TraceEvent) -> TraceEvent:
        """Add a new event to the database.

        Args:
            event: TraceEvent instance to persist

        Returns:
            The created TraceEvent instance
        """
        db_event = self._event_to_orm(event)
        self.session.add(db_event)
        return self._orm_to_event(db_event)

    async def add_events_batch(self, events: list[TraceEvent]) -> list[TraceEvent]:
        """Add multiple events to the database in a single transaction.

        Args:
            events: List of TraceEvent instances to persist

        Returns:
            List of created TraceEvent instances
        """
        db_events = [self._event_to_orm(event) for event in events]
        self.session.add_all(db_events)
        return [self._orm_to_event(db) for db in db_events]

    async def get_event(self, event_id: str) -> TraceEvent | None:
        """Retrieve an event by ID with tenant isolation.

        Args:
            event_id: Unique identifier of the event

        Returns:
            TraceEvent if found and belongs to current tenant, None otherwise
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(
                EventModel.id == event_id,
                SessionModel.tenant_id == self.tenant_id,
            )
        )
        db_event = result.scalar_one_or_none()
        if db_event is None:
            return None
        return self._orm_to_event(db_event)

    async def list_events(self, session_id: str, limit: int = 100, offset: int = 0) -> list[TraceEvent]:
        """List events for a session with pagination.

        Args:
            session_id: Session ID to filter events by
            limit: Maximum number of events to return
            offset: Number of events to skip

        Returns:
            List of TraceEvent instances
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(
                SessionModel.tenant_id == self.tenant_id,
                EventModel.session_id == session_id,
            )
            .order_by(EventModel.timestamp)
            .offset(offset)
            .limit(limit)
        )
        return [self._orm_to_event(db) for db in result.scalars()]

    async def get_event_tree(self, session_id: str) -> list[TraceEvent]:
        """Get all events for a session in hierarchical order.

        Events are returned in timestamp order for tree reconstruction.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent instances ordered by timestamp
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(
                SessionModel.tenant_id == self.tenant_id,
                EventModel.session_id == session_id,
            )
            .order_by(EventModel.timestamp)
        )
        return [self._orm_to_event(db) for db in result.scalars()]

    async def create_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Create a new checkpoint record.

        Args:
            checkpoint: Checkpoint dataclass instance to persist

        Returns:
            The created Checkpoint instance
        """
        db_checkpoint = CheckpointModel(
            id=checkpoint.id,
            tenant_id=self.tenant_id,
            session_id=checkpoint.session_id,
            event_id=checkpoint.event_id,
            sequence=checkpoint.sequence,
            state=checkpoint.state,
            memory=checkpoint.memory,
            timestamp=checkpoint.timestamp,
            importance=checkpoint.importance,
        )
        self.session.add(db_checkpoint)
        return self._orm_to_checkpoint(db_checkpoint)

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    async def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Retrieve a checkpoint by ID with tenant isolation.

        Args:
            checkpoint_id: Unique identifier of the checkpoint

        Returns:
            Checkpoint if found and belongs to current tenant, None otherwise
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(CheckpointModel)
            .join(SessionModel, CheckpointModel.session_id == SessionModel.id)
            .options(selectinload(CheckpointModel.event))
            .where(
                CheckpointModel.id == checkpoint_id,
                SessionModel.tenant_id == self.tenant_id,
            )
        )
        db_checkpoint = result.scalar_one_or_none()
        if db_checkpoint is None:
            return None
        return self._orm_to_checkpoint(db_checkpoint)

    async def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """List all checkpoints for a session.

        Args:
            session_id: Session ID to filter checkpoints by

        Returns:
            List of Checkpoint instances ordered by timestamp
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(CheckpointModel)
            .join(SessionModel, CheckpointModel.session_id == SessionModel.id)
            .options(selectinload(CheckpointModel.event))
            .where(
                SessionModel.tenant_id == self.tenant_id,
                CheckpointModel.session_id == session_id,
            )
            .order_by(CheckpointModel.timestamp)
        )
        return [self._orm_to_checkpoint(db) for db in result.scalars()]

    async def get_high_importance_checkpoints(self, session_id: str, limit: int = 10) -> list[Checkpoint]:
        """Get checkpoints with high importance scores.

        Args:
            session_id: Session ID to filter checkpoints by
            limit: Maximum number of checkpoints to return

        Returns:
            List of high-importance Checkpoint instances
        """
        # Join with SessionModel to ensure tenant isolation
        result = await self.session.execute(
            select(CheckpointModel)
            .join(SessionModel, CheckpointModel.session_id == SessionModel.id)
            .options(selectinload(CheckpointModel.event))
            .where(
                SessionModel.tenant_id == self.tenant_id,
                CheckpointModel.session_id == session_id,
                CheckpointModel.importance >= 0.8,
            )
            .order_by(CheckpointModel.importance.desc())
            .limit(limit)
        )
        return [self._orm_to_checkpoint(db) for db in result.scalars()]

    async def search_events(
        self,
        query: str,
        session_id: str | None = None,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[TraceEvent]:
        """Search events by name or data content.

        Args:
            query: Search string to match against event name
            session_id: Optional session ID to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching TraceEvent instances
        """
        # Escape SQL LIKE wildcards to prevent unintended pattern matching.
        # Without this, a user searching for "test_" would match "testA" because
        # `_` is a single-character wildcard in SQL LIKE patterns.
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{escaped_query}%"

        # Join with SessionModel to ensure tenant isolation
        stmt = (
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(SessionModel.tenant_id == self.tenant_id)
            .where(
                or_(
                    EventModel.name.ilike(search_term),
                    EventModel.event_type.ilike(search_term),
                    cast(EventModel.data, String).ilike(search_term),
                    cast(EventModel.event_metadata, String).ilike(search_term),
                )
            )
            .order_by(EventModel.timestamp.desc())
            .limit(limit)
        )

        if session_id:
            stmt = stmt.where(EventModel.session_id == session_id)
        if event_type:
            stmt = stmt.where(EventModel.event_type == event_type)

        result = await self.session.execute(stmt)
        return [self._orm_to_event(db) for db in result.scalars()]

    def _event_to_orm(self, event: TraceEvent) -> EventModel:
        """Convert a TraceEvent dataclass to an EventModel ORM instance.

        Args:
            event: TraceEvent instance to convert

        Returns:
            EventModel instance
        """
        data = event.to_storage_data()

        event_metadata = dict(event.metadata)
        event_metadata["upstream_event_ids"] = list(event.upstream_event_ids)

        return EventModel(
            id=event.id,
            tenant_id=self.tenant_id,
            session_id=event.session_id,
            parent_id=event.parent_id,
            event_type=str(event.event_type),
            timestamp=event.timestamp,
            name=event.name,
            data=data,
            event_metadata=event_metadata,
            importance=event.importance,
        )

    def _orm_to_event(self, db_event: EventModel) -> TraceEvent:
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

    def _orm_to_session(self, db_session: SessionModel) -> Session:
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

    def _orm_to_checkpoint(self, db_checkpoint: CheckpointModel) -> Checkpoint:
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

    # ------------------------------------------------------------------
    # Anomaly Alert Methods
    # ------------------------------------------------------------------

    async def create_anomaly_alert(self, alert: AnomalyAlertModel | AnomalyAlertCreate) -> AnomalyAlertModel:
        """Create a new anomaly alert record.

        Args:
            alert: AnomalyAlertModel or AnomalyAlertCreate instance to persist

        Returns:
            The created AnomalyAlertModel instance

        Raises:
            ValueError: If alert is a dict with missing required fields
            TypeError: If alert is not AnomalyAlertModel or AnomalyAlertCreate
        """
        if isinstance(alert, AnomalyAlertModel):
            self.session.add(alert)
            return alert

        if isinstance(alert, AnomalyAlertCreate):
            model = AnomalyAlertModel(
                id=alert.id,
                tenant_id=self.tenant_id,
                session_id=alert.session_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                signal=alert.signal,
                event_ids=alert.event_ids,
                detection_source=alert.detection_source,
                detection_config=alert.detection_config,
                created_at=alert.created_at,
            )
            self.session.add(model)
            return model

        raise TypeError(f"Expected AnomalyAlertModel or AnomalyAlertCreate, got {type(alert).__name__}")

    async def list_anomaly_alerts(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[AnomalyAlertModel]:
        """List anomaly alerts for a session.

        Args:
            session_id: Session ID to filter alerts by
            limit: Maximum number of alerts to return

        Returns:
            List of AnomalyAlertModel instances
        """
        result = await self.session.execute(
            select(AnomalyAlertModel)
            .where(
                AnomalyAlertModel.tenant_id == self.tenant_id,
                AnomalyAlertModel.session_id == session_id,
            )
            .order_by(AnomalyAlertModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_anomaly_alert(self, alert_id: str) -> AnomalyAlertModel | None:
        """Retrieve an anomaly alert by ID.

        Args:
            alert_id: Unique identifier of the alert

        Returns:
            AnomalyAlertModel if found, None otherwise
        """
        result = await self.session.execute(
            select(AnomalyAlertModel).where(
                AnomalyAlertModel.id == alert_id,
                AnomalyAlertModel.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()
