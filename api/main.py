"""FastAPI application factory and shared API runtime exports."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.core.context import configure_event_pipeline
from api.auth_routes import router as auth_router
from api.dependencies import get_db_session, get_repository, get_tenant_id
from api.replay_routes import router as replay_router
from api.schemas import (
    AnalysisResponse,
    CheckpointListResponse,
    CreateKeyRequest,
    CreateKeyResponse,
    DecisionTreeResponse,
    DeleteResponse,
    KeyListItem,
    LiveSummaryResponse,
    ReplayResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionUpdateRequest,
    TraceBundleResponse,
    TraceListResponse,
    TraceSearchResponse,
)
from api.services import (
    event_generator as _event_generator,
)
from api.services import (
    normalize_checkpoint as _normalize_checkpoint,
)
from api.services import (
    normalize_event as _normalize_event,
)
from api.services import (
    normalize_session as _normalize_session,
)
from api.services import (
    persist_checkpoint as _persist_checkpoint,
)
from api.services import (
    persist_event as _persist_event,
)
from api.services import (
    persist_session_start as _persist_session_start,
)
from api.services import (
    persist_session_update as _persist_session_update,
)
from api.session_routes import router as session_router
from api.system_routes import router as system_router
from api.trace_routes import router as trace_router
from auth.api_keys import generate_api_key, hash_key
from auth.middleware import get_tenant_from_api_key
from collector.intelligence import TraceIntelligence
from collector.replay import build_replay, build_tree
from collector.server import configure_storage
from collector.server import router as collector_router
from redaction.pipeline import RedactionPipeline
from storage import Base
from storage.engine import create_db_engine, create_session_maker

engine = create_db_engine()
async_session_maker = create_session_maker(engine)
trace_intelligence = TraceIntelligence()

__all__ = [
    "AnalysisResponse",
    "CheckpointListResponse",
    "CreateKeyRequest",
    "CreateKeyResponse",
    "DecisionTreeResponse",
    "DeleteResponse",
    "KeyListItem",
    "LiveSummaryResponse",
    "ReplayResponse",
    "SessionDetailResponse",
    "SessionListResponse",
    "SessionUpdateRequest",
    "TraceBundleResponse",
    "TraceListResponse",
    "TraceSearchResponse",
    "_event_generator",
    "_get_redaction_pipeline",
    "_normalize_checkpoint",
    "_normalize_event",
    "_normalize_session",
    "_persist_checkpoint",
    "_persist_event",
    "_persist_session_start",
    "_persist_session_update",
    "app",
    "async_session_maker",
    "build_replay",
    "build_tree",
    "create_app",
    "engine",
    "generate_api_key",
    "get_config",
    "get_db_session",
    "get_repository",
    "get_tenant_from_api_key",
    "get_tenant_id",
    "hash_key",
    "lifespan",
    "trace_intelligence",
]


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
        persist_event=_persist_event,
        persist_checkpoint=_persist_checkpoint,
        persist_session_start=_persist_session_start,
        persist_session_update=_persist_session_update,
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
    app.include_router(system_router)

    return app


app = create_app()
