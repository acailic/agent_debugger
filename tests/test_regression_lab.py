"""Tests for the incident-to-regression workflow (roadmap W05 / queue item Q14).

Covers the first slice of the regression laboratory: exporting a stored
session as a sanitized, content-hashed incident bundle whose expected
assertions pin the audit engine's verdict; replaying that bundle through the
current engine; and the baseline/candidate comparison that names exactly the
regressed assertions. Guards: unknown schema versions and tampered bundles
are rejected loudly, empty sessions round-trip, and the CLI entry points
carry the same contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, TraceEvent
from collector.audit import SessionAuditEngine
from collector.regression import (
    ASSERTION_CLAIM_STATUS,
    ASSERTION_FAILURE_IDS,
    ASSERTION_NARRATIVE_MECHANISM,
    ASSERTION_SUMMARY_VERDICT,
    ASSERTION_TRUST_BAND,
    ASSERTION_TRUST_SCORE,
    AUDIT_ENGINE_VERSION,
    BUNDLE_SCHEMA_VERSION,
    BundleTamperedError,
    ComparisonPreconditionError,
    UnsupportedBundleSchemaError,
    compare_run_results,
    content_hash,
    export_session_bundle,
    load_bundle,
    parse_bundle,
    run_bundle,
    save_bundle,
)
from redaction.pipeline import RedactionPipeline
from storage import TraceRepository

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLI = _REPO_ROOT / "scripts" / "regression_cli.py"

# Synthetic sentinel markers (same pattern as tests/test_redaction_boundary.py).
# The secret must be >= 20 chars so the generic_api_key pattern matches it.
MARKER_EMAIL = "reglab.user+tag@example.org"
MARKER_API_KEY = "api_key=REGRESSIONLABSECRET42"
ALL_MARKERS = (MARKER_EMAIL, MARKER_API_KEY)

_BASE_TS = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


def _uid(prefix: str) -> str:
    """Unique id per seeding (event ids are a global primary key in tests)."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str,
    *,
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


async def _seed_incident(maker, *, with_sentinels: bool = False) -> dict[str, str]:
    """Seed one auditable incident session; return its ids.

    Shape: an objective, a tool call + successful result, a decision citing
    that result (a verified claim), and a later failing tool result outside
    the decision's subtree (a localized failure + narrative mechanism), plus
    one checkpoint anchored on the successful result.
    """
    session_id = _uid("reglab-session")
    suffix = uuid.uuid4().hex[:6]
    ids = {
        name: _uid(f"reglab-{name}")
        for name in ("start", "call", "result", "decision", "failure")
    }
    contact = MARKER_EMAIL if with_sentinels else "user@example.com"
    config: dict = {"contact": contact}
    checkpoint_state: dict = {"stage": 1}
    if with_sentinels:
        config["credentials"] = MARKER_API_KEY
        checkpoint_state["credentials"] = MARKER_API_KEY

    async with maker() as db:
        repo = TraceRepository(db, tenant_id="local")
        await repo.create_session(
            Session(
                id=session_id,
                agent_name="regression-agent",
                framework="pytest",
                tags=["reglab"],
                config=config,
            )
        )
        events = [
            _event(
                ids["start"],
                EventType.AGENT_START,
                session_id,
                timestamp=_BASE_TS,
                content=f"Summarize the quarter revenue report {suffix}",
                metadata={"contact": contact},
            ),
            _event(
                ids["call"],
                EventType.TOOL_CALL,
                session_id,
                timestamp=_BASE_TS.replace(minute=1),
                tool_name="search",
            ),
            _event(
                ids["result"],
                EventType.TOOL_RESULT,
                session_id,
                parent_id=ids["call"],
                timestamp=_BASE_TS.replace(minute=2),
                tool_name="search",
                result={"rows": 3},
            ),
            _event(
                ids["decision"],
                EventType.DECISION,
                session_id,
                timestamp=_BASE_TS.replace(minute=3),
                confidence=0.9,
                chosen_action="answer",
                reasoning=f"grounded in the search results for report {suffix}",
                evidence_event_ids=[ids["result"]],
            ),
            # Failing tool result outside the decision's causal subtree: the
            # decision stays verified while the session still localizes a
            # failure with a narrative mechanism.
            _event(
                ids["failure"],
                EventType.TOOL_RESULT,
                session_id,
                upstream_event_ids=[ids["call"]],
                timestamp=_BASE_TS.replace(minute=4),
                tool_name="deploy",
                error="connection reset by peer",
            ),
        ]
        await repo.add_events_batch(events)
        await repo.create_checkpoint(
            Checkpoint(
                id=_uid("reglab-checkpoint"),
                session_id=session_id,
                event_id=ids["result"],
                sequence=1,
                state=checkpoint_state,
                memory={"last_tool": "search"},
                timestamp=_BASE_TS.replace(minute=2),
                importance=0.8,
            )
        )
        await db.commit()
    return {"session_id": session_id, **ids}


