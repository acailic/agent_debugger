"""Tests for M2.3 — semantic checkpoint restore (POST /api/checkpoints/{id}/restore).

Restoring a checkpoint must produce a new session that carries the source
session's history up to and including the checkpoint's anchor event (copied
with fresh ids and remapped internal references), a leading restore-marker
event, and an initial checkpoint holding the source state and memory — so the
restored run keeps its history, its state, and its auditability.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, TraceEvent
from api.main import create_app
from storage import TraceRepository

# Event ids are a global primary key (shared per-worker SQLite file), so every
# seed call mints a unique batch of ids.
_id_counter = itertools.count(1)

_BASE_TS = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
_PREWAPPED_STATE = {"framework": "custom", "data": {"stage": 2}}
_MEMORY = {"last_table": "revenue_daily"}


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str,
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
        timestamp=timestamp or _BASE_TS,
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


async def _seed_restorable_session(
    session_id: str,
    *,
    checkpoint_id: str,
    checkpoint_state: dict,
) -> dict[str, str]:
    """Seed a source session + anchored checkpoint; return the seeded event ids.

    Event order (by timestamp): u1 (parented on a dangling "ghost" id),
    c1 (TOOL_CALL), t1 (TOOL_RESULT under c1), d1 (DECISION citing t1 plus an
    out-of-prefix evidence id and an out-of-prefix upstream id), a1 (TOOL_RESULT
    — the checkpoint anchor), f1 (TOOL_RESULT under d1, after the anchor).
    """
    from api import app_context

    n = next(_id_counter)
    ids = {name: f"rs{n}-{name}" for name in ("u1", "c1", "t1", "d1", "anchor", "f1")}

    async with app_context.require_session_maker()() as db_session:
        repo = TraceRepository(db_session)
        await repo.create_session(
            Session(id=session_id, agent_name="restore_agent", framework="pytest")
        )
        events = [
            # Dangling parent ("ghost") must be dropped on copy.
            _event(
                ids["u1"],
                EventType.AGENT_TURN,
                session_id,
                parent_id=f"rs{n}-ghost",
                timestamp=_BASE_TS,
                content="use the cached report",
            ),
            _event(
                ids["c1"],
                EventType.TOOL_CALL,
                session_id,
                timestamp=_BASE_TS.replace(minute=1),
                tool_name="search",
            ),
            _event(
                ids["t1"],
                EventType.TOOL_RESULT,
                session_id,
                parent_id=ids["c1"],
                timestamp=_BASE_TS.replace(minute=2),
                tool_name="search",
                result={"hits": 2},
            ),
            _event(
                ids["d1"],
                EventType.DECISION,
                session_id,
                upstream_event_ids=[ids["c1"], f"rs{n}-outside-upstream"],
                timestamp=_BASE_TS.replace(minute=3),
                confidence=0.9,
                chosen_action="ship",
                evidence_event_ids=[ids["t1"], f"rs{n}-outside-evidence"],
            ),
            _event(
                ids["anchor"],
                EventType.TOOL_RESULT,
                session_id,
                timestamp=_BASE_TS.replace(minute=4),
                tool_name="query",
                result={"rows": 10},
            ),
            # Post-anchor event must NOT be copied.
            _event(
                ids["f1"],
                EventType.TOOL_RESULT,
                session_id,
                parent_id=ids["d1"],
                timestamp=_BASE_TS.replace(minute=5),
                tool_name="deploy",
            ),
        ]
        await repo.add_events_batch(events)
        await repo.create_checkpoint(
            Checkpoint(
                id=checkpoint_id,
                session_id=session_id,
                event_id=ids["anchor"],
                sequence=1,
                state=checkpoint_state,
                memory=dict(_MEMORY),
                timestamp=_BASE_TS.replace(minute=4),
                importance=0.8,
            )
        )
        await db_session.commit()
    return ids


async def _restore(
    client: AsyncClient, checkpoint_id: str, new_session_id: str
) -> dict:
    resp = await client.post(
        f"/api/checkpoints/{checkpoint_id}/restore",
        json={"session_id": new_session_id},
    )
    assert resp.status_code == 200
    return resp.json()


async def _trace(client: AsyncClient, session_id: str) -> list[dict]:
    resp = await client.get(f"/api/sessions/{session_id}/traces", params={"limit": 100})
    assert resp.status_code == 200
    return resp.json()["traces"]


async def _checkpoints(client: AsyncClient, session_id: str) -> list[dict]:
    resp = await client.get(f"/api/sessions/{session_id}/checkpoints")
    assert resp.status_code == 200
    return resp.json()["checkpoints"]


# ---------------------------------------------------------------------------
# Prefix carry-over: structure + reference remapping + dropped outside refs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_copies_prefix_events_with_remapped_references(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-prefix-source"
    new_id = "restore-prefix-new"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ids = await _seed_restorable_session(
            source_id, checkpoint_id="restore-prefix-cp", checkpoint_state=_PREWAPPED_STATE
        )

        body = await _restore(client, "restore-prefix-cp", new_id)

        # Backwards-compatible fields survive.
        assert body["checkpoint_id"] == "restore-prefix-cp"
        assert body["original_session_id"] == source_id
        assert body["new_session_id"] == new_id
        assert body["restore_token"]
        assert body["restored_at"]
        assert body["state"] == _PREWAPPED_STATE
        assert body["replayed_events_count"] is None
        assert body["drift_detected"] is None

        # Prefix of u1, c1, t1, d1, anchor — post-anchor f1 excluded.
        assert body["copied_event_count"] == 5
        assert body["new_checkpoint_id"]
        assert body["restore_event_id"]

        source_events = await _trace(client, source_id)
        source_prefix = source_events[:5]
        assert [e["id"] for e in source_prefix] == [
            ids["u1"],
            ids["c1"],
            ids["t1"],
            ids["d1"],
            ids["anchor"],
        ]

        trace = await _trace(client, new_id)
        assert len(trace) == 6  # marker + 5 copied events
        marker, copied = trace[0], trace[1:]

        assert marker["id"] == body["restore_event_id"]
        assert marker["timestamp"] < copied[0]["timestamp"]  # marker lists first

        new_id_of = {src["id"]: dst["id"] for src, dst in zip(source_prefix, copied)}
        assert len(set(new_id_of.values())) == 5  # fresh, unique ids
        for src, dst in zip(source_prefix, copied):
            assert dst["id"] != src["id"]
            assert dst["session_id"] == new_id
            assert dst["event_type"] == src["event_type"]
            assert dst["name"] == src["name"]
            assert dst["timestamp"] == src["timestamp"]
            assert dst["importance"] == src["importance"]
            # data preserved except remapped id lists
            src_data = {k: v for k, v in src["data"].items() if k != "evidence_event_ids"}
            dst_data = {k: v for k, v in dst["data"].items() if k != "evidence_event_ids"}
            assert dst_data == src_data

        by_new_id = {e["id"]: e for e in copied}
        # In-prefix parent reference remapped.
        assert by_new_id[new_id_of[ids["t1"]]]["parent_id"] == new_id_of[ids["c1"]]
        # Dangling parent reference dropped.
        assert by_new_id[new_id_of[ids["u1"]]]["parent_id"] is None
        # In-prefix evidence/upstream ids remapped; outside refs dropped.
        decision = by_new_id[new_id_of[ids["d1"]]]
        assert decision["evidence_event_ids"] == [new_id_of[ids["t1"]]]
        assert decision["upstream_event_ids"] == [new_id_of[ids["c1"]]]


# ---------------------------------------------------------------------------
# State hand-off: initial checkpoint in the new session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_creates_initial_checkpoint_with_source_state(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-state-source"
    new_id = "restore-state-new"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed_restorable_session(
            source_id, checkpoint_id="restore-state-cp", checkpoint_state=_PREWAPPED_STATE
        )
        body = await _restore(client, "restore-state-cp", new_id)

        checkpoints = await _checkpoints(client, new_id)
        assert len(checkpoints) == 1
        cp = checkpoints[0]
        assert cp["id"] == body["new_checkpoint_id"]
        assert cp["session_id"] == new_id
        assert cp["sequence"] == 1
        assert cp["state"]["framework"] == "custom"
        assert cp["state"]["data"] == {"stage": 2}
        assert cp["memory"] == _MEMORY

        # The checkpoint anchors on the copied anchor event.
        trace = await _trace(client, new_id)
        copied_anchor = trace[5]  # marker + u1', c1', t1', d1', anchor'
        assert copied_anchor["id"] != ""
        assert cp["event_id"] == copied_anchor["id"]

        single = await client.get(f"/api/checkpoints/{cp['id']}")
        assert single.status_code == 200
        assert single.json()["id"] == cp["id"]


@pytest.mark.asyncio
async def test_restore_wraps_plain_dict_state_like_the_sdk(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-wrap-source"
    new_id = "restore-wrap-new"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed_restorable_session(
            source_id, checkpoint_id="restore-wrap-cp", checkpoint_state={"stage": 7}
        )
        body = await _restore(client, "restore-wrap-cp", new_id)
        assert body["state"] == {"stage": 7}  # response echoes the raw source state

        checkpoints = await _checkpoints(client, new_id)
        assert len(checkpoints) == 1
        state = checkpoints[0]["state"]
        assert state["framework"] == "custom"
        assert state["data"] == {"stage": 7}
        assert state["label"] == ""
        assert isinstance(state["created_at"], str)


# ---------------------------------------------------------------------------
# Restore marker event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_marker_event_carries_provenance(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-marker-source"
    new_id = "restore-marker-new"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed_restorable_session(
            source_id, checkpoint_id="restore-marker-cp", checkpoint_state=_PREWAPPED_STATE
        )
        body = await _restore(client, "restore-marker-cp", new_id)

        trace = await _trace(client, new_id)
        marker = trace[0]
        assert marker["id"] == body["restore_event_id"]
        assert marker["event_type"] == "agent_start"
        assert marker["name"] == "session_restored"
        assert marker["data"]["restore_token"] == body["restore_token"]
        assert marker["data"]["source_checkpoint_id"] == "restore-marker-cp"
        assert marker["data"]["source_session_id"] == source_id
        assert marker["data"]["copied_event_count"] == 5
        assert marker["data"]["restored_at"] == body["restored_at"]


# ---------------------------------------------------------------------------
# Audit coherence of a restored session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restored_session_is_audit_coherent(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-audit-source"
    new_id = "restore-audit-new"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed_restorable_session(
            source_id, checkpoint_id="restore-audit-cp", checkpoint_state=_PREWAPPED_STATE
        )
        await _restore(client, "restore-audit-cp", new_id)

        resp = await client.get(f"/api/sessions/{new_id}/audit")
        assert resp.status_code == 200
        audit = resp.json()["audit"]

        trace = await _trace(client, new_id)
        new_event_ids = {event["id"] for event in trace}
        decisions = [event for event in trace if event["event_type"] == "decision"]
        assert len(decisions) == 1  # the copied decision

        claims = [claim for claim in audit["claims"] if claim["event_id"] == decisions[0]["id"]]
        assert len(claims) == 1
        claim = claims[0]
        assert claim["evidence_refs"]
        assert all(ref in new_event_ids for ref in claim["evidence_refs"])
        # The copied decision cites the copied tool result — tool-backed.
        assert claim["verification_status"] == "verified"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_unknown_checkpoint_returns_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/checkpoints/{uuid4()}/restore", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Determinism: two restores from the same checkpoint are structurally equal
# ---------------------------------------------------------------------------


def _normalize_trace(trace: list[dict]) -> list[dict]:
    """Reduce a trace to structure + positional references (no volatile ids)."""
    pos_of = {event["id"]: i for i, event in enumerate(trace)}
    normalized = []
    for event in trace:
        data = {
            key: value
            for key, value in event["data"].items()
            if key not in {"restore_token", "restored_at"}
        }
        normalized.append(
            {
                "event_type": event["event_type"],
                "name": event["name"],
                "timestamp": event["timestamp"],
                "importance": event["importance"],
                "data": data,
                "parent_pos": pos_of.get(event["parent_id"]) if event["parent_id"] else None,
                "upstream_pos": [pos_of[ref] for ref in event["upstream_event_ids"]],
                "evidence_pos": [pos_of[ref] for ref in (event.get("evidence_event_ids") or [])],
            }
        )
    return normalized


@pytest.mark.asyncio
async def test_restoring_twice_yields_structurally_equal_prefixes(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    source_id = "restore-det-source"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed_restorable_session(
            source_id, checkpoint_id="restore-det-cp", checkpoint_state=_PREWAPPED_STATE
        )
        body1 = await _restore(client, "restore-det-cp", "restore-det-new-1")
        body2 = await _restore(client, "restore-det-cp", "restore-det-new-2")

        assert body1["copied_event_count"] == body2["copied_event_count"]
        assert body1["new_session_id"] != body2["new_session_id"]
        assert body1["restore_event_id"] != body2["restore_event_id"]
        assert body1["restore_token"] != body2["restore_token"]

        trace1 = await _trace(client, "restore-det-new-1")
        trace2 = await _trace(client, "restore-det-new-2")
        assert _normalize_trace(trace1) == _normalize_trace(trace2)

        # Handed-off state matches on the stable fields (created_at is per-restore).
        cp1, cp2 = (
            (await _checkpoints(client, "restore-det-new-1"))[0],
            (await _checkpoints(client, "restore-det-new-2"))[0],
        )
        assert cp1["state"]["framework"] == cp2["state"]["framework"]
        assert cp1["state"]["data"] == cp2["state"]["data"]
        assert cp1["memory"] == cp2["memory"]
