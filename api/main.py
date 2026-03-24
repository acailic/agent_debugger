"""FastAPI application factory and shared runtime state."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.context import configure_event_pipeline
from api import services as _services
from api.auth_routes import router as auth_router
from api.replay_routes import router as replay_router
from api.session_routes import router as session_router
from api.system_routes import router as system_router
from api.trace_routes import router as trace_router
from collector.intelligence import TraceIntelligence
from collector.server import configure_storage
from collector.server import router as collector_router
from redaction.pipeline import RedactionPipeline
from storage import Base
from storage.engine import create_db_engine, create_session_maker

engine = create_db_engine()
async_session_maker = create_session_maker(engine)
trace_intelligence = TraceIntelligence()


def _get_redaction_pipeline() -> RedactionPipeline:
    """Build the default redaction pipeline from runtime config."""
    return RedactionPipeline.from_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    from collector import create_buffer
    from storage.engine import get_database_url

    if "sqlite" in get_database_url():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    buffer_backend = "redis" if os.environ.get("REDIS_URL") else "memory"
    buffer = create_buffer(backend=buffer_backend)

    configure_storage(async_session_maker)
    configure_event_pipeline(
        buffer,
        persist_event=_services.persist_event,
        persist_checkpoint=_services.persist_checkpoint,
        persist_session_start=_services.persist_session_start,
        persist_session_update=_services.persist_session_update,
    )

    yield


DIST_PATH = Path(__file__).parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    _ = get_config()

    app = FastAPI(
        lifespan=lifespan,
        title="Agent Debugger API",
        description="API for debugging and visualizing AI agent executions",
        version="1.0.0",
    )

    cors_origins_str = os.environ.get("AGENT_DEBUGGER_CORS_ORIGINS", "*")
    cors_origins = (
        [origin for origin in (item.strip() for item in cors_origins_str.split(",")) if origin]
        if cors_origins_str != "*"
        else ["*"]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(collector_router)
    app.include_router(auth_router)
    app.include_router(session_router)
    app.include_router(trace_router)
    app.include_router(replay_router)
    app.include_router(system_router)

    if DIST_PATH.exists():
        app.mount("/ui", StaticFiles(directory=str(DIST_PATH), html=True), name="ui")

    @app.get("/", response_model=None)
    async def root() -> dict | FileResponse:
        if DIST_PATH.exists():
            return FileResponse(str(DIST_PATH / "index.html"))
        return {"message": "Agent Debugger API", "docs": "/docs"}

    return app


app = create_app()
