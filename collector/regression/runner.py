"""Local regression runner: replay an incident bundle through the current audit engine.

The runner never re-executes the agent or its tools — it is analysis only.
It rebuilds the captured events/checkpoints from the bundle, feeds them to
the *current* :class:`~collector.audit.SessionAuditEngine` (not the report
stored at export time), and evaluates the bundle's stored expected
assertions against that fresh report. Same bundle + same engine semantics →
same verdict, deterministically.

:func:`compare_run_results` then takes two run results that share the same
bundle (the W05 gate: candidate and baseline share data/evaluator versions)
and reports which assertions regressed, improved or stayed unchanged — the
"candidate vs baseline" view for a code change such as engine tuning.

:func:`summarize_bundle_runs` aggregates the many-runs view of one bundle —
the deterministic Tarantula/Ochiai suspiciousness spectrum
(:func:`compute_run_spectrum`) and the τ-bench pass^k reliability figure
(:func:`compute_run_reliability`) over already-recorded run verdicts. Both
are arithmetic over recorded output (no model calls, no re-runs), and the
spectrum only ever ranks decision-node candidates — never a verification
status, never an input to the trust score.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from agent_debugger_sdk.core.events import BASE_EVENT_FIELDS, Checkpoint, EventType, TraceEvent
from collector.audit import SessionAuditEngine

from .bundles import (
    ASSERTION_CLAIM_STATUS,
    ASSERTION_FAILURE_IDS,
    ASSERTION_NARRATIVE_MECHANISM,
    ASSERTION_SUMMARY_VERDICT,
    ASSERTION_TRUST_BAND,
    ASSERTION_TRUST_SCORE,
    AUDIT_ENGINE_VERSION,
    MalformedBundleError,
    decision_node_keys,
    parse_bundle,
)

#: Version of the run-result shape (also the compare input shape).
RUN_RESULT_VERSION = 1

#: Version of the bundle-run report shape (:func:`summarize_bundle_runs`).
BUNDLE_REPORT_VERSION = 1

#: Maximum number of entries in a spectrum's ``top_suspects`` list.
SPECTRUM_TOP_SUSPECTS_CAP = 10

#: Base event field names consumed explicitly when rebuilding an event; every
#: other key in the stored dict is event payload the typed class folds back.
_BASE_KEYS = tuple(sorted(BASE_EVENT_FIELDS - {"event_type", "timestamp", "data"}))


class ComparisonPreconditionError(MalformedBundleError):
    """The two run results cannot be compared (they come from different data)."""


# ---------------------------------------------------------------------------
# Bundle → captured objects
# ---------------------------------------------------------------------------


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _event_from_dict(raw: dict[str, Any]) -> TraceEvent:
    """Rebuild a TraceEvent from its stored dict (mirrors ``orm_to_event``).

    ``TraceEvent.to_dict()`` emits the base fields, the ``data`` payload dict,
    and any typed-event fields as sibling top-level keys. Base fields are
    consumed explicitly, and the payload is reassembled with the explicit
    ``data`` dict winning on conflict — the same fold the HTTP ingest path
    performs.
    """
    data = dict(raw)
    event_type = EventType(str(data.pop("event_type", "agent_start")))
    timestamp = _parse_timestamp(data.pop("timestamp", None))
    base_kwargs: dict[str, Any] = {key: data.pop(key) for key in _BASE_KEYS if key in data}
    payload = dict(data.pop("data", {}) or {})
    if timestamp is not None:
        base_kwargs["timestamp"] = timestamp
    return TraceEvent.from_data(event_type, base_kwargs, {**data, **payload})


def _checkpoint_from_dict(raw: dict[str, Any]) -> Checkpoint:
    data = dict(raw)
    timestamp = _parse_timestamp(data.pop("timestamp", None))
    if timestamp is not None:
        data["timestamp"] = timestamp
    return Checkpoint(**data)


def events_from_bundle(bundle: dict[str, Any]) -> list[TraceEvent]:
    """Rebuild the bundle's ordered event list."""
    return [_event_from_dict(raw) for raw in bundle.get("events", []) or []]


def checkpoints_from_bundle(bundle: dict[str, Any]) -> list[Checkpoint]:
    """Rebuild the bundle's ordered checkpoint list."""
    return [_checkpoint_from_dict(raw) for raw in bundle.get("checkpoints", []) or []]


