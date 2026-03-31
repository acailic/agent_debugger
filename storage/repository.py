"""Facade for data access layer for sessions, events, and checkpoints.

This module provides the TraceRepository class as a facade that composes
entity-specific repositories while maintaining a unified public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from storage.converters import event_to_orm, orm_to_checkpoint, orm_to_event, orm_to_session
from storage.models import AnomalyAlertModel, CheckpointModel, EventModel, SessionModel
from storage.repositories.alert_repo import AnomalyAlertRepository
from storage.repositories.checkpoint_repo import CheckpointRepository
from storage.repositories.event_repo import EventRepository
from storage.repositories.session_repo import SessionRepository
from storage.search import SessionSearchService


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
    """Facade for data access layer for sessions, events, and checkpoints.

    Provides async methods for CRUD operations using SQLAlchemy async session.
    All queries are scoped to a specific tenant_id for multi-tenant isolation.

    This class delegates to entity-specific repositories while maintaining
    the same public API for backward compatibility.
    """

    def __init__(self, session: AsyncSession, tenant_id: str = "local"):
        """Initialize the repository with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation (default: "local")
        """
        self.session = session
        self.tenant_id = tenant_id

        # Initialize entity repositories
        self._session_repo = SessionRepository(session, tenant_id)
        self._event_repo = EventRepository(session, tenant_id)
        self._checkpoint_repo = CheckpointRepository(session, tenant_id)
        self._alert_repo = AnomalyAlertRepository(session, tenant_id)

    # ------------------------------------------------------------------
    # Session Methods (delegated to SessionRepository)
    # ------------------------------------------------------------------

    async def create_session(self, session: Session) -> Session:
        """Create a new session record.

        Args:
            session: Session dataclass instance to persist

        Returns:
            The created Session instance
        """
        return await self._session_repo.create_session(session)

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            Session if found, None otherwise
        """
        return await self._session_repo.get_session(session_id)

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
        return await self._session_repo.list_sessions(limit, offset, sort_by=sort_by)

    async def count_sessions(self) -> int:
        """Count total number of sessions.

        Returns:
            Total count of sessions in the database for the current tenant
        """
        return await self._session_repo.count_sessions()

    async def update_session(self, session_id: str, **updates: Any) -> Session | None:
        """Update a session with the given field values.

        Args:
            session_id: Unique identifier of the session
            **updates: Field names and values to update

        Returns:
            Updated Session if found, None otherwise
        """
        return await self._session_repo.update_session(session_id, **updates)

    async def add_fix_note(self, session_id: str, note: str) -> Session | None:
        """Add or update a fix note for a session.

        Args:
            session_id: Unique identifier of the session
            note: The fix note text to add

        Returns:
            Updated Session if found, None otherwise
        """
        return await self._session_repo.add_fix_note(session_id, note)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            True if deleted, False if not found
        """
        return await self._session_repo.delete_session(session_id)

    # ------------------------------------------------------------------
    # Event Methods (delegated to EventRepository)
    # ------------------------------------------------------------------

    async def add_event(self, event: TraceEvent) -> TraceEvent:
        """Add a new event to the database.

        Automatically increments session.errors when an ERROR event is added.

        Args:
            event: TraceEvent instance to persist

        Returns:
            The created TraceEvent instance
        """
        result = await self._event_repo.add_event(event)
        if event.event_type.value == "error":
            await self._increment_session_error_count(event.session_id)
        return result

    async def add_events_batch(self, events: list[TraceEvent]) -> list[TraceEvent]:
        """Add multiple events to the database in a single transaction.

        Automatically increments session.errors for each ERROR event in the batch.

        Args:
            events: List of TraceEvent instances to persist

        Returns:
            List of created TraceEvent instances
        """
        results = await self._event_repo.add_events_batch(events)
        # Group error events by session_id and batch-increment
        error_counts: dict[str, int] = {}
        for event in events:
            if event.event_type.value == "error":
                error_counts[event.session_id] = error_counts.get(event.session_id, 0) + 1
        for session_id, count in error_counts.items():
            await self._increment_session_error_count(session_id, count)
        return results

    async def _increment_session_error_count(self, session_id: str, count: int = 1) -> None:
        """Increment the errors counter on a session.

        Uses SQL-level atomic increment to avoid read-modify-write races.
        Silently skips if the session does not exist.
        """
        from sqlalchemy import update

        from storage.models import SessionModel

        stmt = (
            update(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.tenant_id == self.tenant_id,
            )
            .values(errors=SessionModel.errors + count)
        )
        await self.session.execute(stmt)

    async def get_event(self, event_id: str) -> TraceEvent | None:
        """Retrieve an event by ID with tenant isolation.

        Args:
            event_id: Unique identifier of the event

        Returns:
            TraceEvent if found and belongs to current tenant, None otherwise
        """
        return await self._event_repo.get_event(event_id)

    async def list_events(self, session_id: str, limit: int = 100, offset: int = 0) -> list[TraceEvent]:
        """List events for a session with pagination.

        Args:
            session_id: Session ID to filter events by
            limit: Maximum number of events to return
            offset: Number of events to skip

        Returns:
            List of TraceEvent instances
        """
        return await self._event_repo.list_events(session_id, limit, offset)

    async def get_event_tree(self, session_id: str) -> list[TraceEvent]:
        """Get all events for a session in hierarchical order.

        Events are returned in timestamp order for tree reconstruction.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent instances ordered by timestamp
        """
        return await self._event_repo.get_event_tree(session_id)

    async def get_events(self, session_id: str) -> tuple[list[TraceEvent], int]:
        """Get events for a session with count.

        This method is used by drift/baseline endpoints that need both
        the events list and total count.

        Args:
            session_id: Session ID to get events for

        Returns:
            Tuple of (events list, total count)
        """
        events = await self._event_repo.get_event_tree(session_id)
        return events, len(events)

    # ------------------------------------------------------------------
    # Checkpoint Methods (delegated to CheckpointRepository)
    # ------------------------------------------------------------------

    async def create_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Create a new checkpoint record.

        Args:
            checkpoint: Checkpoint dataclass instance to persist

        Returns:
            The created Checkpoint instance
        """
        return await self._checkpoint_repo.create_checkpoint(checkpoint)

    async def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Retrieve a checkpoint by ID with tenant isolation.

        Args:
            checkpoint_id: Unique identifier of the checkpoint

        Returns:
            Checkpoint if found and belongs to current tenant, None otherwise
        """
        return await self._checkpoint_repo.get_checkpoint(checkpoint_id)

    async def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """List all checkpoints for a session.

        Args:
            session_id: Session ID to filter checkpoints by

        Returns:
            List of Checkpoint instances ordered by timestamp
        """
        return await self._checkpoint_repo.list_checkpoints(session_id)

    async def get_high_importance_checkpoints(self, session_id: str, limit: int = 10) -> list[Checkpoint]:
        """Get checkpoints with high importance scores.

        Args:
            session_id: Session ID to filter checkpoints by
            limit: Maximum number of checkpoints to return

        Returns:
            List of high-importance Checkpoint instances
        """
        return await self._checkpoint_repo.get_high_importance_checkpoints(session_id, limit)

    # ------------------------------------------------------------------
    # Anomaly Alert Methods (delegated to AnomalyAlertRepository)
    # ------------------------------------------------------------------

    async def create_anomaly_alert(self, alert: AnomalyAlertModel | AnomalyAlertCreate) -> AnomalyAlertModel:
        """Create a new anomaly alert record.

        Args:
            alert: AnomalyAlertModel or AnomalyAlertCreate instance to persist

        Returns:
            The created AnomalyAlertModel instance

        Raises:
            TypeError: If alert is not AnomalyAlertModel or AnomalyAlertCreate
        """
        if isinstance(alert, AnomalyAlertModel):
            return await self._alert_repo.create_anomaly_alert(alert)

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
            return await self._alert_repo.create_anomaly_alert(model)

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
        return await self._alert_repo.list_anomaly_alerts(session_id, limit)

    async def get_anomaly_alert(self, alert_id: str) -> AnomalyAlertModel | None:
        """Retrieve an anomaly alert by ID.

        Args:
            alert_id: Unique identifier of the alert

        Returns:
            AnomalyAlertModel if found, None otherwise
        """
        return await self._alert_repo.get_anomaly_alert(alert_id)

    # ------------------------------------------------------------------
    # Transaction Management
    # ------------------------------------------------------------------

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    # ------------------------------------------------------------------
    # Search Methods (exposed via search property)
    # ------------------------------------------------------------------

    @property
    def search(self) -> SessionSearchService:
        """Get the search service for this repository.

        Returns:
            SessionSearchService instance scoped to this repository's session and tenant
        """
        return SessionSearchService(self.session, self.tenant_id)

    async def search_sessions(
        self,
        query: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Session]:
        """Search sessions by semantic similarity to a text query.

        Delegates to SessionSearchService.search_sessions for backward compatibility.

        Args:
            query: Search query text
            status: Optional session status to filter by (e.g., "error", "completed")
            limit: Maximum number of results to return

        Returns:
            List of Session instances with search_similarity attribute set, ranked by similarity
        """
        return await self.search.search_sessions(query, status=status, limit=limit)

    async def search_events(
        self,
        query: str,
        session_id: str | None = None,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[TraceEvent]:
        """Search events by name or data content.

        Delegates to SessionSearchService.search_events for backward compatibility.

        Args:
            query: Search string to match against event name
            session_id: Optional session ID to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching TraceEvent instances
        """
        return await self.search.search_events(query, session_id=session_id, event_type=event_type, limit=limit)

    # ------------------------------------------------------------------
    # Cost Aggregation Methods
    # ------------------------------------------------------------------

    async def get_cost_summary(self) -> dict:
        """Get aggregate cost statistics across all sessions.

        Returns:
            Dictionary containing:
                - total_cost_usd: Total cost across all sessions
                - session_count: Total number of sessions
                - avg_cost_per_session: Average cost per session
                - by_framework: List of dicts with framework, session_count, and total_cost_usd
        """
        # Get overall aggregates
        result = await self.session.execute(
            select(
                func.count(SessionModel.id).label("session_count"),
                func.sum(SessionModel.total_cost_usd).label("total_cost"),
            ).where(SessionModel.tenant_id == self.tenant_id)
        )
        row = result.one()
        session_count = row.session_count or 0
        total_cost = float(row.total_cost or 0)

        # Per-framework breakdown
        fw_result = await self.session.execute(
            select(
                SessionModel.framework,
                func.count(SessionModel.id).label("count"),
                func.sum(SessionModel.total_cost_usd).label("total"),
            )
            .where(SessionModel.tenant_id == self.tenant_id)
            .group_by(SessionModel.framework)
        )
        by_framework = [
            {"framework": fw, "session_count": cnt, "total_cost_usd": float(tot or 0)}
            for fw, cnt, tot in fw_result.all()
        ]

        return {
            "total_cost_usd": round(total_cost, 6),
            "session_count": session_count,
            "avg_cost_per_session": round(total_cost / session_count, 6) if session_count else 0.0,
            "by_framework": by_framework,
        }

    # ------------------------------------------------------------------
    # ORM Conversion Methods (exposed for testing and backward compatibility)
    # ------------------------------------------------------------------

    def _event_to_orm(self, event: TraceEvent) -> EventModel:
        """Convert a TraceEvent dataclass to an EventModel ORM instance.

        Args:
            event: TraceEvent instance to convert

        Returns:
            EventModel instance
        """
        return event_to_orm(event, self.tenant_id)

    def _orm_to_event(self, db_event: EventModel) -> TraceEvent:
        """Convert an EventModel ORM instance to the appropriate TraceEvent subclass.

        Args:
            db_event: EventModel instance to convert

        Returns:
            Appropriate TraceEvent subclass instance
        """
        return orm_to_event(db_event)

    def _orm_to_session(self, db_session: SessionModel) -> Session:
        """Convert a SessionModel ORM instance to a Session dataclass.

        Args:
            db_session: SessionModel instance to convert

        Returns:
            Session dataclass instance
        """
        return orm_to_session(db_session)

    def _orm_to_checkpoint(self, db_checkpoint: CheckpointModel) -> Checkpoint:
        """Convert a CheckpointModel ORM instance to a Checkpoint dataclass.

        Args:
            db_checkpoint: CheckpointModel instance to convert

        Returns:
            Checkpoint dataclass instance
        """
        return orm_to_checkpoint(db_checkpoint)
