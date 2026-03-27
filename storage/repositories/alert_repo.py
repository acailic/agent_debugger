"""Anomaly alert repository for alert CRUD operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import AnomalyAlertModel


class AnomalyAlertRepository:
    """Data access layer for anomaly alert CRUD operations.

    Provides async methods for alert management using SQLAlchemy async session.
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
        return alert

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
