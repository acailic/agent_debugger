"""Shared FastAPI dependency providers."""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent_debugger_sdk.config import get_config
from api import app_context
from auth.middleware import get_tenant_from_api_key
from storage import TraceRepository

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncSession:
    """Yield an async database session from the configured session factory."""
    async with app_context.require_session_maker()() as session:
        yield session


async def get_tenant_id(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> str:
    """Resolve the current tenant from config mode and request auth.

    In local mode, only requests from localhost are permitted for security.
    Non-localhost requests in local mode are rejected with 403 Forbidden.
    """
    config = get_config()
    if config.mode == "local":
        # Security check: local mode should only accept requests from localhost
        client_host = getattr(request, "client", None)
        if client_host:
            client_host = client_host.host
        if client_host and client_host not in ("127.0.0.1", "::1", "localhost"):
            logger.warning(
                "Rejected non-localhost request in local mode",
                extra={"client_host": client_host, "path": request.url.path},
            )
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail="Local mode only accepts requests from localhost",
            )
        return "local"
    return await get_tenant_from_api_key(request, db)


def get_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
) -> TraceRepository:
    """Construct a repository scoped to the current tenant."""
    return TraceRepository(session, tenant_id=tenant_id)


def get_entity_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Construct an entity repository scoped to the current tenant."""
    from storage.repositories.entity_repo import EntityRepository

    return EntityRepository(session, tenant_id=tenant_id)


async def require_hosted_auth(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Require a valid API key when the server runs in hosted (cloud) mode.

    A minimal mode-conditional gate for routes whose backing store is
    local-only (e.g. the analytics SQLite file) and therefore has no tenant
    dimension to scope by: in hosted mode the caller must present a valid
    Bearer key (401 on a missing/invalid key, via
    ``auth.middleware.get_tenant_from_api_key``), while local mode stays
    fully open — keyless, matching the pre-existing behavior. Data-plane
    routes should keep using ``get_tenant_id``/``get_repository``, which also
    enforce the local-mode loopback restriction.
    """
    if get_config().mode != "local":
        await get_tenant_from_api_key(request, db)
