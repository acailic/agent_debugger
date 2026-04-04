"""Alert policy repository for policy CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import AlertPolicyModel


class AlertPolicyRepository:
    """Data access layer for alert policy CRUD operations.

    Provides async methods for policy management using SQLAlchemy async session.
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

    async def create_policy(
        self,
        agent_name: str | None,
        alert_type: str,
        threshold_value: float,
        severity_threshold: str | None = None,
        enabled: bool = True,
    ) -> AlertPolicyModel:
        """Create a new alert policy.

        Args:
            agent_name: Agent name for specific policy, None for global policy
            alert_type: Type of alert this policy applies to
            threshold_value: Threshold value for the alert
            severity_threshold: Optional severity threshold (warning, critical, etc.)
            enabled: Whether the policy is enabled

        Returns:
            The created AlertPolicyModel instance
        """
        policy = AlertPolicyModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            agent_name=agent_name,
            alert_type=alert_type,
            threshold_value=threshold_value,
            severity_threshold=severity_threshold,
            enabled=enabled,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(policy)
        return policy

    async def get_policy(self, policy_id: str) -> AlertPolicyModel | None:
        """Retrieve an alert policy by ID.

        Args:
            policy_id: Unique identifier of the policy

        Returns:
            AlertPolicyModel if found, None otherwise
        """
        result = await self.session.execute(
            select(AlertPolicyModel).where(
                AlertPolicyModel.id == policy_id,
                AlertPolicyModel.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_policies(
        self,
        agent_name: str | None = None,
        limit: int = 100,
    ) -> list[AlertPolicyModel]:
        """List alert policies, optionally filtered by agent_name.

        Args:
            agent_name: Optional agent name filter (None returns all policies including global)
            limit: Maximum number of policies to return

        Returns:
            List of AlertPolicyModel instances
        """
        query = select(AlertPolicyModel).where(AlertPolicyModel.tenant_id == self.tenant_id)

        if agent_name is not None:
            # Filter for specific agent OR global (NULL agent_name) policies
            query = query.where(
                (AlertPolicyModel.agent_name == agent_name) | (AlertPolicyModel.agent_name.is_(None))
            )

        query = query.order_by(AlertPolicyModel.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_policy(
        self,
        policy_id: str,
        agent_name: str | None = None,
        alert_type: str | None = None,
        threshold_value: float | None = None,
        severity_threshold: str | None = None,
        enabled: bool | None = None,
    ) -> AlertPolicyModel | None:
        """Update an existing alert policy.

        Args:
            policy_id: Unique identifier of the policy to update
            agent_name: New agent name (None keeps existing value)
            alert_type: New alert type (None keeps existing value)
            threshold_value: New threshold value (None keeps existing value)
            severity_threshold: New severity threshold (None keeps existing value)
            enabled: New enabled state (None keeps existing value)

        Returns:
            Updated AlertPolicyModel if found, None otherwise
        """
        policy = await self.get_policy(policy_id)
        if not policy:
            return None

        if agent_name is not None:
            policy.agent_name = agent_name
        if alert_type is not None:
            policy.alert_type = alert_type
        if threshold_value is not None:
            policy.threshold_value = threshold_value
        if severity_threshold is not None:
            policy.severity_threshold = severity_threshold
        if enabled is not None:
            policy.enabled = enabled

        policy.updated_at = datetime.now(timezone.utc)
        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete an alert policy by ID.

        Args:
            policy_id: Unique identifier of the policy to delete

        Returns:
            True if policy was deleted, False if not found
        """
        policy = await self.get_policy(policy_id)
        if not policy:
            return False

        await self.session.delete(policy)
        return True

    async def get_active_policy_for(
        self,
        alert_type: str,
        agent_name: str | None = None,
    ) -> AlertPolicyModel | None:
        """Get the active policy for a specific alert type and agent.

        Returns the most specific policy available:
        1. Agent-specific policy (if agent_name provided)
        2. Global policy for the alert type
        3. None if no policy found

        Args:
            alert_type: Type of alert to find policy for
            agent_name: Optional agent name for agent-specific policy

        Returns:
            AlertPolicyModel if found, None otherwise
        """
        # First try to find agent-specific policy
        if agent_name is not None:
            result = await self.session.execute(
                select(AlertPolicyModel)
                .where(
                    AlertPolicyModel.tenant_id == self.tenant_id,
                    AlertPolicyModel.alert_type == alert_type,
                    AlertPolicyModel.agent_name == agent_name,
                    AlertPolicyModel.enabled.is_(True),
                )
                .order_by(AlertPolicyModel.created_at.desc())
                .limit(1)
            )
            policy = result.scalar_one_or_none()
            if policy:
                return policy

        # Fall back to global policy
        result = await self.session.execute(
            select(AlertPolicyModel)
            .where(
                AlertPolicyModel.tenant_id == self.tenant_id,
                AlertPolicyModel.alert_type == alert_type,
                AlertPolicyModel.agent_name.is_(None),
                AlertPolicyModel.enabled.is_(True),
            )
            .order_by(AlertPolicyModel.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