# ---------------------------------------------------------------------------
# Assertion evaluation
# ---------------------------------------------------------------------------


def _actual_for_kind(assertion: dict[str, Any], report: dict[str, Any]) -> Any:
    kind = assertion.get("kind")
    if kind == ASSERTION_TRUST_BAND:
        return (report.get("trust") or {}).get("band")
    if kind == ASSERTION_TRUST_SCORE:
        return (report.get("trust") or {}).get("score")
    if kind == ASSERTION_CLAIM_STATUS:
        subject = assertion.get("subject")
        for claim in report.get("claims", []) or []:
            if str(claim.get("event_id") or "") == subject:
                return claim.get("verification_status")
        return None
    if kind == ASSERTION_FAILURE_IDS:
        return sorted(
            str(failure.get("event_id"))
            for failure in report.get("failures", []) or []
            if failure.get("event_id")
        )
    if kind == ASSERTION_NARRATIVE_MECHANISM:
        narrative = report.get("failure_narrative", {}) or {}
        return (narrative.get("symptom") or {}).get("mechanism_category")
    if kind == ASSERTION_SUMMARY_VERDICT:
        return (report.get("summary") or {}).get("verdict")
    raise MalformedBundleError(
        f"Unknown assertion kind {kind!r} at {assertion.get('path')!r}; this runner "
        f"supports kinds derived by schema-1 exporters."
    )


