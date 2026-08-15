"""Cross-session failure similarity services."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import String, cast, or_, select

from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from api.exceptions import NotFoundError
from storage import TraceRepository
from storage.converters import orm_to_event, orm_to_session
from storage.models import EventModel, SessionModel

logger = logging.getLogger(__name__)

FAILURE_SIMILARITY_THRESHOLD = 0.5

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
    return bool(
        event.event_type == EventType.ERROR
        or event.event_type == EventType.REFUSAL
        or event.event_type == EventType.POLICY_VIOLATION
        or event.event_type == EventType.BEHAVIOR_ALERT
        or (event.event_type == EventType.TOOL_RESULT and bool(getattr(event, "error", None)))
        or (
            event.event_type == EventType.SAFETY_CHECK
            and (outcome := getattr(event, "outcome", None))
            and outcome != "pass"
        )
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
        source_tool = getattr(source_event, "tool_name", None)
        candidate_tool = getattr(candidate_event, "tool_name", None)
        if source_tool and candidate_tool:
            if source_tool == candidate_tool:
                score += 0.2

    return min(score, 1.0)


def _derive_failure_mode(event: TraceEvent) -> str:
    """Derive a human-readable failure mode from an event."""
    if event.event_type == EventType.BEHAVIOR_ALERT:
        alert_type = getattr(event, "alert_type", None) or ""
        if alert_type == "tool_loop":
            return "looping_behavior"
        return "behavior_anomaly"
    if event.event_type in {EventType.REFUSAL, EventType.SAFETY_CHECK}:
        return "guardrail_block"
    if event.event_type == EventType.POLICY_VIOLATION:
        return "policy_mismatch"
    if event.event_type == EventType.TOOL_RESULT and getattr(event, "error", None):
        return "tool_execution_failure"
    if event.event_type == EventType.ERROR:
        return "runtime_error"
    return "unknown_failure"


def _derive_root_cause(event: TraceEvent) -> str:
    """Derive a root cause summary from an event."""
    if event.event_type == EventType.TOOL_RESULT and getattr(event, "error", None):
        tool_name = getattr(event, "tool_name", None) or "tool"
        return f"Tool {tool_name} failed: {_truncate_text(getattr(event, 'error', None) or '', 80)}"
    if event.event_type == EventType.ERROR:
        error_type = getattr(event, "error_type", None) or "Error"
        error_msg = getattr(event, "error_message", None) or getattr(event, "error", None) or "Unknown error"
        return f"{error_type}: {_truncate_text(error_msg, 80)}"
    if event.event_type == EventType.REFUSAL:
        reason = getattr(event, "reason", None) or "No reason provided"
        return f"Request refused: {_truncate_text(reason, 80)}"
    if event.event_type == EventType.POLICY_VIOLATION:
        vtype = getattr(event, "violation_type", None) or event.name or "Unknown violation"
        return f"Policy violation: {_truncate_text(vtype, 80)}"
    if event.event_type == EventType.BEHAVIOR_ALERT:
        signal = getattr(event, "signal", None) or event.name or "Behavior anomaly"
        return f"Behavior alert: {_truncate_text(signal, 80)}"
    if event.event_type == EventType.SAFETY_CHECK:
        policy = getattr(event, "policy_name", None) or "policy"
        outcome = getattr(event, "outcome", None) or "failed"
        return f"Safety check {policy} returned {outcome}"
    return "Unknown cause"


def _truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


# ------------------------------------------------------------------
# Causal Analysis
# ------------------------------------------------------------------

