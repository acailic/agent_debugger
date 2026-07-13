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
from api.exceptions import NotFoundError
from api.schemas_analysis import (
    DecisionJustificationResponse,
    EvidenceGraphResponse,
    SessionAuditResponse,
)
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


def _session_dict(session) -> dict:
    return {
        "id": session.id,
        "status": str(session.status) if session.status else None,
        "agent_name": session.agent_name,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


@router.get(
    "/api/sessions/{session_id}/decisions/{event_id}/justification",
    response_model=DecisionJustificationResponse,
)
async def get_decision_justification(
    session_id: str,
    event_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> DecisionJustificationResponse:
    """Return a per-decision justification (why / evidence / outcome / where-failed).

    This is the drill-down view for the audit's dominant interaction: one
    important decision node answered end-to-end. Verification status and
    failure localization are reused from :class:`SessionAuditEngine` so they
    match the session-level report exactly.
    """
    session = await require_session(repo, session_id)
    try:
        events, _checkpoints, analysis, _ = await analyze_session(repo, session_id)
        justification = _audit_engine.justify_decision(
            events,
            event_id,
            session=_session_dict(session),
            failure_explanations=analysis.get("failure_explanations", []),
        )
        if justification is None:
            raise NotFoundError(
                f"Decision {event_id} not found in session {session_id}"
            )
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    record_event("decision_justification_viewed", session_id=session_id)
    return DecisionJustificationResponse(
        session_id=session_id,
        event_id=event_id,
        justification=justification,
    )


@router.get(
    "/api/sessions/{session_id}/evidence-graph",
    response_model=EvidenceGraphResponse,
)
async def get_evidence_graph(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> EvidenceGraphResponse:
    """Return the evidence-provenance graph for a session.

    Nodes are claims (decisions) and facts (tool results, user input); edges
    are ``evidence`` (a decision cites a fact) or ``causal`` (parent /
    upstream). Claim nodes reuse :class:`SessionAuditEngine`'s verification
    status, so the graph is a navigable view of how every claim connects to
    its evidence — including available facts that were never cited.
    """
    session = await require_session(repo, session_id)
    try:
        events, _checkpoints, analysis, _ = await analyze_session(repo, session_id)
        graph = _audit_engine.build_evidence_graph(
            events,
            session=_session_dict(session),
            failure_explanations=analysis.get("failure_explanations", []),
        )
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    record_event("evidence_graph_viewed", session_id=session_id)
    return EvidenceGraphResponse(session_id=session_id, graph=graph)
