"""Tests for the regression lab's spectrum + reliability slice (roadmap W05).

Covers the two paper-note metrics added to the bundle-run report:

* the Tarantula/Ochiai suspiciousness spectrum
  (``docs/papers/tarantula-test-information-fault-localization.md``) —
  deterministic counting over the per-run verdicts and decision-node keys the
  runner already records, including the Ochiai arithmetic on hand-computed
  corpora, the sort order and cap, the no-spectrum case, the normalized-key
  derivation across recordings with differing event ids, and determinism;
* the τ-bench pass^k reliability figure
  (``docs/papers/tau-bench-pass-k-reliability.md``) — worst-of-k gating over
  already-recorded runs, true / false / empty.

Also pins that the slice is additive: the pre-existing run-result and
comparison report shapes keep exactly their old keys.

All fixtures are in-process (no database, no subprocess); unique ids are
prefixed ``rsx-``.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine
from collector.regression.bundles import (
    ASSERTION_CLAIM_STATUS,
    ASSERTION_TRUST_BAND,
    AUDIT_ENGINE_VERSION,
    BUNDLE_SCHEMA_VERSION,
    MalformedBundleError,
    content_hash,
    decision_node_keys,
    derive_expected_assertions,
)
from collector.regression.runner import (
    BUNDLE_REPORT_VERSION,
    compare_run_results,
    compute_run_reliability,
    compute_run_spectrum,
    events_from_bundle,
    run_bundle,
    summarize_bundle_runs,
)

_BASE_TS = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)

#: Run-result keys that existed before this slice — the additive guard pins
#: that exactly one new key (``decision_nodes``) joined them.
_PRE_SLICE_RUN_KEYS = {
    "run_result_version",
    "session_id",
    "bundle_hash",
    "sanitized",
    "engine",
    "event_count",
    "verdict",
    "passed",
    "failed",
    "total",
    "assertions",
}


def _uid(prefix: str) -> str:
    """Unique id per test run (the xdist rule; every fixture id starts rsx-)."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _node(key: str, headline: str = "decide_answer") -> dict[str, str]:
    """One decision-node identity row as run_bundle records it."""
    return {"key": key, "normalized_key": f"decision:{headline}"}


def _run(
    bundle_hash: str,
    verdict: str,
    nodes: list[dict[str, str]] | None = None,
    *,
    assertions: list[dict] | None = None,
) -> dict:
    """A minimal run result: the verdict and node set the runner records."""
    if assertions is None:
        assertions = [
            {
                "kind": "summary_verdict",
                "path": "summary.verdict",
                "expected": "pass",
                "actual": "pass" if verdict == "pass" else "review",
                "passed": verdict == "pass",
            }
        ]
    return {
        "run_result_version": 1,
        "session_id": "rsx-session",
        "bundle_hash": bundle_hash,
        "verdict": verdict,
        "passed": 1 if verdict == "pass" else 0,
        "failed": 0 if verdict == "pass" else 1,
        "total": 1,
        "assertions": assertions,
        "decision_nodes": nodes if nodes is not None else [],
    }


def _sdk_event(event_id: str, event_type: EventType, session_id: str, *, timestamp: datetime, **data):
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp,
        data=data,
        upstream_event_ids=[],
    )


def _bundle() -> tuple[dict, dict[str, str]]:
    """Hand-build one incident bundle in-process (no database).

    Shape: objective, tool call + successful result, and a decision citing
    that result — the auditable incident of tests/test_regression_lab.py,
    minus the injected failure so the real engine's run passes. The stored
    report/assertions are computed from the exact rebuilt events the runner
    will use, so the bundle's contract is reproducible by construction.
    """
    session_id = _uid("rsx-session")
    ids = {
        name: _uid(f"rsx-{name}")
        for name in ("start", "call", "result", "decision")
    }
    events = [
        _sdk_event(ids["start"], EventType.AGENT_START, session_id, timestamp=_BASE_TS,
                   content="Summarize the quarter revenue report"),
        _sdk_event(ids["call"], EventType.TOOL_CALL, session_id,
                   timestamp=_BASE_TS.replace(minute=1), tool_name="search"),
        _sdk_event(ids["result"], EventType.TOOL_RESULT, session_id,
                   timestamp=_BASE_TS.replace(minute=2), tool_name="search",
                   result={"rows": 3}),
        _sdk_event(ids["decision"], EventType.DECISION, session_id,
                   timestamp=_BASE_TS.replace(minute=3), confidence=0.9,
                   chosen_action="answer", reasoning="grounded in the search results",
                   evidence_event_ids=[ids["result"]]),
    ]
    event_dicts = [event.to_dict() for event in events]
    session = {
        "id": session_id,
        "agent_name": "spectrum-agent",
        "framework": "pytest",
        "status": None,
        "started_at": None,
        "ended_at": None,
        "tags": ["rsx"],
        "config": {},
    }
    report = SessionAuditEngine().audit(
        events_from_bundle({"events": event_dicts}),
        [],
        session={key: session[key] for key in ("id", "status", "agent_name", "started_at", "ended_at")},
    )
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_kind": "agent_debugger.incident_bundle",
        "session": session,
        "sanitized": False,
        "redaction": None,
        "events": event_dicts,
        "checkpoints": [],
        "audit_report": report,
        "expected_assertions": derive_expected_assertions(report),
        "engine": {"audit_engine_version": AUDIT_ENGINE_VERSION},
        "event_count": len(event_dicts),
        "checkpoint_count": 0,
    }
    bundle["content_hash"] = content_hash(bundle)
    return bundle, ids


