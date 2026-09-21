"""Persistence and SSE event-streaming services."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import fields, replace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from api import app_context
from api.services.sessions import analyze_session, should_refresh_replay_value
from collector.buffer import EventBuffer, get_event_buffer
from collector.intelligence.facade import TraceIntelligence
from redaction.pipeline import RedactionPipeline, apply_payload_redaction
from storage import TraceRepository

logger = logging.getLogger(__name__)

DEFAULT_SSE_TIMEOUT = int(os.getenv("AGENT_DEBUGGER_SSE_TIMEOUT", "300"))


def _resolve_pipeline(redaction_pipeline: RedactionPipeline | None) -> RedactionPipeline:
    """Return the injected pipeline or the single configured one."""
    return redaction_pipeline if redaction_pipeline is not None else app_context._get_redaction_pipeline()


def _copy_redacted_state(event: TraceEvent, redacted: TraceEvent) -> None:
    """Overwrite ``event``'s fields in place with the redacted copy's values.

    The SDK emitter hands the SAME event object to the persister and to
    ``buffer.publish`` (scheduled via ``asyncio.gather``, persister first).
    Copying the redacted state back — before the persister's first await —
    means the concurrent buffer publish streams exactly what the database
    stores: one policy, one representation, no divergent copies.
    """
    for field_info in fields(event):
        setattr(event, field_info.name, getattr(redacted, field_info.name))

async def persist_session_start(
    session: Session,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    redaction_pipeline: RedactionPipeline | None = None,
) -> None:
    pipeline = _resolve_pipeline(redaction_pipeline)
    # Persist a scrubbed copy of the config; the caller's live Session keeps
    # its original config (documented in-process exception).
    to_create = replace(session, config=apply_payload_redaction(pipeline, session.config))
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            existing = await repo.get_session(session.id)
            if existing is None:
                await repo.create_session(to_create)
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
    redaction_pipeline: RedactionPipeline | None = None,
) -> None:
    pipeline = _resolve_pipeline(redaction_pipeline)
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
                # Scrubbed copy: the persisted config carries no more than
                # the policy permits, while the live Session is untouched.
                config=apply_payload_redaction(pipeline, session.config),
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
    pipeline = _resolve_pipeline(redaction_pipeline)
    # Apply the single configured policy and copy the redacted state back
    # onto the caller's event so the concurrent buffer publish (and the
    # NDJSON spill fed from the buffer) sees the redacted representation.
    # Values already captured by the SDK's in-memory event store are the
    # documented exception — every persisted or streamed copy is redacted.
    _copy_redacted_state(event, pipeline.apply(event))
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
    redaction_pipeline: RedactionPipeline | None = None,
) -> None:
    pipeline = _resolve_pipeline(redaction_pipeline)
    # Persist a scrubbed copy; the caller's Checkpoint object is untouched.
    to_store = replace(
        checkpoint,
        state=apply_payload_redaction(pipeline, checkpoint.state),
        memory=apply_payload_redaction(pipeline, checkpoint.memory),
    )
    sm = session_maker or app_context.require_session_maker()
    async with sm() as db_session:
        try:
            repo = TraceRepository(db_session)
            # Same consistency rule as the collector ingest boundary
            # (collector/server.py ingest_checkpoint): within the tenant, a
            # non-empty event reference must resolve to an event of the
            # checkpoint's own session. An empty event_id carries no
            # reference and stays accepted. Inconsistent checkpoints are
            # rejected before any write, so nothing persists.
            if checkpoint.event_id:
                anchor = await repo.get_event(checkpoint.event_id)
                if anchor is None or anchor.session_id != checkpoint.session_id:
                    raise ValueError(
                        f"Checkpoint event {checkpoint.event_id} does not belong to "
                        f"session {checkpoint.session_id}"
                    )
            await repo.create_checkpoint(to_store)
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise


async def event_generator(
    session_id: str,
    *,
    buffer: EventBuffer | None = None,
    max_connection_time: int | None = None,
    last_event_id: str | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
):
    """Generate SSE events for a session.

    Every event block carries an ``id:`` line with the event's id, so
    reconnecting EventSource clients send it back as ``Last-Event-ID``.
    When a cursor is supplied, the persisted events after it are replayed
    first (the database is the durable history; the buffer is
    best-effort), deduplicated against the live stream — a reconnect
    therefore closes the gap instead of silently skipping everything
    published while disconnected. An unknown cursor replays the whole
    session, which is gap-free by construction. Subscribing before the
    replay query means events published in between arrive live and are
    deduplicated by id.

    Args:
        session_id: Session ID to stream events for
        buffer: Optional event buffer (uses default if None)
        max_connection_time: Maximum connection time in seconds (default from
            AGENT_DEBUGGER_SSE_TIMEOUT env var, 300 if not set)
        last_event_id: Optional ``Last-Event-ID`` cursor for reconnect replay
        session_maker: Optional session maker override (tests)
    """
    if max_connection_time is None:
        max_connection_time = DEFAULT_SSE_TIMEOUT
    import time

    buf = buffer or get_event_buffer()
    queue = await buf.subscribe(session_id)
    start_time = time.time()

    def _sse(event) -> str:
        event_data = json.dumps(event.to_dict())
        return f"id: {event.id}\ndata: {event_data}\n\n"

    try:
        delivered: set[str] = set()
        if last_event_id is not None:
            sm = session_maker or app_context.require_session_maker()
            async with sm() as db_session:
                repo = TraceRepository(db_session)
                history = await repo.get_event_tree(session_id)
            history.sort(key=lambda item: (item.timestamp, item.id))
            replay = []
            for item in history:
                if item.id == last_event_id:
                    # Known cursor: everything before it (and it) is already
                    # delivered; replay only what follows.
                    replay = []
                    continue
                replay.append(item)
            for item in replay:
                delivered.add(item.id)
                yield _sse(item)

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
                if event.id in delivered:
                    continue
                delivered.add(event.id)
                yield _sse(event)
            # Python 3.11+ aliases asyncio.TimeoutError with the builtin
            # TimeoutError; on 3.10 they are distinct classes, so catch both
            # or a quiet period kills the stream mid-response.
            except (TimeoutError, asyncio.TimeoutError):
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        await buf.unsubscribe(session_id, queue)
