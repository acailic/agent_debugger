"""Alert policy API routes for configurable alert thresholds."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_tenant_id
from api.exceptions import NotFoundError
from api.schemas import AlertPolicyCreate, AlertPolicyListResponse, AlertPolicySchema, AlertPolicyUpdate
from storage import AlertPolicyRepository

router = APIRouter(tags=["alert-policies"])


async def get_policy_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
) -> AlertPolicyRepository:
    """Get an alert policy repository scoped to the current tenant."""
    return AlertPolicyRepository(session, tenant_id=tenant_id)


@router.get("/api/alert-policies", response_model=AlertPolicyListResponse)
async def list_policies(
    agent_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    repo: AlertPolicyRepository = Depends(get_policy_repository),
) -> AlertPolicyListResponse:
    """List all alert policies, optionally filtered by agent_name.

    Args:
        agent_name: Optional agent name filter. If provided, returns both
                    agent-specific and global policies for this agent.
        limit: Maximum number of policies to return
        repo: AlertPolicyRepository instance

    Returns:
        List of alert policies
    """
    policies = await repo.list_policies(agent_name=agent_name, limit=limit)

    return AlertPolicyListResponse(
        policies=[
            AlertPolicySchema(
                id=policy.id,
                agent_name=policy.agent_name,
                alert_type=policy.alert_type,
                threshold_value=policy.threshold_value,
                severity_threshold=policy.severity_threshold,
                enabled=policy.enabled,
                created_at=policy.created_at,
                updated_at=policy.updated_at,
            )
            for policy in policies
        ],
        total=len(policies),
    )


@router.post("/api/alert-policies", response_model=AlertPolicySchema)
async def create_policy(
    data: AlertPolicyCreate,
    repo: AlertPolicyRepository = Depends(get_policy_repository),
) -> AlertPolicySchema:
    """Create a new alert policy.

    Args:
        data: Policy creation data
        repo: AlertPolicyRepository instance

    Returns:
        Created alert policy
    """
    policy = await repo.create_policy(
        agent_name=data.agent_name,
        alert_type=data.alert_type,
        threshold_value=data.threshold_value,
        severity_threshold=data.severity_threshold,
        enabled=data.enabled,
    )
    # Commit to persist the policy
    await repo.session.commit()
    await repo.session.refresh(policy)

    return AlertPolicySchema(
        id=policy.id,
        agent_name=policy.agent_name,
        alert_type=policy.alert_type,
        threshold_value=policy.threshold_value,
        severity_threshold=policy.severity_threshold,
        enabled=policy.enabled,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.get("/api/alert-policies/{policy_id}", response_model=AlertPolicySchema)
async def get_policy(
    policy_id: str,
    repo: AlertPolicyRepository = Depends(get_policy_repository),
) -> AlertPolicySchema:
    """Get a single alert policy by ID.

    Args:
        policy_id: Unique identifier of the policy
        repo: AlertPolicyRepository instance

    Returns:
        Alert policy details

    Raises:
        NotFoundError: if policy not found
    """
    policy = await repo.get_policy(policy_id)
    if not policy:
        raise NotFoundError(f"Policy {policy_id} not found")

    return AlertPolicySchema(
        id=policy.id,
        agent_name=policy.agent_name,
        alert_type=policy.alert_type,
        threshold_value=policy.threshold_value,
        severity_threshold=policy.severity_threshold,
        enabled=policy.enabled,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.put("/api/alert-policies/{policy_id}", response_model=AlertPolicySchema)
async def update_policy(
    policy_id: str,
    data: AlertPolicyUpdate,
    repo: AlertPolicyRepository = Depends(get_policy_repository),
) -> AlertPolicySchema:
    """Update an existing alert policy.

    Args:
        policy_id: Unique identifier of the policy to update
        data: Policy update data
        repo: AlertPolicyRepository instance

    Returns:
        Updated alert policy

    Raises:
        NotFoundError: if policy not found
    """
    policy = await repo.update_policy(
        policy_id=policy_id,
        agent_name=data.agent_name,
        alert_type=data.alert_type,
        threshold_value=data.threshold_value,
        severity_threshold=data.severity_threshold,
        enabled=data.enabled,
    )

    if not policy:
        raise NotFoundError(f"Policy {policy_id} not found")

    # Commit to persist changes
    await repo.session.commit()
    await repo.session.refresh(policy)

    return AlertPolicySchema(
        id=policy.id,
        agent_name=policy.agent_name,
        alert_type=policy.alert_type,
        threshold_value=policy.threshold_value,
        severity_threshold=policy.severity_threshold,
        enabled=policy.enabled,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.delete("/api/alert-policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    repo: AlertPolicyRepository = Depends(get_policy_repository),
) -> dict[str, Any]:
    """Delete an alert policy by ID.

    Args:
        policy_id: Unique identifier of the policy to delete
        repo: AlertPolicyRepository instance

    Returns:
        Deletion confirmation

    Raises:
        NotFoundError: if policy not found
    """
    deleted = await repo.delete_policy(policy_id)

    if not deleted:
        raise NotFoundError(f"Policy {policy_id} not found")

    # Commit to persist deletion
    await repo.session.commit()

    return {"deleted": True, "policy_id": policy_id}
