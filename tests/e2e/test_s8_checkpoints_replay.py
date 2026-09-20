"""E2E S8 — checkpoints over HTTP + replay + restore semantics.

This scenario is the direct regression test for the checkpoint gap found by
the e2e suite: checkpoints captured in transport mode used to be silently
dropped because neither HttpTransport nor the collector had a checkpoint path.
"""

from __future__ import annotations

import pytest

from .agents import checkpointed_pipeline_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_checkpoints_survive_http_delivery(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/checkpoints")
    assert resp.status_code == 200
    checkpoints = resp.json()["checkpoints"]
    assert len(checkpoints) == 3
    stored_ids = {cp["id"] for cp in checkpoints}
    assert stored_ids == set(result.checkpoint_ids)


async def test_checkpoint_payload_roundtrip(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())
    resp = await api.get(f"/api/checkpoints/{result.checkpoint_ids[1]}")
    assert resp.status_code == 200
    checkpoint = resp.json()
    assert checkpoint["state"]["data"]["stage"] == "transformed"
    assert checkpoint["state"]["data"]["aggregates"] == 84
    assert checkpoint["memory"]["last_table"] == "revenue_daily"


async def test_replay_endpoint_sees_full_session(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/replay")
    assert resp.status_code == 200
    replay = resp.json()
    assert replay["session_id"] == result.session_id
    assert replay["events"]
    assert replay["checkpoints"]
    assert replay["nearest_checkpoint"] is not None


async def test_restore_creates_new_session_with_checkpoint_state(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())
    resp = await api.post(f"/api/checkpoints/{result.checkpoint_ids[1]}/restore", json={})
    assert resp.status_code == 200
    restore = resp.json()
    assert restore["checkpoint_id"] == result.checkpoint_ids[1]
    new_session_id = restore.get("new_session_id") or restore.get("session_id")
    assert new_session_id != result.session_id
    detail = await api.get(f"/api/sessions/{new_session_id}")
    assert detail.status_code == 200


async def test_pipeline_failure_gets_audit_and_narrative(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]
    assert audit["failures"], "warehouse lock failure must be localized"
    narrative = audit["failure_narrative"]
    assert narrative["available"] is True
    assert narrative["symptom"]["failure_event_id"] == result.event_ids["failure"]