async def _export(maker, session_id: str, **kwargs) -> dict:
    """Export through a fresh repository session (read-only use of storage)."""
    async with maker() as db:
        repo = TraceRepository(db, tenant_id="local")
        return await export_session_bundle(repo, session_id, **kwargs)


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
# Export: schema, determinism, sanitization
# ---------------------------------------------------------------------------


async def test_export_is_versioned_and_deterministic(db_session_maker, tmp_path):
    seeded = await _seed_incident(db_session_maker)

    bundle_a = await _export(db_session_maker, seeded["session_id"])
    bundle_b = await _export(db_session_maker, seeded["session_id"])

    assert bundle_a["schema_version"] == BUNDLE_SCHEMA_VERSION == 1
    assert bundle_a["bundle_kind"] == "agent_debugger.incident_bundle"
    # Determinism: two exports of the same stored session hash identically
    # and render byte-identical on disk.
    assert bundle_a["content_hash"] == bundle_b["content_hash"]
    path_a = save_bundle(bundle_a, tmp_path / "a.json")
    path_b = save_bundle(bundle_b, tmp_path / "b.json")
    assert path_a.read_bytes() == path_b.read_bytes()

    assert bundle_a["session"]["id"] == seeded["session_id"]
    assert bundle_a["session"]["agent_name"] == "regression-agent"
    assert bundle_a["session"]["tags"] == ["reglab"]
    assert bundle_a["event_count"] == 5
    assert bundle_a["checkpoint_count"] == 1
    # Deterministic ordering: events by (timestamp, id).
    timestamps = [event["timestamp"] for event in bundle_a["events"]]
    assert timestamps == sorted(timestamps)
    assert [event["id"] for event in bundle_a["events"]] == [
        seeded["start"],
        seeded["call"],
        seeded["result"],
        seeded["decision"],
        seeded["failure"],
    ]

    # Sanitized is the default, with the applied policy recorded.
    assert bundle_a["sanitized"] is True
    assert set(bundle_a["redaction"]) == {
        "redact_prompts",
        "redact_tool_payloads",
        "redact_pii",
        "max_payload_kb",
    }

    # Audit report + derived expected assertions.
    assert bundle_a["audit_report"]["session_id"] == seeded["session_id"]
    kinds = {assertion["kind"] for assertion in bundle_a["expected_assertions"]}
    assert kinds == {
        ASSERTION_TRUST_BAND,
        ASSERTION_TRUST_SCORE,
        ASSERTION_CLAIM_STATUS,
        ASSERTION_FAILURE_IDS,
        ASSERTION_NARRATIVE_MECHANISM,
        ASSERTION_SUMMARY_VERDICT,
    }
    claim_rows = [
        assertion
        for assertion in bundle_a["expected_assertions"]
        if assertion["kind"] == ASSERTION_CLAIM_STATUS
    ]
    assert len(claim_rows) == 1
    assert claim_rows[0]["subject"] == seeded["decision"]
    assert claim_rows[0]["expected"] == "verified"


async def test_export_sanitizes_sentinels_and_keeps_raw_available(db_session_maker):
    seeded = await _seed_incident(db_session_maker, with_sentinels=True)
    pipeline = RedactionPipeline(
        redact_prompts=True, redact_tool_payloads=True, redact_pii=True
    )

    bundle = await _export(
        db_session_maker, seeded["session_id"], redaction_pipeline=pipeline
    )

    assert bundle["sanitized"] is True
    assert bundle["redaction"] == {
        "redact_prompts": True,
        "redact_tool_payloads": True,
        "redact_pii": True,
        "max_payload_kb": 0,
    }
    text = json.dumps(bundle)
    for marker in ALL_MARKERS:
        assert marker not in text, f"{marker} leaked into the sanitized bundle"

    # The sanitized bundle still runs clean: assertions derived from the
    # sanitized events are reproducible on the sanitized events.
    assert run_bundle(bundle)["verdict"] == "pass"

    raw = await _export(db_session_maker, seeded["session_id"], sanitized=False)
    assert raw["sanitized"] is False
    assert raw["redaction"] is None
    raw_text = json.dumps(raw)
    for marker in ALL_MARKERS:
        assert marker in raw_text


