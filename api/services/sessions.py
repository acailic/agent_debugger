"""Session access, normalization, listing, and analysis loading."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, Session, SessionStatus, TraceEvent
from api import app_context
from api.exceptions import NotFoundError
from api.schemas import CheckpointSchema, SessionSchema, TraceEventSchema
from collector.intelligence.facade import TraceIntelligence
from storage import TraceRepository

logger = logging.getLogger(__name__)

SESSION_ANALYSIS_CAP = 100

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
        return dict.fromkeys(previous or {})

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

    if len(sessions) > SESSION_ANALYSIS_CAP:
        logger.warning(
            "Replay-value enrichment capped at %s sessions for one response page (has %s sessions). "
            "Sessions beyond the cap will be returned without replay_value enrichment.",
            SESSION_ANALYSIS_CAP,
            len(sessions),
        )

    capped_sessions = sessions[:SESSION_ANALYSIS_CAP]

    # Parallelize session analysis for better performance
    # Note: We still analyze sessions to get enrichment data like representative_event_id,
    # but the replay_value itself may be cached from a previous analysis
    analyses = await asyncio.gather(*[analyze_session(repo, session.id) for session in capped_sessions])

    enriched: list[SessionSchema] = [
        normalize_session(session, analysis_summary(analysis))
        for session, (_, _, analysis, _) in zip(capped_sessions, analyses, strict=True)
    ]

    for session in sessions[SESSION_ANALYSIS_CAP:]:
        enriched.append(normalize_session(session))

    return enriched
