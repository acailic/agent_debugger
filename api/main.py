"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.context import configure_event_pipeline
from api import app_context
from api import services as _services
from api.analytics_db import init_analytics_db
from api.analytics_routes import router as analytics_router
from api.auth_routes import router as auth_router
from api.comparison_routes import router as comparison_router
from api.cost_routes import router as cost_router
from api.exceptions import AppError
from api.middleware import ContentTypeValidationMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.replay_routes import router as replay_router
from api.search_routes import router as search_router
from api.session_routes import router as session_router
from api.system_routes import router as system_router
from api.trace_routes import router as trace_router
from api.ui_routes import DIST_PATH
from api.ui_routes import router as ui_router
from collector.server import configure_storage
from collector.server import router as collector_router
from storage.engine import get_database_url, prepare_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    from collector import create_buffer

    app_context.init_app_context()

    if "sqlite" in get_database_url():
        await prepare_database(app_context.require_engine())

    # Initialize analytics database (local-only, fire-and-forget)
    init_analytics_db()

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

    # Register global exception handlers
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle custom application errors with consistent JSON responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unhandled exceptions with logging and generic error response."""
        logger.error(
            "Unhandled exception on %s %s: %s\n%s",
            request.method,
            request.url.path,
            str(exc),
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected error occurred. Please try again later.",
                "error": "internal_server_error",
            },
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

    # Add request tracking middleware
    app.add_middleware(ContentTypeValidationMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(collector_router)
    app.include_router(auth_router)
    app.include_router(analytics_router)
    app.include_router(session_router)
    app.include_router(trace_router)
    app.include_router(replay_router)
    app.include_router(comparison_router)
    app.include_router(cost_router)
    app.include_router(search_router)
    app.include_router(system_router)
    app.include_router(ui_router)

    if DIST_PATH.exists():
        app.mount("/ui", StaticFiles(directory=str(DIST_PATH), html=True), name="ui")

    return app


app = create_app()
