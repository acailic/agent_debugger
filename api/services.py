"""Shared API helper functions used by multiple route modules."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, SessionStatus, TraceEvent
from api import app_context
from api.exceptions import NotFoundError
from api.schemas import CheckpointSchema, SessionSchema, TraceEventSchema
from collector.buffer import EventBuffer, get_event_buffer
from collector.intelligence.facade import TraceIntelligence
from redaction.pipeline import RedactionPipeline
from storage import TraceRepository
from storage.converters import orm_to_event, orm_to_session
from storage.models import EventModel, SessionModel

logger = logging.getLogger(__name__)
SESSION_ANALYSIS_CAP = 100
FAILURE_SIMILARITY_THRESHOLD = 0.5


def normalize_session(
    session: Session,
    analysis_summary: dict[str, Any] | None = None,
) -> SessionSchema:
    normalized = session.to_dict()
    if analysis_summary:
        normalized.update(analysis_summary)
    return SessionSchema.model_validate(normalized)


def normalize_event(event: TraceEvent) -> TraceEventSchema:
    return TraceEventSchema.model_validate(event.to_dict())


def normalize_checkpoint(checkpoint: Checkpoint) -> CheckpointSchema:
    return CheckpointSchema.model_validate(checkpoint.to_dict())


def should_refresh_replay_value(session: Session) -> bool:
    return session.ended_at is not None or session.status != SessionStatus.RUNNING


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
        raise NotFoundError(f"Session {session_id} not found")
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
    intelligence: TraceIntelligence | None = None,
) -> tuple[list[TraceEvent], list[Checkpoint], dict[str, Any], float]:
    """Analyze a session's events and checkpoints.

    Returns:
        Tuple of (events, checkpoints, analysis, replay_value)
    """
    events, checkpoints = await load_session_artifacts(repo, session_id)
    session = await repo.get_session(session_id)

    # Build session dict for time-decay analysis
    session_dict = None
    if session:
        session_dict = {
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }

    intel = intelligence or app_context.require_trace_intelligence()
    analysis = intel.analyze_session(events, checkpoints, session=session_dict)
    replay_value = analysis.get("session_replay_value", 0.0)

    if persist_replay_value:
        await repo.update_session(session_id, replay_value=replay_value)

    return events, checkpoints, analysis, replay_value


async def build_live_summary(
    repo: TraceRepository,
    session_id: str,
    *,
    intelligence: TraceIntelligence | None = None,
) -> dict[str, Any]:
    events, checkpoints = await load_session_artifacts(repo, session_id)
    intel = intelligence or app_context.require_trace_intelligence()
    return intel.build_live_summary(events, checkpoints)


def compute_dict_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute the delta between two dictionaries.

    Returns a dictionary containing:
    - Keys with changed values
    - New keys added in current
    - Keys removed from previous (with None as value)
    """
    if not previous:
        return current or {}

    if not current:
        return {k: None for k in (previous or {})}

    all_keys = set(previous.keys()) | set(current.keys())
    delta: dict[str, Any] = {}

    for key in all_keys:
        prev_value = previous.get(key)
        curr_value = current.get(key)

        if key not in previous:
            # New key in current
            delta[key] = curr_value
        elif key not in current:
            # Key was removed
            delta[key] = None
        elif prev_value != curr_value:
            # Value changed
            delta[key] = curr_value

    return delta


def compute_checkpoint_deltas(
    checkpoints: list[Checkpoint],
) -> list[dict[str, Any]]:
    """Compute state and memory deltas between consecutive checkpoints.

    Args:
        checkpoints: List of checkpoints ordered by sequence/timestamp

    Returns:
        List of delta dictionaries with checkpoint_id, previous_checkpoint_id,
        state_delta, and memory_delta
    """
    if not checkpoints:
        return []

    deltas = []
    # Sort checkpoints by sequence to ensure correct ordering
    sorted_checkpoints = sorted(checkpoints, key=lambda cp: cp.sequence)

    for i, checkpoint in enumerate(sorted_checkpoints):
        if i == 0:
            # First checkpoint has no previous
            deltas.append(
                {
                    "checkpoint_id": checkpoint.id,
                    "previous_checkpoint_id": None,
                    "state_delta": checkpoint.state or {},
                    "memory_delta": checkpoint.memory or {},
                }
            )
        else:
            prev_checkpoint = sorted_checkpoints[i - 1]
            state_delta = compute_dict_delta(prev_checkpoint.state, checkpoint.state)
            memory_delta = compute_dict_delta(prev_checkpoint.memory, checkpoint.memory)

            deltas.append(
                {
                    "checkpoint_id": checkpoint.id,
                    "previous_checkpoint_id": prev_checkpoint.id,
                    "state_delta": state_delta,
                    "memory_delta": memory_delta,
                }
            )

    return deltas