async def test_export_missing_session_raises_loudly(db_session_maker):
    with pytest.raises(Exception, match="not found"):
        await _export(db_session_maker, _uid("reglab-missing"))


# ---------------------------------------------------------------------------
# Run: determinism + assertion evaluation
# ---------------------------------------------------------------------------


async def test_run_bundle_passes_and_is_deterministic(db_session_maker, tmp_path):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    result = run_bundle(bundle)

    assert result["session_id"] == seeded["session_id"]
    assert result["bundle_hash"] == bundle["content_hash"]
    assert result["engine"]["audit_engine_version"] == AUDIT_ENGINE_VERSION
    assert result["event_count"] == 5
    assert result["verdict"] == "pass"
    assert result["total"] == len(bundle["expected_assertions"])
    assert result["failed"] == 0
    for row in result["assertions"]:
        assert row["passed"] is True
        assert row["actual"] == row["expected"]

    # Same bundle + same engine -> same verdict, including via a file hop.
    reloaded = load_bundle(save_bundle(bundle, tmp_path / "incident.json"))
    assert run_bundle(reloaded) == result


# ---------------------------------------------------------------------------
# Compare: candidate vs baseline
# ---------------------------------------------------------------------------


async def test_compare_reports_exactly_the_regressed_assertion(db_session_maker):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    baseline = run_bundle(bundle)
    baseline_band = next(
        row["expected"] for row in baseline["assertions"] if row["path"] == "trust.band"
    )
    candidate = run_bundle(bundle, engine=_BandTunedEngine(_other_band(baseline_band)))

    comparison = compare_run_results(baseline, candidate)

    assert comparison["verdict"] == "regressed"
    assert comparison["bundle_hash"] == bundle["content_hash"]
    assert comparison["engine_versions_match"] is True
    assert comparison["counts"] == {
        "regressed": 1,
        "improved": 0,
        "changed": 0,
        "unchanged": baseline["total"] - 1,
        "added": 0,
        "removed": 0,
    }
    regressed = [row for row in comparison["rows"] if row["status"] == "regressed"]
    assert [row["path"] for row in regressed] == ["trust.band"]
    assert regressed[0]["baseline"]["actual"] == baseline_band
    assert regressed[0]["candidate"]["actual"] == _other_band(baseline_band)

    # A candidate identical to the baseline changes nothing.
    identical = compare_run_results(baseline, baseline)
    assert identical["verdict"] == "unchanged"
    assert identical["counts"]["unchanged"] == baseline["total"]


async def test_compare_surfaces_mismatched_engine_versions(db_session_maker):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    baseline = run_bundle(bundle)
    candidate = run_bundle(bundle, engine_version="1-candidate-tuning")

    comparison = compare_run_results(baseline, candidate)
    assert comparison["engine_versions_match"] is False
    assert comparison["verdict"] == "unchanged"


async def test_compare_refuses_runs_from_different_bundles(db_session_maker):
    first = await _seed_incident(db_session_maker)
    second = await _seed_incident(db_session_maker)
    baseline = run_bundle(await _export(db_session_maker, first["session_id"]))
    candidate = run_bundle(await _export(db_session_maker, second["session_id"]))

    with pytest.raises(ComparisonPreconditionError, match="share the same data"):
        compare_run_results(baseline, candidate)


# ---------------------------------------------------------------------------
# Guards: schema version + tampering
# ---------------------------------------------------------------------------


async def test_unknown_schema_version_is_rejected_loudly(db_session_maker, tmp_path):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    future = dict(bundle)
    future["schema_version"] = BUNDLE_SCHEMA_VERSION + 1

    with pytest.raises(UnsupportedBundleSchemaError) as excinfo:
        parse_bundle(future)
    assert str(BUNDLE_SCHEMA_VERSION) in str(excinfo.value)
    assert str(BUNDLE_SCHEMA_VERSION + 1) in str(excinfo.value)

    path = save_bundle(future, tmp_path / "future.json")
    with pytest.raises(UnsupportedBundleSchemaError):
        load_bundle(path)
    with pytest.raises(UnsupportedBundleSchemaError):
        run_bundle(future)


