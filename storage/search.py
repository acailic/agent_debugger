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

        # Fetch candidate sessions with eager-loaded events (limit to prevent unbounded memory usage)
        CANDIDATE_LIMIT = 500
        stmt = (
            select(SessionModel)
            .options(selectinload(SessionModel.events))
            .where(SessionModel.tenant_id == self.tenant_id)
            .order_by(SessionModel.started_at.desc())
            .limit(CANDIDATE_LIMIT)
        )
        if status:
            stmt = stmt.where(SessionModel.status == status)

        result = await self.session.execute(stmt)
        db_sessions = list(result.scalars().all())

        if not db_sessions:
            return []

        # Build similarity scores
        scored: list[tuple[float, SessionModel]] = []
        for db_sess in db_sessions:
            # Events are already loaded via selectinload
            db_events = db_sess.events

            # Build event dicts with flattened data for embedding
            event_dicts = []
            for e in db_events:
                event_dict = {
                    "event_type": e.event_type,
                    "name": e.name,
                }
                # Flatten nested fields from data
                if e.data:
                    if "error_type" in e.data:
                        event_dict["error_type"] = e.data["error_type"]
                    if "error_message" in e.data:
                        event_dict["error_message"] = e.data["error_message"]
                    if "tool_name" in e.data:
                        event_dict["tool_name"] = e.data["tool_name"]
                    if "model" in e.data:
                        event_dict["model"] = e.data["model"]
                event_dicts.append(event_dict)

            session_vec = build_session_embedding(event_dicts)
            sim = cosine_similarity(query_vec, session_vec)
            if sim > 0.0:
                scored.append((sim, db_sess))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[Session] = []
        for sim, db_sess in scored[:limit]:
            session = orm_to_session(db_sess)
            session.search_similarity = sim
            results.append(session)

        return results

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
