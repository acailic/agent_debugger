"""API key management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_tenant_id
from api.schemas import CreateKeyRequest, CreateKeyResponse, KeyListItem
from auth.service import create_api_key, list_active_keys, revoke_key

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    request: CreateKeyRequest,
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new API key for the current tenant."""
    key_model, raw_key = await create_api_key(
        db=db,
        tenant_id=tenant_id,
        name=request.name,
        environment=request.environment,
    )
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
    keys = await list_active_keys(db=db, tenant_id=tenant_id)
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
async def revoke_key_endpoint(
    key_id: str,
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Revoke an API key for the current tenant."""
    key = await revoke_key(db=db, key_id=key_id, tenant_id=tenant_id)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.commit()
