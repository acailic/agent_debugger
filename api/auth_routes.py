"""API key management endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.api_keys import generate_api_key, hash_key
from auth.models import APIKeyModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CreateKeyRequest(BaseModel):
    name: str = ""
    environment: str = "live"  # live or test


class CreateKeyResponse(BaseModel):
    id: str
    key: str  # Only returned once at creation
    key_prefix: str
    name: str
    environment: str


class KeyListItem(BaseModel):
    id: str
    key_prefix: str
    name: str
    environment: str
    created_at: str
    last_used_at: str | None


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    request: CreateKeyRequest,
    db: AsyncSession = Depends(),
    tenant_id: str = Depends(),
):
    """Create a new API key for the current tenant."""
    raw_key = generate_api_key(environment=request.environment)
    key_model = APIKeyModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        key_hash=hash_key(raw_key),
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
    db: AsyncSession = Depends(),
    tenant_id: str = Depends(),
):
    """List all active API keys for the current tenant."""
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.tenant_id == tenant_id,
            APIKeyModel.is_active == True,
        )
    )
    keys = result.scalars().all()
    return [
        KeyListItem(
            id=k.id, key_prefix=k.key_prefix, name=k.name,
            environment=k.environment, created_at=str(k.created_at),
            last_used_at=str(k.last_used_at) if k.last_used_at else None,
        )
        for k in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    db: AsyncSession = Depends(),
    tenant_id: str = Depends(),
):
    """Revoke (deactivate) an API key."""
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
