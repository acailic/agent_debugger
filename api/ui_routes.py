"""UI serving routes — root redirect and static file fallback."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

DIST_PATH = Path(__file__).parent.parent / "frontend" / "dist"


@router.get("/", response_model=None)
async def root() -> dict | FileResponse:
    """Serve bundled UI or API info."""
    if DIST_PATH.exists():
        return FileResponse(str(DIST_PATH / "index.html"))
    return {"message": "Agent Debugger API", "docs": "/docs"}
