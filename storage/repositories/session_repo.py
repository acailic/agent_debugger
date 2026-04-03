"""Session repository for session CRUD operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.core.events import Session
from storage.converters import orm_to_session
from storage.models import SessionModel


class SessionRepository:
    """Data access layer for session CRUD operations.

    Provides async methods for session management using SQLAlchemy async session.
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
            fix_note=session.fix_note,
        )
        self.session.add(db_session)
        return orm_to_session(db_session)

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
        return orm_to_session(db_session)

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        sort_by: str = "started_at",
        agent_name: str | None = None,
    ) -> list[Session]:
        """List sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of Session instances
        """
        stmt = select(SessionModel).where(SessionModel.tenant_id == self.tenant_id)
        if agent_name is not None:
            stmt = stmt.where(SessionModel.agent_name == agent_name)
        if sort_by == "replay_value":
            stmt = stmt.order_by(SessionModel.replay_value.desc(), SessionModel.started_at.desc())
        else:
            stmt = stmt.order_by(SessionModel.started_at.desc())

        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [orm_to_session(db) for db in result.scalars()]

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
            "started_at",
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
        return orm_to_session(db_session)

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
