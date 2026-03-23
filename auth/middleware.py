"""FastAPI auth dependencies."""
from __future__ import annotations

from fastapi import HTTPException
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api_keys import verify_key
from auth.models import APIKeyModel


async def _resolve_tenant_from_key(raw_key: str, db: AsyncSession) -> str:
    """Look up tenant_id for a raw API key. Raises 401 if not found.

    Args:
        raw_key: The raw API key from the Authorization header
        db: Database session for lookup

    Returns:
        The tenant_id for the valid API key

    Raises:
        HTTPException: If the API key is invalid or not found
    """
    # Extract prefix for indexed lookup, then verify full key with bcrypt
    prefix = raw_key[:12] if len(raw_key) > 12 else raw_key
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.key_prefix.startswith(prefix[:8]),
            APIKeyModel.is_active == True,
        )
    )
    candidates = result.scalars().all()
    for candidate in candidates:
        if verify_key(raw_key, candidate.key_hash):
            return candidate.tenant_id
    raise HTTPException(status_code=401, detail="Invalid API key")


async def get_tenant_from_api_key(
    request: Request,
    db: AsyncSession,  # Caller (api/main.py) passes this via Depends chain
) -> str:
    """Extract and validate API key from Authorization header.

    Returns tenant_id. No auth header → 'local' mode.
    This is a helper called from get_tenant_id(), not a direct FastAPI dependency.

    Args:
        request: The FastAPI request object
        db: Database session for API key lookup

    Returns:
        The tenant_id, or 'local' if no auth header present

    Raises:
        HTTPException: If the auth header is malformed or the key is invalid
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return "local"

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    raw_key = auth_header.removeprefix("Bearer ").strip()
    return await _resolve_tenant_from_key(raw_key, db)
