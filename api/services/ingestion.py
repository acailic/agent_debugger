"""Persistence and SSE event-streaming services."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from api import app_context
from api.services.sessions import analyze_session, should_refresh_replay_value
from collector.buffer import EventBuffer, get_event_buffer
from collector.intelligence.facade import TraceIntelligence
from redaction.pipeline import RedactionPipeline
from storage import TraceRepository

logger = logging.getLogger(__name__)

DEFAULT_SSE_TIMEOUT = int(os.getenv("AGENT_DEBUGGER_SSE_TIMEOUT", "300"))

async def persist_session_start(
    session: Session,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            existing = await repo.get_session(session.id)
            if existing is None:
                await repo.create_session(session)
                await repo.commit()
                # Record analytics event (fire-and-forget)
                from api.analytics_db import record_event

                record_event("session_created", session_id=session.id, agent_name=session.agent_name)
        except Exception:
            await db_session.rollback()
            raise


async def persist_session_update(
    session: Session,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    intelligence: TraceIntelligence | None = None,
) -> None:
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            replay_value = session.replay_value
            if should_refresh_replay_value(session):
                _, _, _, replay_value = await analyze_session(repo, session.id, intelligence=intelligence)
                session.replay_value = replay_value

            await repo.update_session(
                session.id,
                agent_name=session.agent_name,
                framework=session.framework,
                ended_at=session.ended_at,
                status=session.status,
                total_tokens=session.total_tokens,
                total_cost_usd=session.total_cost_usd,
                tool_calls=session.tool_calls,
                llm_calls=session.llm_calls,
                errors=session.errors,
                replay_value=replay_value,
                config=session.config,
                tags=session.tags,
            )
            await repo.commit()
        except Exception:
            await db_session.rollback()
            raise


async def persist_event(
    event: TraceEvent,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    redaction_pipeline: RedactionPipeline | None = None,
) -> None:
    pipeline = redaction_pipeline or app_context._get_redaction_pipeline()
    event = pipeline.apply(event)
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            await repo.add_event(event)
            await repo.commit()
        except Exception:
            await db_session.rollback()
            raise


async def persist_checkpoint(
    checkpoint: Checkpoint,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            await repo.create_checkpoint(checkpoint)
            await repo.commit()
        except Exception:
            await db_session.rollback()
            raise


async def event_generator(
    session_id: str,
    *,
    buffer: EventBuffer | None = None,
    max_connection_time: int | None = None,
):
    """Generate SSE events for a session.

    Args:
        session_id: Session ID to stream events for
        buffer: Optional event buffer (uses default if None)
        max_connection_time: Maximum connection time in seconds (default from
            AGENT_DEBUGGER_SSE_TIMEOUT env var, 300 if not set)
    """
    if max_connection_time is None:
        max_connection_time = DEFAULT_SSE_TIMEOUT
    import time

    buf = buffer or get_event_buffer()
    queue = await buf.subscribe(session_id)
    start_time = time.time()

    try:
        while True:
            # Check connection time limit
            elapsed = time.time() - start_time
            if elapsed >= max_connection_time:
                elapsed_int = int(elapsed)
                logger.info(
                    "SSE connection for session %s closed after %s seconds (max: %s)",
                    session_id,
                    elapsed_int,
                    max_connection_time,
                )
                close_data = {
                    "reason": "max_connection_time_exceeded",
                    "elapsed_seconds": elapsed_int,
                }
                yield f'event: close\ndata: {json.dumps(close_data)}\n\n'
                break

            # Calculate remaining time for queue timeout
            remaining = max_connection_time - elapsed
            timeout = min(15.0, remaining)

            try:
                event = await asyncio.wait_for(queue.get(), timeout=timeout)
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        await buf.unsubscribe(session_id, queue)