async def enrich_sessions_for_listing(
    repo: TraceRepository,
    sessions: list[Session],
    *,
    sort_by: str,
) -> list[SessionSchema]:
    if sort_by != "replay_value":
        return [normalize_session(session) for session in sessions]

    capped_sessions = sessions[:SESSION_ANALYSIS_CAP]
    if len(sessions) > SESSION_ANALYSIS_CAP:
        logger.warning(
            "Replay-value enrichment capped at %s sessions for one response page",
            SESSION_ANALYSIS_CAP,
        )

    # Parallelize session analysis for better performance
    # Note: We still analyze sessions to get enrichment data like representative_event_id,
    # but the replay_value itself may be cached from a previous analysis
    analyses = await asyncio.gather(*[analyze_session(repo, session.id) for session in capped_sessions])

    enriched: list[dict[str, Any]] = [
        normalize_session(session, analysis_summary(analysis))
        for session, (_, _, analysis, _) in zip(capped_sessions, analyses)
    ]

    for session in sessions[SESSION_ANALYSIS_CAP:]:
        enriched.append(normalize_session(session))

    return enriched


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
    max_connection_time: int = 300,
):
    """Generate SSE events for a session.

    Args:
        session_id: Session ID to stream events for
        buffer: Optional event buffer (uses default if None)
        max_connection_time: Maximum connection time in seconds (default 300)
    """
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


