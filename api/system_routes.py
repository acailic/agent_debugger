"""System-level API routes."""

from __future__ import annotations

import os

from fastapi import APIRouter
from sqlalchemy import text

from agent_debugger_sdk.config import get_config
from api import app_context

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Health check endpoint with dependency connectivity verification."""
    config = get_config()
    checks = {"status": "ok", "mode": config.mode}

    try:
        async with app_context.require_session_maker()() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            from redis.asyncio import Redis

            r = Redis.from_url(redis_url)
            await r.ping()
            checks["redis"] = "connected"
            await r.aclose()
        except Exception as e:
            checks["redis"] = f"error: {e}"
            checks["status"] = "degraded"

    return checks