def evaluate_assertion(assertion: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one expected assertion against a fresh audit report."""
    expected = assertion.get("expected")
    actual = _actual_for_kind(assertion, report)
    row: dict[str, Any] = {
        "kind": assertion.get("kind"),
        "path": assertion.get("path"),
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
    }
    if assertion.get("subject") is not None:
        row["subject"] = assertion.get("subject")
    return row


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_bundle(
    bundle: dict[str, Any],
    *,
    engine: Any = None,
    engine_version: str | None = None,
) -> dict[str, Any]:
    """Replay a validated bundle through the current engine and evaluate its assertions.

    Args:
        bundle: A bundle dict; its schema version and content hash are
            verified first (tampered or unknown-version bundles raise).
        engine: Audit engine to replay with — any object exposing
            ``audit(events, checkpoints, session=...)``. Defaults to a fresh
            :class:`SessionAuditEngine`. Injecting a tuned double here is the
            seam a candidate comparison exercises.
        engine_version: Evaluator version to record for this run; defaults to
            this code's :data:`AUDIT_ENGINE_VERSION`.

    Returns:
        A run-result dict: verdict plus per-assertion rows with the actual vs
        expected values. Deterministic for a fixed bundle + engine. The
        additive ``decision_nodes`` field records the stable identity
        (:func:`~collector.regression.bundles.decision_node_keys`) of every
        decision node in the fresh report — the per-run evidence the
        Tarantula/Ochiai spectrum in :func:`compute_run_spectrum` counts; it
        ranks candidates only and never feeds the trust score.
    """
    bundle = parse_bundle(bundle)
    events = events_from_bundle(bundle)
    checkpoints = checkpoints_from_bundle(bundle)
    session_meta = dict(bundle.get("session", {}) or {})
    audit_session = {
        "id": session_meta.get("id"),
        "status": session_meta.get("status"),
        "agent_name": session_meta.get("agent_name"),
        "started_at": session_meta.get("started_at"),
        "ended_at": session_meta.get("ended_at"),
    }

    audit_engine = engine if engine is not None else SessionAuditEngine()
    report = audit_engine.audit(events, checkpoints, session=audit_session)

    rows = [
        evaluate_assertion(assertion, report)
        for assertion in bundle.get("expected_assertions", []) or []
    ]
    passed = sum(1 for row in rows if row["passed"])
    failed = len(rows) - passed
    return {
        "run_result_version": RUN_RESULT_VERSION,
        "session_id": session_meta.get("id") or report.get("session_id"),
        "bundle_hash": bundle.get("content_hash"),
        "sanitized": bool(bundle.get("sanitized", False)),
        "engine": {"audit_engine_version": engine_version or AUDIT_ENGINE_VERSION},
        "event_count": len(events),
        "verdict": "pass" if failed == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "total": len(rows),
        "assertions": rows,
        "decision_nodes": decision_node_keys(report),
    }


# ---------------------------------------------------------------------------
# Baseline / candidate comparison
# ---------------------------------------------------------------------------


def _run_identity(run: Any, label: str) -> dict[str, Any]:
    if not isinstance(run, dict) or "assertions" not in run or "bundle_hash" not in run:
        raise MalformedBundleError(
            f"{label} is not a run result: expected a dict from run_bundle() with "
            "'assertions' and 'bundle_hash'."
        )
    return {
        "session_id": run.get("session_id"),
        "bundle_hash": run.get("bundle_hash"),
        "engine_version": (run.get("engine") or {}).get("audit_engine_version"),
        "verdict": run.get("verdict"),
        "passed": run.get("passed"),
        "failed": run.get("failed"),
        "total": run.get("total"),
    }


def _row_status(baseline: dict[str, Any] | None, candidate: dict[str, Any] | None) -> str:
    if baseline is None:
        return "added"
    if candidate is None:
        return "removed"
    same_value = baseline.get("expected") == candidate.get("expected") and baseline.get(
        "actual"
    ) == candidate.get("actual")
    if same_value:
        return "unchanged"
    if baseline.get("passed") and not candidate.get("passed"):
        return "regressed"
    if not baseline.get("passed") and candidate.get("passed"):
        return "improved"
    return "changed"


_VERDICT_PRECEDENCE = ("regressed", "improved", "changed", "unchanged")


def compare_run_results(baseline: Any, candidate: Any) -> dict[str, Any]:
    """Compare a candidate run against a baseline run of the *same* bundle.

    Both inputs are run results from :func:`run_bundle`. Per the W05 gate the
    two runs must share data: a hash mismatch raises
    :class:`ComparisonPreconditionError` instead of producing a meaningless
    diff. The evaluator versions each run recorded are surfaced (and flagged
    when they differ) rather than silently ignored.

    Per-assertion statuses: ``regressed`` (pass → fail), ``improved``
    (fail → pass), ``changed`` (same pass state, different values),
    ``unchanged``, plus ``added`` / ``removed`` for assertion ids that exist
    on only one side (an engine change that stopped or started emitting a
    claim).
    """
    baseline_id = _run_identity(baseline, "baseline")
    candidate_id = _run_identity(candidate, "candidate")
    if baseline_id["bundle_hash"] != candidate_id["bundle_hash"]:
        raise ComparisonPreconditionError(
            "Refusing to compare runs from different incident bundles "
            f"(baseline {baseline_id['bundle_hash']!r} vs candidate "
            f"{candidate_id['bundle_hash']!r}): candidate and baseline must "
            "share the same data. Re-export one bundle from the same session."
        )

    baseline_rows = {str(row.get("path")): row for row in baseline.get("assertions", []) or []}
    candidate_rows = {str(row.get("path")): row for row in candidate.get("assertions", []) or []}

    counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for path in sorted(set(baseline_rows) | set(candidate_rows)):
        baseline_row = baseline_rows.get(path)
        candidate_row = candidate_rows.get(path)
        status = _row_status(baseline_row, candidate_row)
        counts[status] += 1
        row: dict[str, Any] = {
            "path": path,
            "kind": (baseline_row or candidate_row or {}).get("kind"),
            "status": status,
        }
        if baseline_row is not None:
            row["baseline"] = {
                "expected": baseline_row.get("expected"),
                "actual": baseline_row.get("actual"),
                "passed": baseline_row.get("passed"),
            }
        if candidate_row is not None:
            row["candidate"] = {
                "expected": candidate_row.get("expected"),
                "actual": candidate_row.get("actual"),
                "passed": candidate_row.get("passed"),
            }
        rows.append(row)

    verdict = "unchanged"
    for candidate_verdict in _VERDICT_PRECEDENCE:
        if counts.get(candidate_verdict):
            verdict = candidate_verdict
            break

    return {
        "comparison_version": 1,
        "baseline": baseline_id,
        "candidate": candidate_id,
        "bundle_hash": baseline_id["bundle_hash"],
        "engine_versions_match": baseline_id["engine_version"] == candidate_id["engine_version"],
        "counts": {
            status: counts.get(status, 0)
            for status in ("regressed", "improved", "changed", "unchanged", "added", "removed")
        },
        "rows": rows,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Spectrum + reliability (the bundle-run report)
# ---------------------------------------------------------------------------


def _run_passed(run: dict[str, Any]) -> bool:
    """The per-run verdict exactly as the runner recorded it (never re-derived)."""
    return run.get("verdict") == "pass"


def _claim_subjects(run: dict[str, Any]) -> set[str]:
    """Event ids of a run's claim assertions — the pre-``decision_nodes`` identity."""
    return {
        str(row.get("subject"))
        for row in run.get("assertions", []) or []
        if row.get("kind") == ASSERTION_CLAIM_STATUS and row.get("subject")
    }


def _run_node_keys(run: dict[str, Any], *, normalized: bool) -> set[str]:
    """The decision-node key set one run contributes to the spectrum.

    Runs recorded by :func:`run_bundle` carry ``decision_nodes`` rows with
    both identities from :func:`~collector.regression.bundles.decision_node_keys`.
    Runs recorded before that field existed (saved baseline run results)
    contribute the event ids of their claim assertions instead — the same
    primary identity — so an older corpus still counts.
    """
    nodes = run.get("decision_nodes") or []
    if not nodes:
        return _claim_subjects(run)
    field = "normalized_key" if normalized else "key"
    return {str(node.get(field)) for node in nodes if node.get(field)}


def _ochiai(failed_hits: int, passed_hits: int, total_failed: int) -> float:
    """Ochiai suspiciousness: failed_hits / sqrt(total_failed * (failed + passed hits)).

    The denominator is guarded to 0.0 on divide-by-zero (no failed run in the
    corpus, or the node appeared nowhere) so a node with no evidence scores
    nothing rather than raising.
    """
    denominator = math.sqrt(total_failed * (failed_hits + passed_hits))
    if denominator <= 0:
        return 0.0
    return failed_hits / denominator


def compute_run_spectrum(runs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Compute the Tarantula/Ochiai suspiciousness spectrum across a bundle's runs.

    A single session gives a causal chain; a bundle of many runs of the same
    scenario gives a spectrum (Tarantula note,
    ``docs/papers/tarantula-test-information-fault-localization.md``). Each
    run's verdict is the pass/fail the runner already recorded — it is read,
    never re-derived — and each run's decision nodes are the identities it
    recorded at run time. For every node key the function counts in how many
    passed and failed runs it appeared and scores it with Ochiai:
    ``failed(hit) / sqrt(total_failed * (failed(hit) + passed(hit)))``, the
    divide-by-zero case guarded to 0.0. A node that appears only in failed
    runs scores 1.0 and tops the ranking.

    Node identity: within runs of one bundle the decision's event id is
    stable (a bundle pins its events), so primary ``key`` values are used.
    When the corpus spans more than one bundle — repeated recordings of the
    same scenario mint fresh event ids per recording — ids differ across
    runs, and the ``normalized_key`` derivation
    (``"{event_type}:{headline}"``; see
    :func:`~collector.regression.bundles.decision_node_keys`) is used
    instead, so the same decision aggregates across recordings.

    Field shape (the additive ``spectrum`` field of
    :func:`summarize_bundle_runs`)::

        {"scenarios": n_or_null, "runs": total_runs, "passed_runs": p,
         "failed_runs": f, "top_suspects": [{"key", "suspiciousness"
         (4 decimal places), "failed_hits", "passed_hits"}, ...]}

    * ``scenarios`` — the number of distinct bundle hashes (recordings) the
      runs span, or ``None`` when any run carries no bundle hash and the
      corpus therefore cannot be counted reliably (treated as ungrouped).
    * ``top_suspects`` — sorted by suspiciousness descending then key
      ascending, capped at :data:`SPECTRUM_TOP_SUSPECTS_CAP` (10).

    Computed only when the corpus has BOTH a passed and a failed run — a
    corpus without both carries no ranking information. Otherwise the
    function returns ``None`` (documented choice: an absent spectrum rather
    than an empty one, so consumers never mistake "no evidence" for "no
    suspects").

    CAUTION (Tarantula note): SBFL ranks, it does not convict. A decision
    that correlates with failure may be a symptom, not the cause.
    Suspiciousness is an ordering heuristic over decision nodes, never a
    verification status, and must never feed the trust score.
    """
    run_list = list(runs or [])
    hashes = [run.get("bundle_hash") for run in run_list]
    known_hashes = sorted({value for value in hashes if value})
    scenarios: int | None = None
    if all(value is not None for value in hashes):
        scenarios = len(known_hashes)

    passed_runs = sum(1 for run in run_list if _run_passed(run))
    failed_runs = len(run_list) - passed_runs
    if passed_runs == 0 or failed_runs == 0:
        return None

    # Event ids are recording-specific the moment the corpus spans more than
    # one bundle: aggregate on the normalized type+headline identity instead.
    normalized = len(known_hashes) > 1
    hits: dict[str, dict[str, int]] = {}
    for run in run_list:
        bucket = "failed" if not _run_passed(run) else "passed"
        for node_key in _run_node_keys(run, normalized=normalized):
            row = hits.setdefault(node_key, {"failed": 0, "passed": 0})
            row[bucket] += 1

    suspects = [
        {
            "key": key,
            "suspiciousness": round(_ochiai(counts["failed"], counts["passed"], failed_runs), 4),
            "failed_hits": counts["failed"],
            "passed_hits": counts["passed"],
        }
        for key, counts in hits.items()
    ]
    suspects.sort(key=lambda row: (-row["suspiciousness"], row["key"]))
    return {
        "scenarios": scenarios,
        "runs": len(run_list),
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "top_suspects": suspects[:SPECTRUM_TOP_SUSPECTS_CAP],
    }


def compute_run_reliability(runs: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Compute the τ-bench pass^k reliability of a bundle's recorded runs.

    Worst-of-k gating over the *already recorded* runs of one scenario
    (τ-bench note, ``docs/papers/tau-bench-pass-k-reliability.md``): ``k`` is
    the number of trials, ``passes`` the count of runs whose recorded verdict
    is ``pass`` (read, never re-derived), and ``pass_hat_k`` is True only
    when every trial passed (``passes == k``) — a bundle that passes 7 of 8
    trials is a failing bundle under pass^8; the mean pass rate hides that
    failure, worst-of-k does not.

    Computed from already-recorded run results only: this slice is the
    metric, not re-run machinery (the ROADMAP W05 next experiment wires
    re-running scenarios k times into CI).

    An empty corpus reports ``{"k": 0, "passes": 0, "pass_hat_k": False}``:
    zero trials claim no reliability, and worst-of-k must not pass a gate
    vacuously on missing evidence.
    """
    run_list = list(runs or [])
    trials = len(run_list)
    passes = sum(1 for run in run_list if _run_passed(run))
    return {"k": trials, "passes": passes, "pass_hat_k": trials > 0 and passes == trials}


def summarize_bundle_runs(runs: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Aggregate one bundle's run results into the bundle report.

    The many-runs companion to the existing report shapes — the single-run
    result (:func:`run_bundle`) and the two-run comparison
    (:func:`compare_run_results`) are unchanged. Core keys:
    ``bundle_report_version``, ``bundle_hash`` (the single recording the runs
    replay, or ``None`` when they span several or none), ``runs``,
    ``passed_runs``, ``failed_runs`` and ``verdict`` (``pass`` / ``fail`` /
    ``empty`` — the worst-of-k view, not the mean). Additive paper-note keys:

    * ``spectrum`` — :func:`compute_run_spectrum` over all runs, or ``None``
      when the corpus has both no passed-and-failed mix to rank with.
    * ``reliability`` — :func:`compute_run_reliability`, the τ-bench pass^k
      figure ("reliability: pass^k" at a glance).

    Every run is validated like a compare input (:func:`compare_run_results`
    precondition), so a dict that is not a run result raises
    :class:`MalformedBundleError` instead of silently skewing the counts.
    Runs may span several recordings of the same scenario (several bundle
    hashes); the spectrum then aggregates on normalized node identity.

    CAUTION: the spectrum ranks first-bad-decision candidates; it is never a
    verification status and must never feed the trust score.
    """
    run_list = list(runs or [])
    for index, run in enumerate(run_list):
        _run_identity(run, f"runs[{index}]")
    hashes = sorted({run.get("bundle_hash") for run in run_list if run.get("bundle_hash")})
    passed_runs = sum(1 for run in run_list if _run_passed(run))
    failed_runs = len(run_list) - passed_runs
    return {
        "bundle_report_version": BUNDLE_REPORT_VERSION,
        "bundle_hash": hashes[0] if len(hashes) == 1 else None,
        "runs": len(run_list),
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "verdict": "empty" if not run_list else ("pass" if failed_runs == 0 else "fail"),
        "spectrum": compute_run_spectrum(run_list),
        "reliability": compute_run_reliability(run_list),
    }