class _BandTunedEngine:
    """Candidate-engine double: the real engine with one tuned output field."""

    def __init__(self, band: str) -> None:
        self._inner = SessionAuditEngine()
        self._band = band

    def audit(self, events, checkpoints=None, **kwargs):
        report = self._inner.audit(events, checkpoints, **kwargs)
        report["trust"]["band"] = self._band
        return report


def _other_band(band) -> str:
    return "low" if band != "low" else "high"


# ---------------------------------------------------------------------------
# Ochiai arithmetic (hand-computed corpora)
# ---------------------------------------------------------------------------


def test_failed_only_node_scores_exactly_one():
    """Node in 2 failed of 2 failed runs, 0 passed -> Ochiai 1.0."""
    suspect = _node("rsx-node-alpha")
    runs = [
        _run("rsx-bundle", "fail", [suspect]),
        _run("rsx-bundle", "fail", [suspect]),
        _run("rsx-bundle", "pass", [_node("rsx-node-other")]),
    ]

    spectrum = compute_run_spectrum(runs)

    assert spectrum is not None
    assert spectrum["scenarios"] == 1
    assert spectrum["runs"] == 3
    assert spectrum["passed_runs"] == 1
    assert spectrum["failed_runs"] == 2
    assert spectrum["top_suspects"][0] == {
        "key": "rsx-node-alpha",
        "suspiciousness": 1.0,
        "failed_hits": 2,
        "passed_hits": 0,
    }
    # 2 / sqrt(2 * (2 + 0)) == 1.0 exactly, at 4 decimal places.
    assert spectrum["top_suspects"][0]["suspiciousness"] == round(2 / math.sqrt(2 * 2), 4)


def test_mixed_node_scores_the_exact_ochiai_value():
    """3 failed / 5 passed corpus; every node's score checked by hand."""
    runs = [
        # failed: alpha+beta twice, beta+delta once
        _run("rsx-bundle", "fail", [_node("rsx-node-beta"), _node("rsx-node-alpha")]),
        _run("rsx-bundle", "fail", [_node("rsx-node-beta"), _node("rsx-node-alpha")]),
        _run("rsx-bundle", "fail", [_node("rsx-node-beta"), _node("rsx-node-delta")]),
        # passed: alpha+delta once, delta+gamma four times
        _run("rsx-bundle", "pass", [_node("rsx-node-alpha"), _node("rsx-node-delta")]),
        _run("rsx-bundle", "pass", [_node("rsx-node-delta"), _node("rsx-node-gamma")]),
        _run("rsx-bundle", "pass", [_node("rsx-node-delta"), _node("rsx-node-gamma")]),
        _run("rsx-bundle", "pass", [_node("rsx-node-delta"), _node("rsx-node-gamma")]),
        _run("rsx-bundle", "pass", [_node("rsx-node-delta"), _node("rsx-node-gamma")]),
    ]

    spectrum = compute_run_spectrum(runs)

    assert (spectrum["runs"], spectrum["passed_runs"], spectrum["failed_runs"]) == (8, 5, 3)
    # beta 3/sqrt(3*3)=1.0, alpha 2/sqrt(3*3)=0.6667, delta 1/sqrt(3*6)=0.2357,
    # gamma 0/sqrt(3*4)=0.0 — sorted by suspiciousness desc.
    assert spectrum["top_suspects"] == [
        {"key": "rsx-node-beta", "suspiciousness": 1.0, "failed_hits": 3, "passed_hits": 0},
        {"key": "rsx-node-alpha", "suspiciousness": round(2 / 3, 4), "failed_hits": 2, "passed_hits": 1},
        {"key": "rsx-node-delta", "suspiciousness": round(1 / math.sqrt(18), 4), "failed_hits": 1, "passed_hits": 5},
        {"key": "rsx-node-gamma", "suspiciousness": 0.0, "failed_hits": 0, "passed_hits": 4},
    ]


