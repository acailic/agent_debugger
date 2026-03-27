"""Event repository for event CRUD operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.core.events import TraceEvent
from storage.converters import event_to_orm, orm_to_event
from storage.models import EventModel, SessionModel


class EventRepository:
    """Data access layer for event CRUD operations.

    Provides async methods for event management using SQLAlchemy async session.
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

    async def add_event(self, event: TraceEvent) -> TraceEvent:
        """Add a new event to the database.

        Args:
            event: TraceEvent instance to persist

        Returns:
            The created TraceEvent instance
        """
        db_event = event_to_orm(event, self.tenant_id)
        self.session.add(db_event)
        return orm_to_event(db_event)

    async def add_events_batch(self, events: list[TraceEvent]) -> list[TraceEvent]:
        """Add multiple events to the database in a single transaction.

        Args:
            events: List of TraceEvent instances to persist

        Returns:
            List of created TraceEvent instances
        """
        db_events = [event_to_orm(event, self.tenant_id) for event in events]
        self.session.add_all(db_events)
        return [orm_to_event(db) for db in db_events]

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
        return orm_to_event(db_event)

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
        return [orm_to_event(db) for db in result.scalars()]

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
        return [orm_to_event(db) for db in result.scalars()]
