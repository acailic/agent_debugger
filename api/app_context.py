"""Shared application runtime state for the API layer."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collector.intelligence.facade import TraceIntelligence
from redaction.pipeline import RedactionPipeline
from storage.engine import create_db_engine, create_session_maker

engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None
trace_intelligence: TraceIntelligence | None = None
_redaction_pipeline: RedactionPipeline | None = None


def init_app_context() -> None:
    """Initialize shared runtime state for the FastAPI app."""
    global engine, async_session_maker, trace_intelligence, _redaction_pipeline

    if engine is None:
        engine = create_db_engine()
    if async_session_maker is None:
        async_session_maker = create_session_maker(engine)
    if trace_intelligence is None:
        trace_intelligence = TraceIntelligence()

    _redaction_pipeline = RedactionPipeline.from_config()


def _ensure_initialized() -> None:
    """Initialize app context lazily when first accessed."""
    if engine is None or async_session_maker is None or trace_intelligence is None or _redaction_pipeline is None:
        init_app_context()


def require_engine() -> AsyncEngine:
    """Return the initialized database engine."""
    _ensure_initialized()
    assert engine is not None
    return engine


def require_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the initialized async session maker."""
    _ensure_initialized()
    assert async_session_maker is not None
    return async_session_maker


def require_trace_intelligence() -> TraceIntelligence:
    """Return the initialized trace intelligence service."""
    _ensure_initialized()
    assert trace_intelligence is not None
    return trace_intelligence


def _get_redaction_pipeline() -> RedactionPipeline:
    """Return the configured redaction pipeline."""
    _ensure_initialized()
    assert _redaction_pipeline is not None
    return _redaction_pipeline
