"""SSE stream cursor recovery: Last-Event-ID reconnect replays the gap.

A reconnecting EventSource sends the last received event id back as the
Last-Event-ID header. The stream must then replay the persisted events
published after that cursor — deduplicated against the live queue — so a
disconnect never silently skips events. These tests drive the real route
through the in-process app with a bounded connection time.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from api import app_context
from storage import TraceRepository


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_event(session_id: str, name: str, sequence: int) -> TraceEvent:
    base = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    return TraceEvent(
        id=f"{session_id}-{name}",
        session_id=session_id,
        event_type=EventType.AGENT_TURN,
        name=name,
        data={"sequence": sequence},
        timestamp=base + timedelta(seconds=sequence),
    )


async def _seed(session_id: str, names: list[str]) -> list[TraceEvent]:
    events = [_make_event(session_id, name, idx) for idx, name in enumerate(names)]
    session = Session(
        id=session_id,
        agent_name="sse-recovery",
        framework="pytest",
        status=SessionStatus.COMPLETED,
    )
    async with app_context.require_session_maker()() as db:
        repo = TraceRepository(db)
        await repo.create_session(session)
        for event in events:
            await repo.add_event(event)
        await db.commit()
    return events


def _parse_blocks(body: str) -> list[tuple[str, dict]]:
    """Parse (id, data-json) pairs from event blocks.

    Keepalive comments and the terminal close block (whose payload carries
    no event id) are ignored.
    """
    blocks: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        event_id = None
        data = None
        for line in block.splitlines():
            if line.startswith("id: "):
                event_id = line[4:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if data is not None and isinstance(data, dict) and "id" in data:
            blocks.append((event_id, data))
    return blocks


@pytest.fixture
def bounded_sse(monkeypatch):
    import api.services.ingestion as ingestion_service

    monkeypatch.setattr(ingestion_service, "DEFAULT_SSE_TIMEOUT", 1)


@pytest.mark.asyncio
async def test_replayed_blocks_carry_event_ids(api_client, bounded_sse):
    session_id = _uid("sse-ids")
    alpha, beta = await _seed(session_id, ["alpha", "beta"])

    response = await api_client.get(
        f"/api/sessions/{session_id}/stream",
        headers={"Last-Event-ID": "never-seen"},
    )
    assert response.status_code == 200
    blocks = _parse_blocks(response.text)
    assert [block_id for block_id, _ in blocks] == [alpha.id, beta.id]
    for block_id, data in blocks:
        assert block_id == data["id"]


@pytest.mark.asyncio
async def test_reconnect_replays_events_after_cursor(api_client, bounded_sse):
    session_id = _uid("sse-replay")
    alpha, beta, gamma = await _seed(session_id, ["alpha", "beta", "gamma"])

    response = await api_client.get(
        f"/api/sessions/{session_id}/stream",
        headers={"Last-Event-ID": alpha.id},
    )
    assert response.status_code == 200
    blocks = _parse_blocks(response.text)
    assert [block_id for block_id, _ in blocks] == [beta.id, gamma.id]
    assert [data["name"] for _, data in blocks] == ["beta", "gamma"]


@pytest.mark.asyncio
async def test_unknown_cursor_replays_whole_session(api_client, bounded_sse):
    session_id = _uid("sse-unknown")
    alpha, beta = await _seed(session_id, ["alpha", "beta"])

    response = await api_client.get(
        f"/api/sessions/{session_id}/stream",
        headers={"Last-Event-ID": "never-seen"},
    )
    assert response.status_code == 200
    assert [block_id for block_id, _ in _parse_blocks(response.text)] == [alpha.id, beta.id]


@pytest.mark.asyncio
async def test_live_event_deduplicated_against_replay(api_client, bounded_sse):
    session_id = _uid("sse-dedupe")
    alpha, beta = await _seed(session_id, ["alpha", "beta"])

    # The replay delivers beta; a live publish of the SAME event while the
    # stream is open must be suppressed by id instead of delivered twice.
    from collector.buffer import get_event_buffer

    stream = asyncio.create_task(
        api_client.get(
            f"/api/sessions/{session_id}/stream",
            headers={"Last-Event-ID": alpha.id},
        )
    )
    await asyncio.sleep(0.3)  # subscribe + replay settled, stream now live
    await get_event_buffer().publish(session_id, beta)
    response = await asyncio.wait_for(stream, timeout=10.0)

    assert response.status_code == 200
    ids = [block_id for block_id, _ in _parse_blocks(response.text)]
    assert ids.count(beta.id) == 1
    assert ids == [beta.id]


@pytest.mark.asyncio
async def test_live_event_after_replay_is_delivered(api_client, bounded_sse):
    session_id = _uid("sse-live")
    alpha = (await _seed(session_id, ["alpha"]))[0]
    live = _make_event(session_id, "live-one", 5)
    # Persist the live event too — a real publish path stores before fan-out.
    async with app_context.require_session_maker()() as db:
        repo = TraceRepository(db)
        await repo.add_event(live)
        await db.commit()

    from collector.buffer import get_event_buffer

    stream = asyncio.create_task(
        api_client.get(
            f"/api/sessions/{session_id}/stream",
            headers={"Last-Event-ID": alpha.id},
        )
    )
    await asyncio.sleep(0.3)
    await get_event_buffer().publish(session_id, live)
    response = await asyncio.wait_for(stream, timeout=10.0)

    assert response.status_code == 200
    names = [data["name"] for _, data in _parse_blocks(response.text)]
    assert names == ["live-one"]
