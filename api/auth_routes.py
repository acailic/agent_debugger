"""API key management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_tenant_id
from api.schemas import CreateKeyRequest, CreateKeyResponse, KeyListItem
from auth.api_keys import generate_api_key as _default_generate_api_key
from auth.api_keys import hash_key as _default_hash_key
from auth.models import APIKeyModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
generate_api_key = _default_generate_api_key
hash_key = _default_hash_key


def _auth_key_helpers():
    from api import main as api_main

    generate = (
        generate_api_key
        if generate_api_key is not _default_generate_api_key
        else getattr(api_main, "generate_api_key", generate_api_key)
    )
    hash_fn = (
        hash_key
        if hash_key is not _default_hash_key
        else getattr(api_main, "hash_key", hash_key)
    )
    return generate, hash_fn


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    request: CreateKeyRequest,
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new API key for the current tenant."""
    generate, hash_fn = _auth_key_helpers()
    raw_key = generate(environment=request.environment)
    key_model = APIKeyModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        key_hash=hash_fn(raw_key),
        key_prefix=raw_key[:12] + "...",
        environment=request.environment,
        name=request.name,
    )
    db.add(key_model)
    await db.commit()
    return CreateKeyResponse(
        id=key_model.id,
        key=raw_key,
        key_prefix=key_model.key_prefix,
        name=key_model.name,
        environment=key_model.environment,
    )


@router.get("/keys", response_model=list[KeyListItem])
async def list_keys(
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """List all active API keys for the current tenant."""
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.tenant_id == tenant_id,
            APIKeyModel.is_active.is_(True),
        )
    )
    keys = result.scalars().all()
    return [
        KeyListItem(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            environment=key.environment,
            created_at=str(key.created_at),
            last_used_at=str(key.last_used_at) if key.last_used_at else None,
        )
        for key in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Revoke an API key for the current tenant."""
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.id == key_id,
            APIKeyModel.tenant_id == tenant_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.is_active = False
    await db.commit()
