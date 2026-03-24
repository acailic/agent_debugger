"""FastAPI application factory."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.context import configure_event_pipeline
from api import app_context
from api import services as _services
from api.auth_routes import router as auth_router
from api.comparison_routes import router as comparison_router
from api.replay_routes import router as replay_router
from api.session_routes import router as session_router
from api.system_routes import router as system_router
from api.trace_routes import router as trace_router
from api.ui_routes import DIST_PATH
from api.ui_routes import router as ui_router
from collector.server import configure_storage
from collector.server import router as collector_router
from storage.engine import get_database_url, prepare_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    from collector import create_buffer

    app_context.init_app_context()

    if "sqlite" in get_database_url():
        await prepare_database(app_context.require_engine())

    buffer_backend = "redis" if os.environ.get("REDIS_URL") else "memory"
    buffer = create_buffer(backend=buffer_backend)

    configure_storage(app_context.require_session_maker())
    configure_event_pipeline(
        buffer,
        persist_event=_services.persist_event,
        persist_checkpoint=_services.persist_checkpoint,
        persist_session_start=_services.persist_session_start,
        persist_session_update=_services.persist_session_update,
    )

    yield


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
    app.include_router(comparison_router)
    app.include_router(system_router)
    app.include_router(ui_router)

    if DIST_PATH.exists():
        app.mount("/ui", StaticFiles(directory=str(DIST_PATH), html=True), name="ui")

    return app


def __getattr__(name: str):
    """Provide compatibility access to app runtime state."""
    if name in {"engine", "async_session_maker", "trace_intelligence"}:
        return getattr(app_context, name)
    if name == "_get_redaction_pipeline":
        return app_context._get_redaction_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


app = create_app()
