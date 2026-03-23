"""Shared FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.config import get_config
from auth.middleware import get_tenant_from_api_key
from storage import TraceRepository


async def get_db_session() -> AsyncSession:
    """Yield an async database session from the configured session factory."""
    from api import main as api_main

    async with api_main.async_session_maker() as session:
        yield session


async def get_tenant_id(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> str:
    """Resolve the current tenant from config mode and request auth."""
    config = get_config()
    if config.mode == "local":
        return "local"
    return await get_tenant_from_api_key(request, db)


def get_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
) -> TraceRepository:
    """Construct a repository scoped to the current tenant."""
    return TraceRepository(session, tenant_id=tenant_id)