async def test_tampered_bundle_is_rejected(db_session_maker, tmp_path):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    tampered = json.loads(json.dumps(bundle))
    tampered["events"][0]["name"] = "edited-after-export"

    with pytest.raises(BundleTamperedError, match="hash mismatch"):
        parse_bundle(tampered)
    path = save_bundle(tampered, tmp_path / "tampered.json")
    with pytest.raises(BundleTamperedError):
        load_bundle(path)
    with pytest.raises(BundleTamperedError):
        run_bundle(tampered)


async def test_edited_assertion_set_must_be_resigned_and_fails_exactly_itself(
    db_session_maker,
):
    """An operator-edited expectation (reviewed + re-signed) pins the diff.

    Mutating one stored assertion without re-signing is tampering (rejected
    above); re-signing it via ``content_hash`` is the reviewed edit path — and
    the run then fails on exactly that assertion.
    """
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])

    edited = json.loads(json.dumps(bundle))
    target = next(
        assertion
        for assertion in edited["expected_assertions"]
        if assertion["kind"] == ASSERTION_TRUST_BAND
    )
    original_expected = target["expected"]
    target["expected"] = _other_band(original_expected)
    edited["content_hash"] = content_hash(edited)

    result = run_bundle(edited)

    assert result["verdict"] == "fail"
    assert result["failed"] == 1
    failed_rows = [row for row in result["assertions"] if not row["passed"]]
    assert [row["path"] for row in failed_rows] == ["trust.band"]
    assert failed_rows[0]["expected"] == _other_band(original_expected)
    assert failed_rows[0]["actual"] == original_expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_empty_session_bundle_round_trips(db_session_maker, tmp_path):
    session_id = _uid("reglab-empty")
    async with db_session_maker() as db:
        repo = TraceRepository(db, tenant_id="local")
        await repo.create_session(
            Session(id=session_id, agent_name="regression-agent", framework="pytest")
        )
        await db.commit()

    bundle = await _export(db_session_maker, session_id)

    assert bundle["event_count"] == 0
    assert bundle["events"] == []
    assert bundle["checkpoints"] == []
    # Scalar pins still exist and still evaluate — an empty incident is a
    # valid regression case.
    kinds = {assertion["kind"] for assertion in bundle["expected_assertions"]}
    assert ASSERTION_TRUST_BAND in kinds
    assert ASSERTION_SUMMARY_VERDICT in kinds

    result = run_bundle(load_bundle(save_bundle(bundle, tmp_path / "empty.json")))
    assert result["verdict"] == "pass"
    assert result["total"] == len(bundle["expected_assertions"])


# ---------------------------------------------------------------------------
# CLI contract (subprocess, like tests/test_benchmark_who_when_cli.py)
# ---------------------------------------------------------------------------


async def test_cli_run_and_compare(tmp_path, db_session_maker):
    seeded = await _seed_incident(db_session_maker)
    bundle = await _export(db_session_maker, seeded["session_id"])
    bundle_path = save_bundle(bundle, tmp_path / "incident.json")
    baseline_path = tmp_path / "baseline.json"

    run = subprocess.run(
        [sys.executable, str(_CLI), "run", "--bundle", str(bundle_path), "--out", str(baseline_path)],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PASS" in run.stdout
    assert json.loads(baseline_path.read_text())["verdict"] == "pass"

    baseline = run_bundle(bundle)
    baseline_band = next(
        row["expected"] for row in baseline["assertions"] if row["path"] == "trust.band"
    )
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(
            run_bundle(bundle, engine=_BandTunedEngine(_other_band(baseline_band))),
            indent=2, sort_keys=True, default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    compare = subprocess.run(
        [
            sys.executable, str(_CLI), "compare",
            "--baseline", str(baseline_path),
            "--candidate", str(candidate_path),
        ],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
    )
    assert compare.returncode == 1, compare.stdout + compare.stderr
    assert "REGRESSED" in compare.stdout
    assert "trust.band" in compare.stdout

    identical = subprocess.run(
        [
            sys.executable, str(_CLI), "compare",
            "--baseline", str(baseline_path),
            "--candidate", str(baseline_path),
        ],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
    )
    assert identical.returncode == 0, identical.stdout + identical.stderr
    assert "UNCHANGED" in identical.stdout


def test_cli_tampered_bundle_exits_operational_error(tmp_path):
    result = subprocess.run(
        [sys.executable, str(_CLI), "run", "--bundle", str(tmp_path / "missing.json")],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stderr
