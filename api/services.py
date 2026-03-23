"""Shared API helper functions used by multiple route modules."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import HTTPException, status

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from collector.buffer import get_event_buffer
from storage import TraceRepository

logger = logging.getLogger(__name__)
SESSION_ANALYSIS_CAP = 100


def normalize_session(session: Session, analysis_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = session.to_dict()
    if analysis_summary:
        normalized.update(analysis_summary)
    return normalized


def normalize_event(event: TraceEvent) -> dict[str, Any]:
    return event.to_dict()


def normalize_checkpoint(checkpoint: Checkpoint) -> dict[str, Any]:
    return checkpoint.to_dict()


def should_refresh_replay_value(session: Session) -> bool:
    return session.ended_at is not None or session.status != "running"


def analysis_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    session_summary = analysis.get("session_summary", {})
    representative_failure_ids = analysis.get("representative_failure_ids", [])
    return {
        "replay_value": analysis.get("session_replay_value", 0.0),
        "retention_tier": analysis.get("retention_tier"),
        "failure_count": session_summary.get("failure_count", 0),
        "behavior_alert_count": session_summary.get("behavior_alert_count", 0),
        "representative_event_id": representative_failure_ids[0] if representative_failure_ids else None,
    }


async def require_session(repo: TraceRepository, session_id: str) -> Session:
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


async def load_session_artifacts(
    repo: TraceRepository,
    session_id: str,
) -> tuple[list[TraceEvent], list[Checkpoint]]:
    events = await repo.get_event_tree(session_id)
    checkpoints = await repo.list_checkpoints(session_id)
    return events, checkpoints


async def analyze_session(
    repo: TraceRepository,
    session_id: str,
    *,
    persist_replay_value: bool = False,
) -> tuple[list[TraceEvent], list[Checkpoint], dict[str, Any]]:
    from api import main as api_main

    events, checkpoints = await load_session_artifacts(repo, session_id)
    analysis = api_main.trace_intelligence.analyze_session(events, checkpoints)

    if persist_replay_value:
        await repo.update_session(session_id, replay_value=analysis.get("session_replay_value", 0.0))

    return events, checkpoints, analysis


async def build_live_summary(repo: TraceRepository, session_id: str) -> dict[str, Any]:
    from api import main as api_main

    events, checkpoints = await load_session_artifacts(repo, session_id)
    return api_main.trace_intelligence.build_live_summary(events, checkpoints)


async def enrich_sessions_for_listing(
    repo: TraceRepository,
    sessions: list[Session],
    *,
    sort_by: str,
) -> list[dict[str, Any]]:
    if sort_by != "replay_value":
        return [normalize_session(session) for session in sessions]

    capped_sessions = sessions[:SESSION_ANALYSIS_CAP]
    if len(sessions) > SESSION_ANALYSIS_CAP:
        logger.warning(
            "Replay-value enrichment capped at %s sessions for one response page",
            SESSION_ANALYSIS_CAP,
        )

    enriched: list[dict[str, Any]] = []
    for session in capped_sessions:
        _, _, analysis = await analyze_session(repo, session.id)
        enriched.append(normalize_session(session, analysis_summary(analysis)))

    for session in sessions[SESSION_ANALYSIS_CAP:]:
        enriched.append(normalize_session(session))

    return enriched


async def persist_session_start(session: Session) -> None:
    from api import main as api_main

    async with api_main.async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        existing = await repo.get_session(session.id)
        if existing is None:
            await repo.create_session(session)


async def persist_session_update(session: Session) -> None:
    from api import main as api_main

    async with api_main.async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        replay_value = session.replay_value
        if should_refresh_replay_value(session):
            _, _, analysis = await analyze_session(repo, session.id)
            replay_value = analysis.get("session_replay_value", 0.0)
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


async def persist_event(event: TraceEvent) -> None:
    from api import main as api_main

    pipeline = api_main._get_redaction_pipeline()
    event = pipeline.apply(event)
    async with api_main.async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        await repo.add_event(event)


async def persist_checkpoint(checkpoint: Checkpoint) -> None:
    from api import main as api_main

    async with api_main.async_session_maker() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_checkpoint(checkpoint)


async def event_generator(session_id: str):
    buffer = get_event_buffer()
    queue = await buffer.subscribe(session_id)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        await buffer.unsubscribe(session_id, queue)
