"""E2E — authenticated SDK semantic restore (W04/Q10).

The full loop, the way a user runs it: a small traced session is delivered to
the real server (with an API key), a checkpoint is anchored mid-run, and
``TraceContext.restore`` is called through the SDK. The SDK must hit the
semantic restore endpoint with the configured Bearer key, adopt the returned
ids/provenance, and leave the source session untouched — while starting NO
execution. Assertions then go over the operator HTTP API.
"""

from __future__ import annotations

import uuid

import pytest

from agent_debugger_sdk import trace_session
from agent_debugger_sdk.core.context import TraceContext

from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def _run_source_session() -> dict[str, str]:
    """Traced run with a mid-session checkpoint anchored on the failed load.

    The checkpoint is anchored (``set_parent``) on the failing tool result so
    the semantic restore has a non-empty prefix to copy; the post-checkpoint
    on-call notification must NOT be copied into the restored session.
    """
    session_id = f"e2e-restore-src-{uuid.uuid4().hex[:10]}"
    ids: dict[str, str] = {"session_id": session_id}

    async def scenario() -> None:
        async with trace_session(
            "restore_agent", session_id=session_id, tags=["e2e", "restore"]
        ) as ctx:
            turn_id = await ctx.record_agent_turn(
                agent_id="restore_agent",
                speaker="user",
                turn_index=0,
                content="Roll back the failed warehouse load.",
            )
            load_id = await ctx.record_tool_result(
                "warehouse_load",
                result=None,
                error="destination table locked",
                duration_ms=120,
                upstream_event_ids=[turn_id],
            )
            ctx.set_parent(load_id)  # anchor the checkpoint on the failed load
            ids["checkpoint_id"] = await ctx.create_checkpoint(
                state={"stage": "loaded", "rows": 10},
                memory={"last_table": "revenue_daily"},
                importance=0.8,
            )
            ctx.clear_parent()
            # Post-checkpoint activity: must stay out of the restored prefix.
            await ctx.record_tool_result("notify_oncall", result={"paged": True}, duration_ms=15)
            ids["turn_id"] = turn_id
            ids["load_id"] = load_id

    await run_scenario(scenario())
    return ids


async def _traces(api, session_id: str) -> list[dict]:
    resp = await api.get(f"/api/sessions/{session_id}/traces", params={"limit": 100})
    assert resp.status_code == 200
    return resp.json()["traces"]


async def _checkpoints(api, session_id: str) -> list[dict]:
    resp = await api.get(f"/api/sessions/{session_id}/checkpoints")
    assert resp.status_code == 200
    return resp.json()["checkpoints"]


async def test_sdk_semantic_restore_authenticated_end_to_end(api, e2e_sdk):
    source = await _run_source_session()
    session_id = source["session_id"]
    checkpoint_id = source["checkpoint_id"]

    # Source state before the restore (to prove it is preserved).
    source_trace_before = await _traces(api, session_id)
    source_event_ids_before = [event["id"] for event in source_trace_before]
    source_checkpoint_ids_before = [cp["id"] for cp in await _checkpoints(api, session_id)]

    # Restore through the SDK: config carries the e2e endpoint + API key, so
    # the semantic restore POST goes out with the Bearer header.
    ctx = await run_scenario(TraceContext.restore(checkpoint_id))

    # --- The SDK object adopts the server-returned ids/provenance. ---
    provenance = ctx.restore_provenance
    assert provenance is not None
    assert provenance.restore_mode == "semantic-post"
    assert provenance.source_checkpoint_id == checkpoint_id
    assert provenance.source_session_id == session_id
    assert provenance.new_session_id == ctx.session_id
    assert provenance.restore_event_id
    assert provenance.new_checkpoint_id
    assert provenance.restore_token
    assert provenance.copied_event_count == 3  # session_start + turn + failed load
    assert ctx.session.config["restore_provenance"]["restore_mode"] == "semantic-post"
    assert ctx.restored_state is not None
    assert ctx.restored_state.data == {"stage": "loaded", "rows": 10}

    # --- No execution was started by the restore. ---
    assert ctx._entered is False
    assert ctx._transport is None
    assert await ctx.get_events() == []

    new_session_id = provenance.new_session_id
    assert new_session_id != session_id

    # --- Over HTTP: the new session exists with the copied prefix + marker. ---
    new_trace = await _traces(api, new_session_id)
    marker, copied = new_trace[0], new_trace[1:]
    assert marker["id"] == provenance.restore_event_id
    assert marker["name"] == "session_restored"
    assert marker["data"]["source_checkpoint_id"] == checkpoint_id
    assert marker["data"]["source_session_id"] == session_id
    assert marker["data"]["copied_event_count"] == 3

    assert len(copied) == 3
    copied_ids = [event["id"] for event in copied]
    assert len(set(copied_ids)) == 3  # fresh, unique ids
    assert set(copied_ids).isdisjoint(source_event_ids_before)
    assert all(event["session_id"] == new_session_id for event in copied)
    # The pre-anchor turn and the anchor load were copied (with new ids)...
    assert {source["turn_id"], source["load_id"]} <= set(source_event_ids_before)
    # ...and the post-checkpoint on-call page was NOT copied.
    assert all("notify_oncall" not in (event.get("name") or "") for event in new_trace)

    # The new session holds the handed-off state as its initial checkpoint.
    new_checkpoints = await _checkpoints(api, new_session_id)
    assert [cp["id"] for cp in new_checkpoints] == [provenance.new_checkpoint_id]
    initial = new_checkpoints[0]
    assert initial["sequence"] == 1
    assert initial["state"]["framework"] == "custom"
    assert initial["state"]["data"] == {"stage": "loaded", "rows": 10}
    assert initial["memory"] == {"last_table": "revenue_daily"}

    # --- The source session is unchanged. ---
    source_trace_after = await _traces(api, session_id)
    assert [event["id"] for event in source_trace_after] == source_event_ids_before
    assert all(event["name"] != "session_restored" for event in source_trace_after)
    assert [cp["id"] for cp in await _checkpoints(api, session_id)] == source_checkpoint_ids_before
    assert checkpoint_id in source_checkpoint_ids_before
