"""Checkpoint repository for checkpoint CRUD operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent_debugger_sdk.core.events import Checkpoint
from storage.converters import orm_to_checkpoint
from storage.models import CheckpointModel, SessionModel


class CheckpointRepository:
    """Data access layer for checkpoint CRUD operations.

    Provides async methods for checkpoint management using SQLAlchemy async session.
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
        return orm_to_checkpoint(db_checkpoint)

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
        return orm_to_checkpoint(db_checkpoint)

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
        return [orm_to_checkpoint(db) for db in result.scalars()]

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
        return [orm_to_checkpoint(db) for db in result.scalars()]
