"""Entity repository for entity CRUD operations.

This module provides the EntityRepository class for managing extracted entities
from trace events, including persistence and querying.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.entities import Entity, EntityExtractor, EntityType, get_top_entities
from storage.models import EventModel, SessionModel


class EntityRepository:
    """Data access layer for entity extraction and querying.

    Provides async methods to extract entities from stored events and query
    entity statistics. All queries are scoped to a specific tenant_id for
    multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession, tenant_id: str = "local"):
        """Initialize the repository with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation (default: "local")
        """
        self.session = session
        self.tenant_id = tenant_id
        self.extractor = EntityExtractor()

    async def extract_entities_from_session(self, session_id: str) -> dict[str, Entity]:
        """Extract entities from all events in a session.

        Args:
            session_id: Session ID to extract entities from

        Returns:
            Dictionary of extracted entities keyed by entity_type:value
        """
        events = await self._load_session_events(session_id)
        event_dicts = [self._event_to_dict(db_event) for db_event in events]
        return self.extractor.extract_from_events(event_dicts)

    async def extract_entities_from_all_sessions(self) -> dict[str, Entity]:
        """Extract entities from all events across all sessions.

        Returns:
            Dictionary of extracted entities keyed by entity_type:value
        """
        events = await self._load_all_events()
        event_dicts = [self._event_to_dict(db_event) for db_event in events]
        return self.extractor.extract_from_events(event_dicts)

    async def get_top_entities(
        self,
        entity_type: str | None = None,
        limit: int = 10,
        sort_by: str = "count",
    ) -> list[dict]:
        """Get top entities by type and metric.

        Args:
            entity_type: Optional entity type to filter by (e.g., 'tool_name', 'error_type')
            limit: Maximum number of entities to return
            sort_by: Metric to sort by ('count', 'session_count', 'value')

        Returns:
            List of entity dictionaries sorted by the specified metric
        """
        entities = await self.extract_entities_from_all_sessions()
        return get_top_entities(entities, entity_type=entity_type, limit=limit, sort_by=sort_by)

    async def get_top_tools(self, limit: int = 10, sort_by: str = "count") -> list[dict]:
        """Get top tool names by usage frequency.

        Args:
            limit: Maximum number of tools to return
            sort_by: Metric to sort by ('count', 'session_count')

        Returns:
            List of tool entity dictionaries with usage statistics
        """
        return await self.get_top_entities(entity_type=EntityType.TOOL_NAME, limit=limit, sort_by=sort_by)

    async def get_top_errors(self, limit: int = 10, sort_by: str = "count") -> list[dict]:
        """Get top error types by occurrence frequency.

        Args:
            limit: Maximum number of error types to return
            sort_by: Metric to sort by ('count', 'session_count')

        Returns:
            List of error entity dictionaries with occurrence statistics
        """
        return await self.get_top_entities(entity_type=EntityType.ERROR_TYPE, limit=limit, sort_by=sort_by)

    async def get_top_models(self, limit: int = 10) -> list[dict]:
        """Get top LLM models by usage frequency.

        Args:
            limit: Maximum number of models to return

        Returns:
            List of model entity dictionaries with usage statistics
        """
        return await self.get_top_entities(entity_type=EntityType.MODEL, limit=limit, sort_by="count")

    async def get_entity_summary(self) -> dict[str, int]:
        """Get summary statistics for all entity types.

        Returns:
            Dictionary with entity type as key and count as value
        """
        entities = await self.extract_entities_from_all_sessions()
        summary: dict[str, int] = {}

        for entity in entities.values():
            summary[entity.entity_type] = summary.get(entity.entity_type, 0) + 1

        return summary

    async def _load_session_events(self, session_id: str) -> list[EventModel]:
        """Load all events for a specific session with tenant isolation.

        Args:
            session_id: Session ID to load events for

        Returns:
            List of EventModel instances
        """
        stmt = (
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(
                SessionModel.tenant_id == self.tenant_id,
                EventModel.session_id == session_id,
            )
            .order_by(EventModel.timestamp)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_all_events(self) -> list[EventModel]:
        """Load all events across all sessions with tenant isolation.

        Returns:
            List of EventModel instances
        """
        stmt = (
            select(EventModel)
            .join(SessionModel, EventModel.session_id == SessionModel.id)
            .where(SessionModel.tenant_id == self.tenant_id)
            .order_by(EventModel.timestamp)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _event_to_dict(self, db_event: EventModel) -> dict:
        """Convert an EventModel to a dictionary for entity extraction.

        Args:
            db_event: EventModel instance

        Returns:
            Dictionary representation of the event
        """
        return {
            "id": db_event.id,
            "session_id": db_event.session_id,
            "event_type": db_event.event_type,
            "name": db_event.name,
            "data": db_event.data or {},
            "event_metadata": db_event.event_metadata or {},
            "timestamp": db_event.timestamp.isoformat() if db_event.timestamp else None,
        }