def test_top_suspects_tie_break_on_key_and_cap_at_ten():
    """12 failed-only suspects all score 1.0: key-ascending ties, cap at 10."""
    twelve = [_node(f"rsx-suspect-{index:02d}") for index in range(1, 13)]
    runs = [_run("rsx-bundle", "fail", twelve), _run("rsx-bundle", "pass", [])]

    spectrum = compute_run_spectrum(runs)

    assert len(spectrum["top_suspects"]) == 10
    assert [row["key"] for row in spectrum["top_suspects"]] == [
        f"rsx-suspect-{index:02d}" for index in range(1, 11)
    ]
    assert all(row["suspiciousness"] == 1.0 for row in spectrum["top_suspects"])


# ---------------------------------------------------------------------------
# The no-spectrum case (corpus without both verdicts)
# ---------------------------------------------------------------------------


def test_all_passed_and_all_failed_corpora_have_no_spectrum():
    all_passed = [_run("rsx-bundle", "pass", [_node("rsx-node-any")]) for _ in range(3)]
    all_failed = [_run("rsx-bundle", "fail", [_node("rsx-node-any")]) for _ in range(3)]

    # Documented choice: no passed-and-failed mix -> no spectrum is claimed
    # (None, never an empty ranking that reads as "no suspects").
    assert compute_run_spectrum(all_passed) is None
    assert compute_run_spectrum(all_failed) is None
    assert compute_run_spectrum([]) is None

    report = summarize_bundle_runs(all_passed)
    assert report["spectrum"] is None
    assert report["verdict"] == "pass"
    assert report["reliability"] == {"k": 3, "passes": 3, "pass_hat_k": True}


# ---------------------------------------------------------------------------
# Node identity: event id within one bundle, normalized key across recordings
# ---------------------------------------------------------------------------


def test_same_bundle_runs_aggregate_on_event_id():
    same = _node("rsx-same-decision")
    runs = [
        _run("rsx-bundle", "fail", [same]),
        # Same event id, different headline: the primary identity wins and
        # the normalized keys are never consulted within one bundle.
        _run("rsx-bundle", "pass", [{"key": "rsx-same-decision", "normalized_key": "decision:other"}]),
    ]

    spectrum = compute_run_spectrum(runs)

    assert spectrum["scenarios"] == 1
    assert spectrum["top_suspects"] == [
        {"key": "rsx-same-decision", "suspiciousness": round(1 / math.sqrt(2), 4),
         "failed_hits": 1, "passed_hits": 1}
    ]


def test_differing_event_ids_aggregate_on_normalized_key():
    """Two recordings of one scenario mint fresh ids; type+headline survives."""
    runs = [
        _run("rsx-bundle-a", "fail", [_node("rsx-a-decision-1", headline="decide_answer")]),
        _run("rsx-bundle-b", "pass", [_node("rsx-b-decision-9", headline="decide_answer")]),
    ]

    spectrum = compute_run_spectrum(runs)

    assert spectrum["scenarios"] == 2
    assert spectrum["top_suspects"] == [
        {"key": "decision:decide_answer", "suspiciousness": round(1 / math.sqrt(2), 4),
         "failed_hits": 1, "passed_hits": 1}
    ]


def test_runs_without_decision_nodes_fall_back_to_claim_subjects():
    """Pre-spectrum run results (saved baselines) still count their claims."""
    legacy = _run(
        "rsx-bundle",
        "fail",
        None,
        assertions=[
            {
                "kind": ASSERTION_CLAIM_STATUS,
                "path": "claims.rsx-legacy-claim.verification_status",
                "expected": "verified",
                "actual": "unsupported",
                "passed": False,
                "subject": "rsx-legacy-claim",
            },
            {
                "kind": ASSERTION_TRUST_BAND,
                "path": "trust.band",
                "expected": "high",
                "actual": "high",
                "passed": True,
            },
        ],
    )
    legacy.pop("decision_nodes")  # the shape before this slice

    spectrum = compute_run_spectrum([legacy, _run("rsx-bundle", "pass", [])])

    assert spectrum["top_suspects"] == [
        {"key": "rsx-legacy-claim", "suspiciousness": 1.0, "failed_hits": 1, "passed_hits": 0}
    ]


def test_decision_node_keys_derivation_skips_idless_and_sorts():
    report = {
        "claims": [
            {"event_id": "rsx-claim-2", "event_type": "EventType.DECISION", "headline": "decide b"},
            {"event_id": "rsx-claim-1", "event_type": "EventType.DECISION", "headline": "decide a"},
            {"event_id": "", "event_type": "EventType.DECISION", "headline": "no id, skipped"},
            {"event_type": "EventType.DECISION", "headline": "also skipped"},
        ]
    }

    keys = decision_node_keys(report)

    assert keys == [
        {"key": "rsx-claim-1", "normalized_key": "EventType.DECISION:decide a"},
        {"key": "rsx-claim-2", "normalized_key": "EventType.DECISION:decide b"},
    ]


