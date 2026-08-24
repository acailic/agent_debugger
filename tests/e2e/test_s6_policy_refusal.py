"""E2E S6 — policy violation + refusal: guardrails fire and the audit says so."""

from __future__ import annotations

import pytest

from .agents import policy_refusal_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_policy_violation_lowers_trust_and_fails_verdict(api, e2e_sdk):
    result = await run_scenario(policy_refusal_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    assert audit["trust"]["band"] == "low"
    assert audit["summary"]["verdict"] == "fail"
    policy_signals = [s for s in audit["signals"] if s["type"] == "policy_violation"]
    assert policy_signals
    assert "pii_export_without_approval" in policy_signals[0]["message"]
    assert audit["trust"]["components"]["policy_compliance"] < 1.0


async def test_refusal_is_localized_as_guardrail_block(api, e2e_sdk):
    result = await run_scenario(policy_refusal_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    narrative = audit["failure_narrative"]
    assert narrative["available"] is True
    assert narrative["symptom"]["mechanism_category"] == "guardrail_or_policy_block"
    guardrail_modes = {
        "guardrail_block",
        "policy_mismatch",
    }
    assert narrative["symptom"]["mode"] in guardrail_modes


async def test_safety_analysis_endpoint_sees_the_guardrail_event(api, e2e_sdk):
    result = await run_scenario(policy_refusal_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/safety")
    assert resp.status_code == 200
    body = resp.json()
    report = body.get("safety_report", body)
    assert report["total_steps"] >= 1
    assert report["is_safe"] is False
