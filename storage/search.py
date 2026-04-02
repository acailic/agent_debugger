"""Search service for sessions and events.

This module provides the SessionSearchService class for semantic search
functionality over sessions and events.
"""

from __future__ import annotations

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent_debugger_sdk.core.events import Session, TraceEvent
from storage.converters import orm_to_event, orm_to_session
from storage.embedding import build_session_embedding, cosine_similarity, text_to_vector
from storage.models import EventModel, SessionModel


class SessionSearchService:
    """Service for searching sessions and events.

    Provides semantic similarity search over sessions using bag-of-words
    embeddings, and text search over events using SQL LIKE patterns.
    All queries are scoped to a specific tenant_id for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession, tenant_id: str):
        """Initialize the search service with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation
        """
        self.session = session
        self.tenant_id = tenant_id

    async def search_sessions(
        self,
        query: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Session]:
        """Search sessions by semantic similarity to a text query.

        Uses bag-of-words cosine similarity against session event embeddings.
        Searches across event_type, name, error_type, error_message, tool_name, and model fields.

        Args:
            query: Search query text
            status: Optional session status to filter by (e.g., "error", "completed")
            limit: Maximum number of results to return

        Returns:
            List of Session instances with search_similarity attribute set, ranked by similarity
        """
        if not query or not query.strip():
            return []

        query_vec = text_to_vector(query)
        if not query_vec:
            return []

        db_sessions = await self._load_candidate_sessions(status=status)
        if not db_sessions:
            return []

        scored = self._score_sessions(db_sessions, query_vec)
        return self._build_ranked_session_results(scored, limit)

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
                    EventModel.name.ilike(search_term, escape="\\"),
                    EventModel.event_type.ilike(search_term, escape="\\"),
                    cast(EventModel.data, String).ilike(search_term, escape="\\"),
                    cast(EventModel.event_metadata, String).ilike(search_term, escape="\\"),
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

        return [orm_to_event(db) for db in result.scalars()]

    async def _load_candidate_sessions(self, *, status: str | None) -> list[SessionModel]:
        """Fetch recent tenant-scoped sessions with events eagerly loaded."""
        candidate_limit = 500
        stmt = (
            select(SessionModel)
            .options(selectinload(SessionModel.events))
            .where(SessionModel.tenant_id == self.tenant_id)
            .order_by(SessionModel.started_at.desc())
            .limit(candidate_limit)
        )
        if status:
            stmt = stmt.where(SessionModel.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _score_sessions(
        self,
        db_sessions: list[SessionModel],
        query_vec: dict[str, float],
    ) -> list[tuple[float, SessionModel]]:
        """Return positive-scoring sessions paired with cosine similarity."""
        scored: list[tuple[float, SessionModel]] = []
        for db_session in db_sessions:
            similarity = self._score_session(db_session, query_vec)
            if similarity > 0.0:
                scored.append((similarity, db_session))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _score_session(self, db_session: SessionModel, query_vec: dict[str, float]) -> float:
        """Compute semantic similarity between a query vector and a stored session."""
        event_dicts = [self._embedding_event_dict(db_event) for db_event in db_session.events]
        session_vec = build_session_embedding(event_dicts)
        return cosine_similarity(query_vec, session_vec)

    def _embedding_event_dict(self, db_event) -> dict[str, str]:
        """Flatten searchable event fields into an embedding payload."""
        event_dict = {
            "event_type": db_event.event_type,
            "name": db_event.name,
        }
        event_dict.update(self._embedding_data_fields(db_event.data))
        return event_dict

    def _embedding_data_fields(self, event_data: dict | None) -> dict[str, str]:
        """Extract nested event fields that contribute to semantic search."""
        if not event_data:
            return {}

        searchable_fields = ("error_type", "error_message", "tool_name", "model")
        return {field_name: event_data[field_name] for field_name in searchable_fields if field_name in event_data}

    def _build_ranked_session_results(
        self,
        scored_sessions: list[tuple[float, SessionModel]],
        limit: int,
    ) -> list[Session]:
        """Convert scored ORM sessions into API models with attached similarity."""
        results: list[Session] = []
        for similarity, db_session in scored_sessions[:limit]:
            session = orm_to_session(db_session)
            session.search_similarity = similarity
            results.append(session)
        return results
