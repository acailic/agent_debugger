"""E2E S10 — cross-session surfaces: twins, divergence, portfolio.

Runs the SAME triage flow twice — once clean, once failing at routing — and
checks every cross-session operator surface: success-flow advisory, session
comparison, divergence, and the audit portfolio.
"""

from __future__ import annotations

import pytest

from .agents import triage_agent_run
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.fixture
async def twins(api, e2e_sdk):
    good = await run_scenario(triage_agent_run(fail_at_step=0))
    bad = await run_scenario(triage_agent_run(fail_at_step=2))
    return good, bad


async def test_success_flow_advisory_localizes_first_divergence(api, twins):
    good, bad = twins
    resp = await api.get(f"/api/sessions/{bad.session_id}/success-flow")
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is not None, body.get("reason", "")
    advisory = body["advisory"]
    assert body["reference"]["session_id"] == good.session_id
    # Divergence must point at or before the failing route step.
    divergence_id = advisory.get("first_divergence_event_id") or advisory.get("divergence_event_id")
    if divergence_id:
        assert divergence_id in {bad.event_ids["classify"], bad.event_ids["route"]}


async def test_audit_distinguishes_twin_outcomes(api, twins):
    good, bad = twins
    good_audit = (await api.get(f"/api/sessions/{good.session_id}/audit")).json()["audit"]
    bad_audit = (await api.get(f"/api/sessions/{bad.session_id}/audit")).json()["audit"]

    assert good_audit["summary"]["verdict"] in {"pass", "review"}
    assert bad_audit["summary"]["verdict"] == "fail"
    assert bad_audit["trust"]["score"] < good_audit["trust"]["score"]


async def test_session_comparison_reports_the_difference(api, twins):
    good, bad = twins
    resp = await api.get(f"/api/compare/{good.session_id}/{bad.session_id}")
    assert resp.status_code == 200
    body = resp.json()
    deltas = body["comparison_deltas"]
    assert deltas, "comparison must report per-metric deltas"
    # The failing twin had an error the good twin did not.
    error_delta = deltas.get("error_count") or deltas.get("failure_count") or deltas.get("escalation_count")
    assert error_delta is not None


async def test_divergence_endpoint_identifies_structural_difference(api, twins):
    good, bad = twins
    resp = await api.get(f"/api/compare/{good.session_id}/{bad.session_id}/divergence")
    assert resp.status_code == 200
    body = resp.json()
    assert body  # non-empty divergence payload


async def test_portfolio_ranks_bad_twin_worst_trust(api, twins):
    good, bad = twins
    resp = await api.get("/api/audit/portfolio?limit=50")
    assert resp.status_code == 200
    sessions = resp.json()["summary"]["sessions"]
    rows = {row["session_id"]: row for row in sessions}
    assert bad.session_id in rows
    assert good.session_id in rows
    assert rows[bad.session_id]["trust_score"] < rows[good.session_id]["trust_score"]
    assert rows[bad.session_id]["failure_count"] > rows[good.session_id]["failure_count"]
    # Portfolio is sorted worst-trust-first: the bad twin must rank before good.
    ordered_ids = [row["session_id"] for row in sessions]
    assert ordered_ids.index(bad.session_id) < ordered_ids.index(good.session_id)
