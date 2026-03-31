"""Auth service layer for API key operations.

This module provides service functions that encapsulate business logic
for API key management, keeping routes thin and delegating database
operations properly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api_keys import generate_api_key, hash_key
from auth.models import APIKeyModel


async def create_api_key(
    db: AsyncSession,
    tenant_id: str,
    name: str,
    environment: str,
) -> APIKeyModel:
    """Create a new API key for a tenant.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        name: Display name for the key
        environment: Either "live" or "test"

    Returns:
        The created APIKeyModel instance (not yet committed)
    """
    raw_key = generate_api_key(environment=environment)
    key_model = APIKeyModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        key_hash=hash_key(raw_key),
        key_prefix=raw_key[:12] + "...",
        environment=environment,
        name=name,
    )
    db.add(key_model)
    return key_model, raw_key


async def list_active_keys(
    db: AsyncSession,
    tenant_id: str,
) -> list[APIKeyModel]:
    """List all active API keys for a tenant.

    Args:
        db: Database session
        tenant_id: Tenant identifier

    Returns:
        List of active APIKeyModel instances
    """
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.tenant_id == tenant_id,
            APIKeyModel.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def revoke_key(
    db: AsyncSession,
    key_id: str,
    tenant_id: str,
) -> APIKeyModel | None:
    """Revoke an API key for a tenant.

    Args:
        db: Database session
        key_id: ID of the key to revoke
        tenant_id: Tenant identifier

    Returns:
        The revoked APIKeyModel, or None if not found
    """
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.id == key_id,
            APIKeyModel.tenant_id == tenant_id,
        )
    )
    key = result.scalar_one_or_none()
    if key:
        key.is_active = False
    return key
