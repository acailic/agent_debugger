"""API key management endpoints."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_tenant_id
from api.exceptions import NotFoundError, RateLimitError
from api.schemas import CreateKeyRequest, CreateKeyResponse, KeyListItem
from auth.service import create_api_key, list_active_keys, revoke_key

router = APIRouter(prefix="/api/auth", tags=["auth"])

# --- Simple in-memory rate limiter for key creation ---
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_KEYS = 10
_key_creation_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(tenant_id: str) -> None:
    """Raise RateLimitError if tenant exceeded key creation rate limit."""
    now = time.monotonic()
    window = now - _RATE_WINDOW_SECONDS
    _key_creation_attempts[tenant_id] = [t for t in _key_creation_attempts[tenant_id] if t > window]
    if len(_key_creation_attempts[tenant_id]) >= _RATE_MAX_KEYS:
        raise RateLimitError(
            f"Rate limit exceeded: max {_RATE_MAX_KEYS} key creations per {_RATE_WINDOW_SECONDS}s",
            retry_after=_RATE_WINDOW_SECONDS,
        )


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    request: CreateKeyRequest,
    db: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new API key for the current tenant."""
    _check_rate_limit(tenant_id)
    _key_creation_attempts[tenant_id].append(time.monotonic())
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
        raise NotFoundError("Key not found")
    await db.commit()
