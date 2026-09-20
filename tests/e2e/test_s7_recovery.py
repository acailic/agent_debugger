"""E2E S7 — recovery: a failure repaired in-run must not sink the trust score."""

from __future__ import annotations

import pytest

from .agents import recovery_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_successful_repair_recovers_trust(api, e2e_sdk):
    result = await run_scenario(recovery_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    components = audit["trust"]["components"]
    assert components["recovery_rate"] == 1.0
    assert audit["trust"]["band"] in {"medium", "high"}
    assert audit["summary"]["verdict"] in {"pass", "review"}


async def test_failure_is_still_localized_despite_recovery(api, e2e_sdk):
    result = await run_scenario(recovery_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    assert audit["failures"], "the 403 failure must still be on the record"
    narrative = audit["failure_narrative"]
    assert narrative["available"] is True
    assert narrative["symptom"]["failure_event_id"] == result.event_ids["failure"]


async def test_post_repair_decision_is_verified_against_retry_result(api, e2e_sdk):
    result = await run_scenario(recovery_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    claim = next(c for c in audit["claims"] if c["event_id"] == result.event_ids["decision"])
    assert claim["verification_status"] == "verified"
    assert claim["evidence_refs"] == [result.event_ids["retry"]]


async def test_repair_attempt_event_survives_http_delivery(api, e2e_sdk):
    result = await run_scenario(recovery_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/trace")
    events = resp.json()["events"]
    repairs = [e for e in events if e["event_type"].upper() == "REPAIR_ATTEMPT"]
    assert len(repairs) == 1
    assert str(repairs[0]["repair_outcome"]).lower().endswith("success")
    assert "User-Agent" in repairs[0]["repair_diff"]