# ---------------------------------------------------------------------------
# τ-bench pass^k reliability
# ---------------------------------------------------------------------------


def test_pass_hat_k_true_when_every_trial_passes():
    runs = [_run("rsx-bundle", "pass") for _ in range(3)]
    assert compute_run_reliability(runs) == {"k": 3, "passes": 3, "pass_hat_k": True}


def test_pass_hat_k_false_on_one_failure_in_eight():
    """The tau-bench finding, verbatim: 7 of 8 trials is a failing bundle."""
    runs = [_run("rsx-bundle", "pass") for _ in range(7)] + [_run("rsx-bundle", "fail")]
    assert compute_run_reliability(runs) == {"k": 8, "passes": 7, "pass_hat_k": False}


def test_pass_hat_k_empty_corpus_claims_nothing():
    assert compute_run_reliability([]) == {"k": 0, "passes": 0, "pass_hat_k": False}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_spectrum_is_deterministic_and_run_order_independent():
    runs = [
        _run("rsx-bundle", "fail", [_node("rsx-node-beta"), _node("rsx-node-alpha")]),
        _run("rsx-bundle", "pass", [_node("rsx-node-alpha")]),
        _run("rsx-bundle", "fail", [_node("rsx-node-beta")]),
    ]

    first = compute_run_spectrum(runs)
    second = compute_run_spectrum(list(reversed(runs)))

    assert first == second == compute_run_spectrum(runs)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert summarize_bundle_runs(runs) == summarize_bundle_runs(list(reversed(runs)))


# ---------------------------------------------------------------------------
# The bundle report over real runs (in-process bundle + engine double)
# ---------------------------------------------------------------------------


def test_bundle_report_over_real_runs_of_one_bundle():
    bundle, ids = _bundle()
    baseline_band = next(
        row["expected"]
        for row in bundle["expected_assertions"]
        if row["kind"] == ASSERTION_TRUST_BAND
    )
    tuned = run_bundle(bundle, engine=_BandTunedEngine(_other_band(baseline_band)))
    runs = [run_bundle(bundle), run_bundle(bundle), tuned]

    # The per-run recording: the decision node carries its event id, and the
    # real-engine runs are deterministic.
    for result in (runs[0], runs[1]):
        assert result["verdict"] == "pass"
        assert [node["key"] for node in result["decision_nodes"]] == [ids["decision"]]
    assert runs[0] == runs[1]
    assert tuned["verdict"] == "fail"
    assert [node["key"] for node in tuned["decision_nodes"]] == [ids["decision"]]

    report = summarize_bundle_runs(runs)

    assert report["bundle_report_version"] == BUNDLE_REPORT_VERSION
    assert report["bundle_hash"] == bundle["content_hash"]
    assert (report["runs"], report["passed_runs"], report["failed_runs"]) == (3, 2, 1)
    assert report["verdict"] == "fail"
    assert report["reliability"] == {"k": 3, "passes": 2, "pass_hat_k": False}
    # 1 failed run, decision present in all three: 1/sqrt(1*3) = 0.5774.
    assert report["spectrum"] == {
        "scenarios": 1,
        "runs": 3,
        "passed_runs": 2,
        "failed_runs": 1,
        "top_suspects": [
            {"key": ids["decision"], "suspiciousness": round(1 / math.sqrt(3), 4),
             "failed_hits": 1, "passed_hits": 2}
        ],
    }


def test_summarize_refuses_dicts_that_are_not_run_results():
    with pytest.raises(MalformedBundleError, match="runs\\[0\\] is not a run result"):
        summarize_bundle_runs([{"bundle_hash": "rsx-bundle"}])


# ---------------------------------------------------------------------------
# Additivity: the pre-existing report shapes are unchanged
# ---------------------------------------------------------------------------


def test_existing_report_keys_are_unchanged():
    bundle, _ = _bundle()
    result = run_bundle(bundle)

    # The run result gained exactly one key: the recorded decision nodes.
    assert set(result) == _PRE_SLICE_RUN_KEYS | {"decision_nodes"}
    # The comparison report keeps exactly its shape and still accepts the
    # extended run results.
    comparison = compare_run_results(result, result)
    assert set(comparison) == {
        "comparison_version",
        "baseline",
        "candidate",
        "bundle_hash",
        "engine_versions_match",
        "counts",
        "rows",
        "verdict",
    }
    assert comparison["verdict"] == "unchanged"

    # The bundle report: core keys plus exactly the two additive fields.
    report = summarize_bundle_runs([result])
    assert set(report) == {
        "bundle_report_version",
        "bundle_hash",
        "runs",
        "passed_runs",
        "failed_runs",
        "verdict",
        "spectrum",
        "reliability",
    }
