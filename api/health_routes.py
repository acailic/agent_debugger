"""Health check and system status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for health checks."""

    status: str
    version: str
    timestamp: str
    database: str | None = None


class ReadinessResponse(BaseModel):
    """Response model for readiness checks."""

    ready: bool
    checks: dict[str, str]
    timestamp: str


@router.get("/health")
async def health_check():
    """Basic health check endpoint.

    Returns:
        JSON with status, mode, version, and timestamp
    """
    return {
        "status": "ok",
        "mode": "local",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(db_session: AsyncSession = Depends(get_db_session)):
    """Readiness check endpoint that verifies database connectivity.

    Returns:
        ReadinessResponse with status of all dependency checks
    """
    checks: dict[str, str] = {}

    # Check database connectivity
    try:
        await db_session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"failed: {str(e)}"

    all_healthy = all(status == "ok" for status in checks.values())

    return ReadinessResponse(
        ready=all_healthy,
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/live")
async def liveness_check():
    """Liveness check endpoint.

    Returns 200 if the service is alive and responding.
    """
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}