async def find_similar_failures(
    repo: TraceRepository,
    session_id: str,
    failure_event_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find sessions with similar failures based on failure type and error patterns.

    Args:
        repo: Trace repository
        session_id: Current session ID
        failure_event_id: The failure event to find similar failures for
        limit: Maximum number of similar failures to return

    Returns:
        List of similar failure dicts with session_id, agent_name, framework,
        started_at, failure_type, failure_mode, root_cause, similarity, fix_note
    """
    # Get the failure event
    failure_event = await repo.get_event(failure_event_id)
    if not failure_event:
        raise NotFoundError(f"Failure event {failure_event_id} not found")
    if failure_event.session_id != session_id:
        raise NotFoundError(
            f"Failure event {failure_event_id} was not found in session {session_id}"
        )

    # Determine failure characteristics
    error_text = _event_error_text(failure_event)
    error_type = _event_error_type(failure_event)
    candidate_failures = await _load_candidate_failure_events(repo, failure_event, session_id)

    best_match_by_session: dict[str, dict[str, Any]] = {}

    for event, session in candidate_failures:
        similarity = _calculate_failure_similarity(
            failure_event,
            event,
            error_text,
            error_type,
        )
        if similarity < FAILURE_SIMILARITY_THRESHOLD:
            continue

        failure_summary = {
            "session_id": session.id,
            "agent_name": session.agent_name,
            "framework": session.framework,
            "started_at": session.started_at,
            "failure_type": str(event.event_type),
            "failure_mode": _derive_failure_mode(event),
            "root_cause": _derive_root_cause(event),
            "similarity": similarity,
            "fix_note": session.fix_note,
        }
        existing = best_match_by_session.get(session.id)
        if existing is None or failure_summary["similarity"] > existing["similarity"]:
            best_match_by_session[session.id] = failure_summary

    # Sort by similarity and limit
    similar_failures = list(best_match_by_session.values())
    similar_failures.sort(key=lambda x: x["similarity"], reverse=True)
    return similar_failures[:limit]


async def _load_candidate_failure_events(
    repo: TraceRepository,
    failure_event: TraceEvent,
    session_id: str,
) -> list[tuple[TraceEvent, Session]]:
    """Load tenant-scoped failure candidates without per-session N+1 queries."""
    failure_event_types = [
        str(EventType.ERROR),
        str(EventType.REFUSAL),
        str(EventType.POLICY_VIOLATION),
        str(EventType.BEHAVIOR_ALERT),
        str(EventType.TOOL_RESULT),
        str(EventType.SAFETY_CHECK),
    ]

    source_clues = [EventModel.event_type == str(failure_event.event_type)]
    source_error_type = _event_error_type(failure_event)
    if source_error_type:
        source_clues.append(cast(EventModel.data, String).ilike(f"%{source_error_type}%"))
    source_tool_name = getattr(failure_event, "tool_name", None)
    if source_tool_name:
        source_clues.append(cast(EventModel.data, String).ilike(f"%{source_tool_name}%"))

    stmt = (
        select(EventModel, SessionModel)
        .join(SessionModel, EventModel.session_id == SessionModel.id)
        .where(
            SessionModel.tenant_id == repo.tenant_id,
            EventModel.tenant_id == repo.tenant_id,
            SessionModel.id != session_id,
            SessionModel.errors > 0,
            EventModel.event_type.in_(failure_event_types),
            or_(*source_clues),
        )
        .order_by(SessionModel.started_at.desc(), EventModel.timestamp.desc())
    )
    result = await repo.session.execute(stmt)

    candidates: list[tuple[TraceEvent, Session]] = []
    for db_event, db_session in result.all():
        event = orm_to_event(db_event)
        if not _is_failure_event(event):
            continue
        candidates.append((event, orm_to_session(db_session)))
    return candidates


def _is_failure_event(event: TraceEvent) -> bool:
    """Check if an event represents a failure."""
    return (
        event.event_type == EventType.ERROR
        or event.event_type == EventType.REFUSAL
        or event.event_type == EventType.POLICY_VIOLATION
        or event.event_type == EventType.BEHAVIOR_ALERT
        or (event.event_type == EventType.TOOL_RESULT and bool(event.error))
        or (event.event_type == EventType.SAFETY_CHECK and event.outcome and event.outcome != "pass")
    )


def _event_error_text(event: TraceEvent) -> str:
    """Return the most useful error-like text available on an event."""
    return (
        getattr(event, "error", None)
        or getattr(event, "error_message", None)
        or getattr(event, "reason", None)
        or event.name
        or ""
    )


def _event_error_type(event: TraceEvent) -> str:
    """Return the most useful error-like type available on an event."""
    return (
        getattr(event, "error_type", None)
        or getattr(event, "violation_type", None)
        or getattr(event, "alert_type", None)
        or ""
    )



def _calculate_failure_similarity(
    source_event: TraceEvent,
    candidate_event: TraceEvent,
    source_error_text: str,
    source_error_type: str,
) -> float:
    """Calculate similarity score between two failure events.

    Returns a float between 0.0 and 1.0.
    """
    score = 0.0

    # Event type match (high weight)
    if source_event.event_type == candidate_event.event_type:
        score += 0.4

    # Error type match
    candidate_error_type = _event_error_type(candidate_event)
    if source_error_type and candidate_error_type:
        if source_error_type.lower() == candidate_error_type.lower():
            score += 0.3

    # Error text similarity (simple keyword overlap)
    candidate_error_text = _event_error_text(candidate_event)
    if source_error_text and candidate_error_text:
        source_words = set(source_error_text.lower().split())
        candidate_words = set(candidate_error_text.lower().split())

        if source_words and candidate_words:
            overlap = len(source_words & candidate_words)
            total = len(source_words | candidate_words)
            if total > 0:
                score += 0.3 * (overlap / total)

    # Tool name match for tool_result failures
    if source_event.event_type == EventType.TOOL_RESULT and candidate_event.event_type == EventType.TOOL_RESULT:
        if source_event.tool_name and candidate_event.tool_name:
            if source_event.tool_name == candidate_event.tool_name:
                score += 0.2

    return min(score, 1.0)


def _derive_failure_mode(event: TraceEvent) -> str:
    """Derive a human-readable failure mode from an event."""
    if event.event_type == EventType.BEHAVIOR_ALERT:
        alert_type = event.alert_type or ""
        if alert_type == "tool_loop":
            return "looping_behavior"
        return "behavior_anomaly"
    if event.event_type in {EventType.REFUSAL, EventType.SAFETY_CHECK}:
        return "guardrail_block"
    if event.event_type == EventType.POLICY_VIOLATION:
        return "policy_mismatch"
    if event.event_type == EventType.TOOL_RESULT and event.error:
        return "tool_execution_failure"
    if event.event_type == EventType.ERROR:
        return "runtime_error"
    return "unknown_failure"


def _derive_root_cause(event: TraceEvent) -> str:
    """Derive a root cause summary from an event."""
    if event.event_type == EventType.TOOL_RESULT and event.error:
        tool_name = event.tool_name or "tool"
        return f"Tool {tool_name} failed: {_truncate_text(event.error, 80)}"
    if event.event_type == EventType.ERROR:
        error_type = event.error_type or "Error"
        error_msg = event.error_message or event.error or "Unknown error"
        return f"{error_type}: {_truncate_text(error_msg, 80)}"
    if event.event_type == EventType.REFUSAL:
        reason = event.reason or "No reason provided"
        return f"Request refused: {_truncate_text(reason, 80)}"
    if event.event_type == EventType.POLICY_VIOLATION:
        vtype = event.violation_type or event.name or "Unknown violation"
        return f"Policy violation: {_truncate_text(vtype, 80)}"
    if event.event_type == EventType.BEHAVIOR_ALERT:
        signal = event.signal or event.name or "Behavior anomaly"
        return f"Behavior alert: {_truncate_text(signal, 80)}"
    if event.event_type == EventType.SAFETY_CHECK:
        policy = event.policy_name or "policy"
        outcome = event.outcome or "failed"
        return f"Safety check {policy} returned {outcome}"
    return "Unknown cause"


def _truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
