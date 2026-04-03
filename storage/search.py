"""Search service for sessions and events.

This module provides the SessionSearchService class for semantic search
functionality over sessions and events with natural language query support.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.core.events import Session, TraceEvent
from storage.converters import orm_to_event, orm_to_session
from storage.embedding import build_session_embedding, cosine_similarity, text_to_vector
from storage.models import EventModel, SessionModel


class SearchHighlight:
    """Represents a highlighted match in a search result."""

    def __init__(
        self,
        event_id: str,
        event_type: str,
        field_name: str,
        matched_text: str,
        relevance: float,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.field_name = field_name
        self.matched_text = matched_text
        self.relevance = relevance

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "field_name": self.field_name,
            "matched_text": self.matched_text,
            "relevance": self.relevance,
        }


class SessionSearchService:
    """Service for searching sessions and events.

    Provides semantic similarity search over sessions using bag-of-words
    embeddings, and text search over events using SQL LIKE patterns.
    All queries are scoped to a specific tenant_id for multi-tenant isolation.

    Supports natural language queries that are interpreted into structured filters.
    """

    # Natural language query patterns
    NL_PATTERNS = {
        "stuck in a loop": {"min_errors": 1, "query": "loop repeat retry again"},
        "tool execution failures": {"event_type": "tool_result", "query": "tool error failed"},
        "llm errors": {"event_type": "error", "query": "llm error api rate limit"},
        "safety violations": {"event_type": "policy_violation", "query": "safety violation blocked"},
        "high cost": {"query": "expensive cost tokens"},
        "timeout": {"query": "timeout slow"},
        "failed": {"status": "error", "query": "error failure"},
        "completed": {"status": "completed", "query": "done finished"},
        "running": {"status": "running", "query": "active ongoing"},
    }
    AGENT_NAME_PATTERNS = (
        re.compile(r'\bagent\s+named\s+["\']?([\w-]+)["\']?', re.IGNORECASE),
        re.compile(r'\bagent\s+["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(r"\bagent\s+([\w-]+)\b", re.IGNORECASE),
    )
    AGENT_NAME_STOPWORDS = {
        "a",
        "an",
        "and",
        "for",
        "got",
        "has",
        "in",
        "is",
        "named",
        "or",
        "stuck",
        "that",
        "the",
        "where",
        "with",
    }

    def __init__(self, session: AsyncSession, tenant_id: str):
        """Initialize the search service with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation
        """
        self.session = session
        self.tenant_id = tenant_id

    def interpret_nl_query(self, query: str) -> dict[str, Any]:
        """Interpret natural language query into structured search parameters.

        Detects patterns like "sessions with tool failures" or "agent stuck in loop"
        and extracts corresponding filters.

        Args:
            query: Natural language search query

        Returns:
            Dictionary with extracted filters and refined query string
        """
        params: dict[str, Any] = {"query": query}
        query_lower = query.lower()

        # Check for known patterns
        for pattern, filters in self.NL_PATTERNS.items():
            if pattern in query_lower:
                # Apply filters from pattern
                if "status" in filters:
                    params["status"] = filters["status"]
                if "event_type" in filters:
                    params["event_type"] = filters["event_type"]
                if "min_errors" in filters:
                    params["min_errors"] = filters["min_errors"]

                # Refine query for semantic search
                if "query" in filters:
                    params["query"] = f"{query} {filters['query']}"

        # Extract agent name only from explicit naming phrases like
        # "agent my-agent" or "agent named my-agent". Avoid parsing
        # "the agent got stuck..." into an agent filter.
        agent_name = self._extract_agent_name(query)
        if agent_name:
            params["agent_name"] = agent_name

        # Extract tags if mentioned
        tag_matches = re.findall(r'tag:\s*([\w-]+)', query_lower)
        if tag_matches:
            params["tags"] = tag_matches

        return params

    def _extract_agent_name(self, query: str) -> str | None:
        """Extract an explicitly named agent from a natural language query."""
        for pattern in self.AGENT_NAME_PATTERNS:
            match = pattern.search(query)
            if not match:
                continue
            agent_name = match.group(1).strip().strip("\"'")
            if agent_name.lower() not in self.AGENT_NAME_STOPWORDS:
                return agent_name
        return None

    async def search_sessions(
        self,
        query: str,
        *,
        status: str | None = None,
        event_type: str | None = None,
        agent_name: str | None = None,
        tags: list[str] | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        min_errors: int | None = None,
        limit: int = 20,
    ) -> list[Session]:
        """Search sessions by semantic similarity to a text query with advanced filters.

        Uses bag-of-words cosine similarity against session event embeddings.
        Searches across event_type, name, error_type, error_message, tool_name, and model fields.

        Args:
            query: Search query text (supports natural language like "sessions with tool failures")
            status: Optional session status to filter by (e.g., "error", "completed")
            event_type: Optional event type to filter sessions by
            agent_name: Optional agent name to filter by
            tags: Optional list of tags to filter sessions by (sessions must have at least one)
            started_after: Optional start time filter (sessions started after this datetime)
            started_before: Optional start time filter (sessions started before this datetime)
            min_errors: Minimum error count for sessions to include
            limit: Maximum number of results to return

        Returns:
            List of Session instances with search_similarity and search_highlights attributes set,
            ranked by similarity
        """
        if not query or not query.strip():
            return []

        query_vec = text_to_vector(query)
        if not query_vec:
            return []

        db_sessions = await self._load_candidate_sessions(
            status=status,
            event_type=event_type,
            agent_name=agent_name,
            tags=tags,
            started_after=started_after,
            started_before=started_before,
            min_errors=min_errors,
        )
        if not db_sessions:
            return []

        scored, highlights = await self._score_sessions_with_highlights(db_sessions, query_vec)
        return self._build_ranked_session_results(scored, highlights, limit)

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

    async def _load_candidate_sessions(
        self,
        *,
        status: str | None = None,
        event_type: str | None = None,
        agent_name: str | None = None,
        tags: list[str] | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        min_errors: int | None = None,
    ) -> list[SessionModel]:
        """Fetch tenant-scoped sessions without eager-loading all events.

        Events are loaded lazily on demand in _score_session to avoid the
        O(n*m) cost of eagerly loading every event for every candidate session.

        Supports filtering by status, event_type, agent_name, tags, time range, and error count.
        """
        stmt = (
            select(SessionModel)
            .where(SessionModel.tenant_id == self.tenant_id)
            .order_by(SessionModel.started_at.desc())
        )

        if status:
            stmt = stmt.where(SessionModel.status == status)
        if agent_name:
            stmt = stmt.where(SessionModel.agent_name == agent_name)
        if started_after:
            stmt = stmt.where(SessionModel.started_at >= started_after)
        if started_before:
            stmt = stmt.where(SessionModel.started_at <= started_before)
        if min_errors is not None:
            stmt = stmt.where(SessionModel.errors >= min_errors)

        # For tags and event_type filtering, we need to check JSON fields
        # Tags are stored as JSON array in the tags column
        # For SQLite, we need to use json_each or string matching
        if tags:
            # For SQLite, check if any tag is in the JSON array
            # This works for both SQLite and PostgreSQL
            from sqlalchemy import or_

            tag_conditions = []
            for tag in tags:
                # For SQLite: cast tags to string and check if tag is present
                # This is a simple approach that works for JSON arrays stored as text
                tag_conditions.append(
                    cast(SessionModel.tags, String).like(f'%"{tag}"%')
                )
            if tag_conditions:
                stmt = stmt.where(or_(*tag_conditions))

        if event_type:
            event_type_str = event_type.value if hasattr(event_type, "value") else event_type
            event_subq = (
                select(EventModel.session_id)
                .where(
                    EventModel.tenant_id == self.tenant_id,
                    EventModel.event_type == event_type_str,
                )
                .scalar_subquery()
            )
            stmt = stmt.where(SessionModel.id.in_(event_subq))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _score_sessions(
        self,
        db_sessions: list[SessionModel],
        query_vec: dict[str, float],
    ) -> list[tuple[float, SessionModel]]:
        """Return positive-scoring sessions paired with cosine similarity."""
        scored: list[tuple[float, SessionModel]] = []
        for db_session in db_sessions:
            similarity = await self._score_session(db_session, query_vec)
            if similarity > 0.0:
                scored.append((similarity, db_session))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    async def _score_sessions_with_highlights(
        self,
        db_sessions: list[SessionModel],
        query_vec: dict[str, float],
    ) -> tuple[list[tuple[float, SessionModel]], dict[str, list[SearchHighlight]]]:
        """Return positive-scoring sessions with highlights for matched terms.

        Returns:
            Tuple of (scored sessions list, highlights dict mapping session_id to highlights)
        """
        scored: list[tuple[float, SessionModel]] = []
        highlights: dict[str, list[SearchHighlight]] = {}

        for db_session in db_sessions:
            similarity, session_highlights = await self._score_session_with_highlights(
                db_session, query_vec
            )
            if similarity > 0.0:
                scored.append((similarity, db_session))
                if session_highlights:
                    highlights[db_session.id] = session_highlights

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored, highlights

    async def _score_session(self, db_session: SessionModel, query_vec: dict[str, float]) -> float:
        """Compute semantic similarity between a query vector and a stored session.

        Loads events lazily to avoid the O(n*m) cost of eager loading.
        """
        from sqlalchemy import select as sa_select

        stmt = sa_select(EventModel).where(
            EventModel.session_id == db_session.id,
            EventModel.tenant_id == self.tenant_id,
        )
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())
        event_dicts = [self._embedding_event_dict(db_event) for db_event in events]
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
        highlights: dict[str, list[SearchHighlight]] | None = None,
        limit: int = 20,
    ) -> list[Session]:
        """Convert scored ORM sessions into API models with attached similarity and highlights."""
        results: list[Session] = []
        for similarity, db_session in scored_sessions[:limit]:
            session = orm_to_session(db_session)
            session.search_similarity = similarity
            session.search_highlights = (
                [h.to_dict() for h in highlights.get(db_session.id, [])] if highlights else []
            )
            results.append(session)
        return results

    async def _score_session_with_highlights(
        self,
        db_session: SessionModel,
        query_vec: dict[str, float],
    ) -> tuple[float, list[SearchHighlight]]:
        """Compute semantic similarity and extract highlights for a session.

        Returns:
            Tuple of (similarity score, list of SearchHighlight objects)
        """
        from sqlalchemy import select as sa_select

        stmt = sa_select(EventModel).where(
            EventModel.session_id == db_session.id,
            EventModel.tenant_id == self.tenant_id,
        )
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())

        if not events:
            return 0.0, []

        event_dicts = [self._embedding_event_dict(db_event) for db_event in events]
        session_vec = build_session_embedding(event_dicts)
        similarity = cosine_similarity(query_vec, session_vec)

        # Extract highlights from matching events
        highlights = self._extract_highlights(events, query_vec, similarity)

        return similarity, highlights

    def _extract_highlights(
        self,
        events: list[EventModel],
        query_vec: dict[str, float],
        session_similarity: float,
    ) -> list[SearchHighlight]:
        """Extract highlight snippets from events that matched the query.

        Returns top 5 highlights per session based on term relevance.
        """
        query_terms = set(query_vec.keys())
        highlights: list[tuple[float, SearchHighlight]] = []

        for event in events:
            # Check each searchable field for query term matches
            searchable_fields = {
                "event_type": event.event_type,
                "name": event.name,
                "error_type": (event.data or {}).get("error_type") if event.data else None,
                "error_message": (event.data or {}).get("error_message") if event.data else None,
                "tool_name": (event.data or {}).get("tool_name") if event.data else None,
                "model": (event.data or {}).get("model") if event.data else None,
            }

            for field_name, field_value in searchable_fields.items():
                if not field_value:
                    continue

                field_text = str(field_value).lower()
                # Count matching query terms in this field
                matched_terms = [t for t in query_terms if t in field_text]
                if matched_terms:
                    # Calculate relevance based on term weights and match count
                    term_relevance = sum(query_vec.get(t, 0) for t in matched_terms)
                    relevance = term_relevance * session_similarity

                    highlight = SearchHighlight(
                        event_id=event.id,
                        event_type=event.event_type,
                        field_name=field_name,
                        matched_text=str(field_value)[:200],  # Truncate long values
                        relevance=relevance,
                    )
                    highlights.append((relevance, highlight))

        # Sort by relevance and return top 5
        highlights.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in highlights[:5]]
