"""Agent audit / trust API routes.

Exposes a per-session audit report that answers the five operator questions
(what / why / evidence / outcome / where-failed) plus an explainable trust
score. The report is produced by :class:`collector.audit.SessionAuditEngine`,
reusing the session's existing failure explanations so it stays consistent
with the replay / causal analysis surfaced elsewhere.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.analytics_db import record_event
from api.dependencies import get_repository
from api.schemas_analysis import SessionAuditResponse
from api.services import analyze_session, require_session
from collector.audit import SessionAuditEngine
from storage import TraceRepository

router = APIRouter(tags=["audit"])

_audit_engine = SessionAuditEngine()


@router.get("/api/sessions/{session_id}/audit", response_model=SessionAuditResponse)
async def get_session_audit(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> SessionAuditResponse:
    """Return a human-auditable trust + failure report for a session.

    Combines the five-question audit view with deterministic claim
    verification statuses, risk signals, localized failures, and an
    explainable trust score. All numbers are derivable from captured
    event fields — no opaque model scoring.
    """
    session = await require_session(repo, session_id)
    try:
        events, checkpoints, analysis, _ = await analyze_session(repo, session_id)
        session_dict = {
            "id": session.id,
            "status": str(session.status) if session.status else None,
            "agent_name": session.agent_name,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
        report = _audit_engine.audit(
            events,
            checkpoints,
            session=session_dict,
            failure_explanations=analysis.get("failure_explanations", []),
        )
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    record_event("audit_report_viewed", session_id=session_id)
    return SessionAuditResponse(session_id=session_id, audit=report)
