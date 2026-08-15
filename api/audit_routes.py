"""Agent audit / trust API routes.

Exposes a per-session audit report that answers the five operator questions
(what / why / evidence / outcome / where-failed) plus an explainable trust
score. The report is produced by :class:`collector.audit.SessionAuditEngine`,
reusing the session's existing failure explanations so it stays consistent
with the replay / causal analysis surfaced elsewhere.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.analytics_db import record_event
from api.dependencies import get_repository
from api.exceptions import NotFoundError
from api.schemas_analysis import (
    DecisionJustificationResponse,
    EvidenceGraphResponse,
    PortfolioAuditResponse,
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
        session_dict = _session_dict(session)
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


@router.get("/api/sessions/{session_id}/success-flow")
async def get_success_flow_advisory(
    session_id: str,
    reference_session_id: str | None = Query(default=None),
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Return a success-flow deviation advisory for a session.

    Aligns the session's step flow against a successful reference run
    (explicit, or auto-selected: most recent completed, error-free session
    of the same agent) and reports the first divergence — a candidate
    first-bad-step in the spirit of OAT's success-flow attribution.

    Advisory by construction: statistical contrast, never feeds the
    deterministic trust score or claim verification.
    """
    from agent_debugger_sdk.core.events import EventType
    from agent_debugger_sdk.core.success_flow import build_success_flow_advisory

    session = await require_session(repo, session_id)
    target_events = await repo.get_event_tree(session_id)

    reference_session = None
    reference_events: list = []
    if reference_session_id:
        reference_session = await require_session(repo, reference_session_id)
        reference_events = await repo.get_event_tree(reference_session_id)
    else:
        candidates = await repo.list_sessions(
            limit=20, agent_name=session.agent_name
        )
        for candidate in candidates:
            if candidate.id == session_id:
                continue
            if str(candidate.status or "") != "SessionStatus.COMPLETED":
                if getattr(candidate.status, "value", None) != "completed":
                    continue
            events = await repo.get_event_tree(candidate.id)
            if any(event.event_type == EventType.ERROR for event in events):
                continue
            reference_session = candidate
            reference_events = events
            break

    if reference_session is None:
        return {
            "session_id": session_id,
            "advisory": None,
            "reason": (
                "No successful reference run found for this agent "
                "(need a completed, error-free session)."
            ),
        }

    advisory = build_success_flow_advisory(
        target_events,
        reference_events,
        reference_session_id=reference_session.id,
    )
    record_event("success_flow_viewed", session_id=session_id)
    return {
        "session_id": session_id,
        "reference": {
            "session_id": reference_session.id,
            "agent_name": reference_session.agent_name,
            "started_at": reference_session.started_at.isoformat()
            if reference_session.started_at
            else None,
        },
        "advisory": advisory,
    }


@router.get("/api/audit/portfolio", response_model=PortfolioAuditResponse)
async def get_audit_portfolio(
    limit: int = Query(default=50, ge=1, le=200),
    repo: TraceRepository = Depends(get_repository),
) -> PortfolioAuditResponse:
    """Return a cross-session audit portfolio: trust + verification aggregated
    across runs.

    The portfolio view lets an operator find the least trustworthy runs
    without opening each session. It audits each recent session with
    :class:`SessionAuditEngine` and reduces the reports into fleet-level
    trust means, verification totals, recurring signal/failure modes, and a
    worst-trust-first per-session list. Deterministic — every number is
    derivable from captured event fields.
    """
    try:
        sessions = await repo.list_sessions(limit=limit)
        reports: list[dict] = []
        sessions_meta: dict[str, dict[str, str | None]] = {}
        for session in sessions:
            events, checkpoints, analysis, _ = await analyze_session(repo, session.id)
            if not events:
                continue
            session_dict = _session_dict(session)
            report = _audit_engine.audit(
                events,
                checkpoints,
                session=session_dict,
                failure_explanations=analysis.get("failure_explanations", []),
            )
            reports.append(report)
            sessions_meta[session.id] = session_dict
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    summary = _audit_engine.aggregate_audits(reports, sessions_meta=sessions_meta)
    record_event("audit_portfolio_viewed")
    return PortfolioAuditResponse(summary=summary)
