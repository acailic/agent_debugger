"""Route-level tests for CUSTOM_CONDITION breakpoint creation (Q07).

The stepper API must validate custom_condition predicates at creation time
(pre-mutation) and surface rejection as an explicit 4xx naming the
unsupported construct, instead of accepting the breakpoint and failing later
during step/continue. Valid predicates keep working end to end: the
breakpoint is created and a later CONTINUE triggers on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from api.main import create_app
from storage import TraceRepository


def _make_session(session_id: str) -> Session:
    return Session(
        id=session_id,
        agent_name="route-conditions-agent",
        framework="pytest",
        started_at=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc),
        config={},
    )


def _make_event(session_id: str, event_id: str, name: str) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        timestamp=datetime(2026, 9, 20, 10, 5, tzinfo=timezone.utc),
        event_type=EventType.DECISION,
        name=name,
        data={},
        metadata={},
        importance=0.8,
        upstream_event_ids=[],
        parent_id=None,
    )


async def _seed_session(session_id: str, event_name: str) -> None:
    """Persist one session with two events under the local tenant."""
    from api import app_context

    session_maker = app_context.require_session_maker()
    async with session_maker() as db:
        repo = TraceRepository(db)
        await repo.create_session(_make_session(session_id))
        await repo.add_event(_make_event(session_id, f"{session_id}-ev-1", "warmup_event"))
        await repo.add_event(_make_event(session_id, f"{session_id}-ev-2", event_name))
        await db.commit()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition", "expected_fragment"),
    [
        # The exact probe from the delivery follow-up: previously accepted at
        # creation, only blowing up later during evaluation.
        ("len(event.data) > 0", "function calls"),
        ("__import__('os').system('id')", "function calls"),
        ("event.__class__", "dunder attribute"),
        ("x > 1", "names other than 'event'"),
        ("event.importance >", "invalid syntax"),
    ],
)
async def test_set_breakpoint_rejects_invalid_condition_with_422(condition, expected_fragment):
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = _uid("route-cond")
    await _seed_session(session_id, "target_event")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/sessions/{session_id}/breakpoints",
            params={
                "breakpoint_type": "custom_condition",
                "condition_value": condition,
                "description": "should be rejected",
            },
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "custom condition uses unsupported construct" in detail
    assert expected_fragment in detail


@pytest.mark.asyncio
async def test_rejected_breakpoint_is_not_materialized():
    """A 422 must leave no breakpoint behind (pre-mutation rejection)."""
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = _uid("route-cond")
    await _seed_session(session_id, "target_event")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rejected = await client.post(
            f"/api/sessions/{session_id}/breakpoints",
            params={"breakpoint_type": "custom_condition", "condition_value": "len(event.name)"},
        )
        assert rejected.status_code == 422

        listed = await client.get(f"/api/sessions/{session_id}/breakpoints")
        assert listed.status_code == 200
        assert listed.json()["breakpoints"] == []


@pytest.mark.asyncio
async def test_valid_condition_creates_and_later_triggers():
    """Valid predicate -> 2xx creation, and a CONTINUE step hits it."""
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = _uid("route-cond")
    target_name = _uid("route-cond-target")
    await _seed_session(session_id, target_name)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/sessions/{session_id}/breakpoints",
            params={
                "breakpoint_type": "custom_condition",
                "condition_value": f"event.name == '{target_name}'",
                "description": "break on the target event",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["breakpoint"]["breakpoint_type"] == "custom_condition"
        assert body["breakpoint"]["condition_value"] == f"event.name == '{target_name}'"

        stepped = await client.post(
            f"/api/sessions/{session_id}/step",
            params={"action": "continue"},
        )
        assert stepped.status_code == 200, stepped.text
        step_result = stepped.json()["step_result"]
        assert step_result["breakpoint_hit"] is not None
        assert step_result["current_event"]["name"] == target_name
        assert step_result["breakpoint_hit"]["hit_count"] == 1


@pytest.mark.asyncio
async def test_non_custom_breakpoint_types_skip_condition_validation():
    """Other breakpoint types never had a grammar; creation stays unchanged."""
    app = create_app()
    transport = ASGITransport(app=app)
    session_id = _uid("route-cond")
    await _seed_session(session_id, "target_event")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/sessions/{session_id}/breakpoints",
            params={"breakpoint_type": "event_type", "condition_value": "decision"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["breakpoint"]["condition_value"] == "decision"
