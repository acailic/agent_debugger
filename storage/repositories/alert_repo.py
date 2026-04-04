"""Anomaly alert repository for alert CRUD operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from storage.cache import QueryCache
from storage.models import AnomalyAlertModel


class AnomalyAlertRepository:
    """Data access layer for anomaly alert CRUD operations.

    Provides async methods for alert management using SQLAlchemy async session.
    All queries are scoped to a specific tenant_id for multi-tenant isolation.

    Queries leverage the following indexes:
    - ix_anomaly_alerts_created_at: time-based ordering and filtering
    - ix_anomaly_alerts_severity: severity-based filtering
    - ix_anomaly_alerts_alert_type: alert type filtering
    - ix_anomaly_alerts_session_id: session-based lookups
    - ix_anomaly_alerts_tenant_id_status: tenant + status filtering
    """

    VALID_STATUSES = {"active", "acknowledged", "resolved", "dismissed"}

    # Class-level cache shared across instances (for summary/trending data)
    _cache = QueryCache()

    def __init__(self, session: AsyncSession, tenant_id: str = "local"):
        """Initialize the repository with an async session and tenant_id.

        Args:
            session: SQLAlchemy AsyncSession instance
            tenant_id: Tenant identifier for data isolation (default: "local")
        """
        self.session = session
        self.tenant_id = tenant_id

    async def create_anomaly_alert(
        self, alert: AnomalyAlertModel, created_at: object | None = None
    ) -> AnomalyAlertModel:
        """Create a new anomaly alert record.

        Args:
            alert: AnomalyAlertModel instance to persist
            created_at: Optional creation timestamp (for AnomalyAlertCreate compatibility)

        Returns:
            The created AnomalyAlertModel instance
        """
        self.session.add(alert)
        # Invalidate summary cache when new alert is created
        self._invalidate_summary_cache()
        return alert

    async def list_anomaly_alerts(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[AnomalyAlertModel]:
        """List anomaly alerts for a session.

        Uses ix_anomaly_alerts_session_id and ix_anomaly_alerts_created_at indexes.

        Args:
            session_id: Session ID to filter alerts by
            limit: Maximum number of alerts to return (default: 50)

        Returns:
            List of AnomalyAlertModel instances ordered by creation time (newest first)
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

    async def get_alert_summary(self, hours: int = 24) -> dict[str, Any]:
        """Get aggregated alert statistics for the recent time window.

        Uses ix_anomaly_alerts_created_at index for time filtering and
        ix_anomaly_alerts_severity, ix_anomaly_alerts_alert_type for grouping.

        Results are cached for 60 seconds to reduce database load.

        Args:
            hours: Number of hours to look back (default: 24)

        Returns:
            Dictionary with total_count, by_severity, by_type, and by_session
        """
        cache_key = f"alert_summary:{self.tenant_id}:{hours}h"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Count by severity - uses ix_anomaly_alerts_severity
        severity_result = await self.session.execute(
            select(AnomalyAlertModel.severity, func.count(AnomalyAlertModel.id))
            .where(
                AnomalyAlertModel.tenant_id == self.tenant_id,
                AnomalyAlertModel.created_at >= cutoff,
            )
            .group_by(AnomalyAlertModel.severity)
        )
        by_severity = {row[0]: row[1] for row in severity_result.all()}

        # Count by alert type - uses ix_anomaly_alerts_alert_type
        type_result = await self.session.execute(
            select(AnomalyAlertModel.alert_type, func.count(AnomalyAlertModel.id))
            .where(
                AnomalyAlertModel.tenant_id == self.tenant_id,
                AnomalyAlertModel.created_at >= cutoff,
            )
            .group_by(AnomalyAlertModel.alert_type)
        )
        by_type = {row[0]: row[1] for row in type_result.all()}

        # Count by session - uses ix_anomaly_alerts_session_id
        session_result = await self.session.execute(
            select(AnomalyAlertModel.session_id, func.count(AnomalyAlertModel.id))
            .where(
                AnomalyAlertModel.tenant_id == self.tenant_id,
                AnomalyAlertModel.created_at >= cutoff,
            )
            .group_by(AnomalyAlertModel.session_id)
            .order_by(func.count(AnomalyAlertModel.id).desc())
            .limit(10)
        )
        by_session = {row[0]: row[1] for row in session_result.all()}

        summary = {
            "total_count": sum(by_severity.values()),
            "by_severity": by_severity,
            "by_type": by_type,
            "by_session": by_session,
            "period_hours": hours,
        }

        # Cache for 60 seconds
        self._cache.set(cache_key, summary, ttl_seconds=60)
        return summary

    async def get_trending_alerts(
        self,
        hours: int = 24,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get trending alerts by type for the recent time window.

        Uses ix_anomaly_alerts_alert_type and ix_anomaly_alerts_created_at indexes.

        Results are cached for 60 seconds to reduce database load.

        Args:
            hours: Number of hours to look back (default: 24)
            limit: Maximum number of trending types to return (default: 10)

        Returns:
            List of dicts with alert_type, count, and avg_severity
        """
        cache_key = f"trending_alerts:{self.tenant_id}:{hours}h"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.session.execute(
            select(
                AnomalyAlertModel.alert_type,
                func.count(AnomalyAlertModel.id).label("count"),
                func.avg(AnomalyAlertModel.severity).label("avg_severity"),
            )
            .where(
                AnomalyAlertModel.tenant_id == self.tenant_id,
                AnomalyAlertModel.created_at >= cutoff,
            )
            .group_by(AnomalyAlertModel.alert_type)
            .order_by(func.count(AnomalyAlertModel.id).desc())
            .limit(limit)
        )

        trending = [
            {
                "alert_type": row.alert_type,
                "count": row.count,
                "avg_severity": float(row.avg_severity) if row.avg_severity else 0.0,
            }
            for row in result.all()
        ]

        # Cache for 60 seconds
        self._cache.set(cache_key, trending, ttl_seconds=60)
        return trending

    def _invalidate_summary_cache(self) -> None:
        """Invalidate summary and trending cache entries for this tenant."""
        # Invalidate all cache entries for this tenant
        self._cache.invalidate(f"alert_summary:{self.tenant_id}:")
        self._cache.invalidate(f"trending_alerts:{self.tenant_id}:")

    # ------------------------------------------------------------------
    # Lifecycle Management Methods
    # ------------------------------------------------------------------

    async def update_alert_status(
        self, alert_id: str, status: str, note: str | None = None
    ) -> AnomalyAlertModel | None:
        """Update the status of a single alert with appropriate timestamp.

        Uses primary key lookup for efficient single-alert update.

        Args:
            alert_id: Unique identifier of the alert
            status: New status (active/acknowledged/resolved/dismissed)
            note: Optional resolution note

        Returns:
            Updated AnomalyAlertModel if found, None otherwise

        Raises:
            ValueError: If status is not valid
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}")

        result = await self.session.execute(
            select(AnomalyAlertModel).where(
                AnomalyAlertModel.id == alert_id,
                AnomalyAlertModel.tenant_id == self.tenant_id,
            )
        )
        alert = result.scalar_one_or_none()

        if not alert:
            return None

        # Update status and note
        alert.status = status
        if note:
            alert.resolution_note = note

        # Update appropriate timestamp
        now = datetime.now(timezone.utc)
        if status == "acknowledged":
            alert.acknowledged_at = now
        elif status == "resolved":
            alert.resolved_at = now
        elif status == "dismissed":
            alert.dismissed_at = now

        # Invalidate cache when alert status changes
        self._invalidate_summary_cache()

        return alert

    async def bulk_update_status(self, alert_ids: list[str], status: str) -> int:
        """Bulk update status for multiple alerts.

        Uses efficient bulk update with WHERE ... IN clause.

        Args:
            alert_ids: List of alert IDs to update
            status: New status for all alerts

        Returns:
            Number of alerts updated

        Raises:
            ValueError: If status is not valid
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}")

        now = datetime.now(timezone.utc)
        updates = {"status": status}

        # Set appropriate timestamp based on status
        if status == "acknowledged":
            updates["acknowledged_at"] = now
        elif status == "resolved":
            updates["resolved_at"] = now
        elif status == "dismissed":
            updates["dismissed_at"] = now

        stmt = (
            update(AnomalyAlertModel)
            .where(
                AnomalyAlertModel.id.in_(alert_ids),
                AnomalyAlertModel.tenant_id == self.tenant_id,
            )
            .values(**updates)
        )
        result = await self.session.execute(stmt)

        # Invalidate cache when bulk status changes occur
        self._invalidate_summary_cache()

        return result.rowcount

    async def list_alerts_filtered(
        self,
        agent_name: str | None = None,
        severity: float | None = None,
        alert_type: str | None = None,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
    ) -> list[AnomalyAlertModel]:
        """List alerts with rich filtering options.

        Leverages ix_anomaly_alerts_tenant_id_status, ix_anomaly_alerts_severity,
        ix_anomaly_alerts_alert_type, and ix_anomaly_alerts_created_at indexes.

        Args:
            agent_name: Optional agent name to filter by (requires join)
            severity: Optional minimum severity to filter by
            alert_type: Optional alert type to filter by
            status: Optional status to filter by
            from_date: Optional start date for created_at filter
            to_date: Optional end date for created_at filter
            limit: Maximum number of alerts to return

        Returns:
            List of AnomalyAlertModel instances matching filters
        """
        query = select(AnomalyAlertModel).where(AnomalyAlertModel.tenant_id == self.tenant_id)

        # Apply filters
        if alert_type:
            query = query.where(AnomalyAlertModel.alert_type == alert_type)
        if severity is not None:
            query = query.where(AnomalyAlertModel.severity >= severity)
        if status:
            query = query.where(AnomalyAlertModel.status == status)
        if from_date:
            query = query.where(AnomalyAlertModel.created_at >= from_date)
        if to_date:
            query = query.where(AnomalyAlertModel.created_at <= to_date)

        # Join with sessions if agent_name filter is provided
        if agent_name:
            from storage.models import SessionModel

            query = query.join(SessionModel, AnomalyAlertModel.session_id == SessionModel.id).where(
                SessionModel.agent_name == agent_name
            )

        query = query.order_by(AnomalyAlertModel.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_alert_lifecycle_summary(self) -> dict[str, Any]:
        """Get alert summary statistics grouped by severity, type, and status.

        Uses ix_anomaly_alerts_severity, ix_anomaly_alerts_alert_type, and
        ix_anomaly_alerts_tenant_id_status indexes for efficient grouping.

        Results are cached for 60 seconds.

        Returns:
            Dictionary with counts by severity, type, and status
        """
        cache_key = f"lifecycle_summary:{self.tenant_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Count by status
        status_result = await self.session.execute(
            select(AnomalyAlertModel.status, func.count(AnomalyAlertModel.id))
            .where(AnomalyAlertModel.tenant_id == self.tenant_id)
            .group_by(AnomalyAlertModel.status)
        )
        by_status = {status: count for status, count in status_result.all()}

        # Count by alert_type
        type_result = await self.session.execute(
            select(AnomalyAlertModel.alert_type, func.count(AnomalyAlertModel.id))
            .where(AnomalyAlertModel.tenant_id == self.tenant_id)
            .group_by(AnomalyAlertModel.alert_type)
        )
        by_type = {alert_type: count for alert_type, count in type_result.all()}

        # Count by severity ranges
        critical_result = await self.session.execute(
            select(func.count(AnomalyAlertModel.id)).where(
                and_(
                    AnomalyAlertModel.tenant_id == self.tenant_id,
                    AnomalyAlertModel.severity >= 0.8,
                )
            )
        )
        critical_count = critical_result.scalar() or 0

        high_result = await self.session.execute(
            select(func.count(AnomalyAlertModel.id)).where(
                and_(
                    AnomalyAlertModel.tenant_id == self.tenant_id,
                    AnomalyAlertModel.severity >= 0.5,
                    AnomalyAlertModel.severity < 0.8,
                )
            )
        )
        high_count = high_result.scalar() or 0

        medium_result = await self.session.execute(
            select(func.count(AnomalyAlertModel.id)).where(
                and_(
                    AnomalyAlertModel.tenant_id == self.tenant_id,
                    AnomalyAlertModel.severity >= 0.3,
                    AnomalyAlertModel.severity < 0.5,
                )
            )
        )
        medium_count = medium_result.scalar() or 0

        low_result = await self.session.execute(
            select(func.count(AnomalyAlertModel.id)).where(
                and_(
                    AnomalyAlertModel.tenant_id == self.tenant_id,
                    AnomalyAlertModel.severity < 0.3,
                )
            )
        )
        low_count = low_result.scalar() or 0

        summary = {
            "by_status": by_status,
            "by_type": by_type,
            "by_severity": {
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
            },
            "total": sum(by_status.values()),
        }

        # Cache for 60 seconds
        self._cache.set(cache_key, summary, ttl_seconds=60)
        return summary

    async def get_alert_trending(self, days: int = 7) -> list[dict[str, Any]]:
        """Get alert volume trend grouped by day.

        Uses ix_anomaly_alerts_created_at index for efficient time-based grouping.

        Results are cached for 60 seconds.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            List of dicts with date and count
        """
        cache_key = f"trending:{self.tenant_id}:{days}d"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)

        result = await self.session.execute(
            select(
                func.date(AnomalyAlertModel.created_at).label("date"),
                func.count(AnomalyAlertModel.id).label("count"),
            )
            .where(
                and_(
                    AnomalyAlertModel.tenant_id == self.tenant_id,
                    AnomalyAlertModel.created_at >= from_date,
                )
            )
            .group_by(func.date(AnomalyAlertModel.created_at))
            .order_by(func.date(AnomalyAlertModel.created_at))
        )

        trending = [{"date": str(row.date), "count": row.count} for row in result.all()]

        # Cache for 60 seconds
        self._cache.set(cache_key, trending, ttl_seconds=60)
        return trending
