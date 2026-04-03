"""Pattern repository for pattern CRUD operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import PatternModel


class PatternRepository:
    """Data access layer for pattern CRUD operations.

    Provides async methods for pattern management using SQLAlchemy async session.
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

    async def create_pattern(
        self,
        pattern_type: str,
        agent_name: str,
        severity: str,
        description: str,
        affected_sessions: list[str],
        metadata: dict[str, Any] | None = None,
        baseline_value: float | None = None,
        current_value: float | None = None,
        threshold: float | None = None,
        change_percent: float | None = None,
    ) -> PatternModel:
        """Create a new pattern record.

        Args:
            pattern_type: Type of pattern (error_trend, tool_failure, confidence_drop, new_failure_mode)
            agent_name: Name of the agent this pattern affects
            severity: Severity level (warning, critical)
            description: Human-readable description of the pattern
            affected_sessions: List of session IDs affected by this pattern
            metadata: Additional pattern-specific data
            baseline_value: Baseline metric value
            current_value: Current metric value
            threshold: Threshold that was exceeded
            change_percent: Percentage change from baseline

        Returns:
            The created PatternModel instance
        """
        import uuid

        db_pattern = PatternModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            pattern_type=pattern_type,
            agent_name=agent_name,
            severity=severity,
            status="active",
            detected_at=datetime.now(),
            description=description,
            affected_sessions=affected_sessions,
            session_count=len(affected_sessions),
            pattern_data=metadata or {},
            baseline_value=baseline_value,
            current_value=current_value,
            threshold=threshold,
            change_percent=change_percent,
        )
        self.session.add(db_pattern)
        return db_pattern

    async def get_pattern(self, pattern_id: str) -> PatternModel | None:
        """Retrieve a pattern by ID.

        Args:
            pattern_id: Unique identifier of the pattern

        Returns:
            PatternModel if found, None otherwise
        """
        result = await self.session.execute(
            select(PatternModel).where(
                PatternModel.id == pattern_id,
                PatternModel.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_patterns_by_agent(
        self,
        agent_name: str,
        *,
        pattern_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[PatternModel]:
        """Retrieve patterns for a specific agent.

        Args:
            agent_name: Name of the agent
            pattern_type: Optional filter by pattern type
            severity: Optional filter by severity
            status: Optional filter by status (active, resolved, dismissed)
            limit: Maximum number of patterns to return

        Returns:
            List of PatternModel instances
        """
        stmt = select(PatternModel).where(
            PatternModel.tenant_id == self.tenant_id,
            PatternModel.agent_name == agent_name,
        )

        if pattern_type:
            stmt = stmt.where(PatternModel.pattern_type == pattern_type)
        if severity:
            stmt = stmt.where(PatternModel.severity == severity)
        if status:
            stmt = stmt.where(PatternModel.status == status)

        stmt = stmt.order_by(PatternModel.detected_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_patterns(
        self,
        *,
        pattern_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        hours: int | None = None,
        limit: int = 50,
    ) -> list[PatternModel]:
        """Retrieve recent patterns across all agents.

        Args:
            pattern_type: Optional filter by pattern type
            severity: Optional filter by severity
            status: Optional filter by status (active, resolved, dismissed)
            hours: Only return patterns detected in the last N hours
            limit: Maximum number of patterns to return

        Returns:
            List of PatternModel instances
        """
        stmt = select(PatternModel).where(PatternModel.tenant_id == self.tenant_id)

        if pattern_type:
            stmt = stmt.where(PatternModel.pattern_type == pattern_type)
        if severity:
            stmt = stmt.where(PatternModel.severity == severity)
        if status:
            stmt = stmt.where(PatternModel.status == status)
        if hours:
            from datetime import timedelta

            cutoff = datetime.now() - timedelta(hours=hours)
            stmt = stmt.where(PatternModel.detected_at >= cutoff)

        stmt = stmt.order_by(PatternModel.detected_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_pattern_status(
        self,
        pattern_id: str,
        status: str,
        resolved_by: str | None = None,
    ) -> PatternModel | None:
        """Update the status of a pattern.

        Args:
            pattern_id: Unique identifier of the pattern
            status: New status (active, resolved, dismissed)
            resolved_by: Optional identifier of who resolved the pattern

        Returns:
            Updated PatternModel if found, None otherwise
        """
        result = await self.session.execute(
            select(PatternModel).where(
                PatternModel.id == pattern_id,
                PatternModel.tenant_id == self.tenant_id,
            )
        )
        db_pattern = result.scalar_one_or_none()
        if db_pattern is None:
            return None

        db_pattern.status = status
        if status == "resolved":
            db_pattern.resolved_at = datetime.now()
            db_pattern.resolved_by = resolved_by

        return db_pattern

    async def count_patterns_by_type(self) -> dict[str, int]:
        """Count patterns grouped by type.

        Returns:
            Dictionary mapping pattern_type to count
        """
        result = await self.session.execute(
            select(PatternModel.pattern_type, func.count(PatternModel.id))
            .where(PatternModel.tenant_id == self.tenant_id)
            .where(PatternModel.status == "active")
            .group_by(PatternModel.pattern_type)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_patterns_by_severity(self) -> dict[str, int]:
        """Count patterns grouped by severity.

        Returns:
            Dictionary mapping severity to count
        """
        result = await self.session.execute(
            select(PatternModel.severity, func.count(PatternModel.id))
            .where(PatternModel.tenant_id == self.tenant_id)
            .where(PatternModel.status == "active")
            .group_by(PatternModel.severity)
        )
        return {row[0]: row[1] for row in result.all()}

    async def delete_pattern(self, pattern_id: str) -> bool:
        """Delete a pattern by ID.

        Args:
            pattern_id: Unique identifier of the pattern

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(PatternModel).where(
                PatternModel.id == pattern_id,
                PatternModel.tenant_id == self.tenant_id,
            )
        )
        return result.rowcount > 0


    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        await self.session.rollback()
