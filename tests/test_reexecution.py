"""Tests for collector/audit/reexecution.py — the minimal re-execution set.

Covers the M2.1 audit surface: for a suspect decision, the smallest sub-graph
that would need to re-run to confirm or invalidate its claim — the decision,
its cited evidence, the tool calls upstream of that evidence, and the
downstream causal subtree (each marked read-only vs required-rerun) — plus
determinism of the payload and the HTTP route behavior.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api.main import create_app
from collector.audit import SessionAuditEngine
from collector.audit.reexecution import build_reexecution_set
from storage import TraceRepository

# ---------------------------------------------------------------------------
# Helpers (mirror test_failure_narrative.py conventions)
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "reexec-session",
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp or datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    chosen_action: str = "act",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        timestamp=timestamp,
        confidence=confidence,
        chosen_action=chosen_action,
        **data,
    )


def _grounded_session() -> list[TraceEvent]:
    """c1 (TOOL_CALL) → t1 (TOOL_RESULT); d1 (DECISION citing t1) → f1 (TOOL_RESULT)."""
    call = _event("c1", EventType.TOOL_CALL, tool_name="search")
    result = _event(
        "t1",
        EventType.TOOL_RESULT,
        parent_id="c1",
        tool_name="search",
        result={"hits": 2},
    )
    decision = _decision(
        "d1", confidence=0.9, chosen_action="ship", evidence_event_ids=["t1"]
    )
    downstream = _event(
        "f1", EventType.TOOL_RESULT, parent_id="d1", tool_name="deploy"
    )
    return [call, result, decision, downstream]


def _edges(payload: dict) -> list[tuple[str, str, str, str | None]]:
    return [
        (edge["source_id"], edge["target_id"], edge["edge_type"], edge["source_class"])
        for edge in payload["edges"]
    ]


# ---------------------------------------------------------------------------
# Grounded decision: cited evidence + upstream tool call + downstream
# ---------------------------------------------------------------------------


def test_reexecution_set_grounded_decision_cites_tool_result():
    events = _grounded_session()
    report = SessionAuditEngine().audit(events)
    payload = build_reexecution_set(events, report, "d1")

    assert payload is not None
    nodes = {node["event_id"]: node for node in payload["nodes"]}
    assert set(nodes) == {"d1", "t1", "c1", "f1"}
    assert payload["node_count"] == 4
    assert payload["node_count"] == len(payload["nodes"])
    assert nodes["d1"]["role"] == "decision"
    assert nodes["t1"]["role"] == "evidence"
    assert nodes["c1"]["role"] == "upstream_tool_call"
    assert nodes["f1"]["role"] == "downstream"
    assert all(node["why_included"] for node in payload["nodes"])
    assert all(node["mode"] == "required_rerun" for node in payload["nodes"])
    assert nodes["d1"]["event_type"] == "decision"

    edges = _edges(payload)
    assert ("d1", "t1", "evidence", "tool_backed") in edges
    assert ("c1", "t1", "causal", None) in edges
    assert ("d1", "f1", "causal", None) in edges

    markdown = payload["markdown"]
    assert markdown.startswith("# Minimal re-execution set — d1")
    for event_id in {"d1", "t1", "c1", "f1"}:
        assert f"`{event_id}`" in markdown


def test_reexecution_set_upstream_tool_call_omitted_when_evidence_has_no_call():
    # t1 has no parent and no upstream refs — no tool call to re-invoke.
    events = [
        _event("t1", EventType.TOOL_RESULT, tool_name="search", result={"hits": 1}),
        _decision("d1", confidence=0.9, evidence_event_ids=["t1"]),
    ]
    report = SessionAuditEngine().audit(events)
    payload = build_reexecution_set(events, report, "d1")

    assert payload is not None
    assert {node["event_id"] for node in payload["nodes"]} == {"d1", "t1"}
    assert all(node["role"] != "upstream_tool_call" for node in payload["nodes"])


def test_reexecution_set_evidence_free_decision_downstream_only():
    events = [
        _decision("d1", confidence=0.9, chosen_action="ship"),
        _event("f1", EventType.TOOL_RESULT, parent_id="d1", tool_name="deploy"),
    ]
    report = SessionAuditEngine().audit(events)
    payload = build_reexecution_set(events, report, "d1")

    assert payload is not None
    assert {node["event_id"] for node in payload["nodes"]} == {"d1", "f1"}
    assert payload["node_count"] == 2
    roles = {node["event_id"]: node["role"] for node in payload["nodes"]}
    assert roles == {"d1": "decision", "f1": "downstream"}
    assert all(edge["edge_type"] == "causal" for edge in payload["edges"])
    assert ("d1", "f1", "causal", None) in _edges(payload)


def test_reexecution_set_marks_read_only_vs_required_rerun_downstream():
    user_input = _event(
        "u1", EventType.AGENT_TURN, content="use the cached report"
    )
    call = _event("c1", EventType.TOOL_CALL, tool_name="search")
    result = _event(
        "t1",
        EventType.TOOL_RESULT,
        parent_id="c1",
        tool_name="search",
        result={"hits": 1},
    )
    decision = _decision(
        "d1", confidence=0.9, chosen_action="ship", evidence_event_ids=["u1", "t1"]
    )
    downstream_tool = _event(
        "f1", EventType.TOOL_RESULT, parent_id="d1", tool_name="deploy"
    )
    downstream_input = _event(
        "u2", EventType.AGENT_TURN, parent_id="d1", content="keep going"
    )
    events = [user_input, call, result, decision, downstream_tool, downstream_input]
    report = SessionAuditEngine().audit(events)
    payload = build_reexecution_set(events, report, "d1")

    assert payload is not None
    nodes = {node["event_id"]: node for node in payload["nodes"]}
    assert nodes["u1"]["role"] == "evidence"
    assert nodes["u1"]["mode"] == "read_only"
    assert nodes["t1"]["role"] == "evidence"
    assert nodes["t1"]["mode"] == "required_rerun"
    assert nodes["f1"]["role"] == "downstream"
    assert nodes["f1"]["mode"] == "required_rerun"
    assert nodes["u2"]["role"] == "downstream"
    assert nodes["u2"]["mode"] == "read_only"
    assert ("d1", "u1", "evidence", "user_provided") in _edges(payload)
    assert "## Read-only" in payload["markdown"]
    assert "## Required re-runs" in payload["markdown"]


def test_reexecution_set_unknown_or_non_decision_event_returns_none():
    events = _grounded_session()
    report = SessionAuditEngine().audit(events)

    assert build_reexecution_set(events, report, "nope") is None
    # The id of a non-decision event is not a claim — also None.
    assert build_reexecution_set(events, report, "t1") is None


def test_reexecution_set_is_deterministic():
    events = _grounded_session()
    first = build_reexecution_set(
        events, SessionAuditEngine().audit(copy.deepcopy(events)), "d1"
    )
    second = build_reexecution_set(
        copy.deepcopy(events), SessionAuditEngine().audit(copy.deepcopy(events)), "d1"
    )
    assert first == second


# ---------------------------------------------------------------------------
# HTTP route end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reexecution_route_returns_set(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = "reexec-route-session"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(
                Session(
                    id=session_id,
                    agent_name="reexec_agent",
                    framework="pytest",
                    started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
                    status=SessionStatus.COMPLETED,
                    config={},
                    tags=["reexec-route-test"],
                )
            )
            tool_result = TraceEvent(
                id="rr-tool-result",
                session_id=session_id,
                name="search",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
                data={"tool_name": "search", "result": {"hits": 2}},
            )
            decision = TraceEvent(
                id="rr-decision",
                session_id=session_id,
                name="decide",
                event_type=EventType.DECISION,
                timestamp=datetime(2026, 3, 26, 10, 6, tzinfo=timezone.utc),
                data={
                    "confidence": 0.9,
                    "chosen_action": "ship",
                    "evidence_event_ids": ["rr-tool-result"],
                },
            )
            downstream = TraceEvent(
                id="rr-downstream",
                session_id=session_id,
                parent_id="rr-decision",
                name="deploy",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime(2026, 3, 26, 10, 7, tzinfo=timezone.utc),
                data={"tool_name": "deploy"},
            )
            await repo.add_event(tool_result)
            await repo.add_event(decision)
            await repo.add_event(downstream)
            await db_session.commit()

        url = f"/api/sessions/{session_id}/decisions/rr-decision/reexecution-set"
        resp1 = await client.get(url)
        assert resp1.status_code == 200
        body = resp1.json()
        assert body["session_id"] == session_id
        assert body["event_id"] == "rr-decision"
        assert set(body) == {"session_id", "event_id", "reexecution_set"}
        payload = body["reexecution_set"]
        assert set(payload) == {"nodes", "edges", "node_count", "markdown"}
        node_ids = {node["event_id"] for node in payload["nodes"]}
        assert {"rr-decision", "rr-tool-result", "rr-downstream"} <= node_ids
        assert payload["node_count"] == len(payload["nodes"])
        assert payload["markdown"].startswith("# Minimal re-execution set — rr-decision")

        # Two calls over the same session produce equal payloads.
        resp2 = await client.get(url)
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()


@pytest.mark.asyncio
async def test_reexecution_route_unknown_decision_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = "reexec-route-404-session"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(
                Session(
                    id=session_id,
                    agent_name="reexec_agent",
                    framework="pytest",
                    started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
                    status=SessionStatus.COMPLETED,
                    config={},
                    tags=["reexec-route-404"],
                )
            )
            await repo.add_event(
                TraceEvent(
                    id="rr404-tool-result",
                    session_id=session_id,
                    name="search",
                    event_type=EventType.TOOL_RESULT,
                    timestamp=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
                    data={"tool_name": "search", "result": {"hits": 1}},
                )
            )
            await db_session.commit()

        resp = await client.get(
            f"/api/sessions/{session_id}/decisions/nope/reexecution-set"
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reexecution_route_unknown_session_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions/reexec-route-missing-session/decisions/whatever/reexecution-set"
        )
        assert resp.status_code == 404
