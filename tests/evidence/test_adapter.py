"""EvidenceTimelineAdapter tests — package parsing, mapping and redaction.

Packages are built by hand in ``tmp_path`` from the shared schema models
only (mirroring ``tests/evidence/test_schema.py`` construction); the
adapter never imports other evidence subsystems, and neither do these
tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidence.adapter import (
    EvidenceTimelineAdapter,
    PackageLoadError,
    flagged_package_summary,
)
from evidence.schema import (
    GENESIS_PREV_HASH,
    CoverageVerdict,
    DecisionKind,
    DecisionPayload,
    EventType,
    EvidenceEvent,
    IntegrityFinding,
    IntegrityVerdict,
    OutcomePayload,
    OutcomeStatus,
    PackageManifest,
    SignedEventRecord,
    VerificationResult,
    event_hash,
)

FIXED_AT = datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
GATEWAY_ID = "gw-test"
KEY_ID = "ed25519:deadbeefdeadbeef"
AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"


def _record(seq: int, event_type: EventType, payload: dict, prev_hash: str) -> SignedEventRecord:
    event = EvidenceEvent(
        type=event_type,
        execution_id="exec-1",
        seq=seq,
        prev_hash=prev_hash,
        gateway_id=GATEWAY_ID,
        key_id=KEY_ID,
        recorded_at=FIXED_AT,
        payload=payload,
    )
    return SignedEventRecord(event=event, hash=event_hash(event), signature="ff" * 64)


def _package_events() -> list[SignedEventRecord]:
    started = {"principal": "svc-claims", "policy_version": "pol-1", "run_id": "run-42"}
    allow = DecisionPayload(
        decision=DecisionKind.ALLOW,
        reason=f"policy pol-1 permits status update; credential {AWS_EXAMPLE_KEY} matched registry",
        call_id="call-1",
        principal="svc-claims",
        policy_version="pol-1",
        tool_name="update_claim_status",
        input_schema_hash="ab" * 32,
        config_version="cfg-1",
        run_id="run-42",
    )
    deny = DecisionPayload(
        decision=DecisionKind.DENY,
        reason="tool binding not approved for server identity",
        call_id="call-2",
        principal="svc-claims",
        policy_version="pol-1",
        tool_name="purge_database",
        input_schema_hash="cd" * 32,
        config_version="cfg-1",
        run_id="run-42",
    )
    done = OutcomePayload(call_id="call-1", status=OutcomeStatus.SUCCESS, outcome_code="updated")
    broken = OutcomePayload(call_id="call-2", status=OutcomeStatus.UNKNOWN)
    return [
        _record(1, EventType.EXECUTION_STARTED, started, GENESIS_PREV_HASH),
        _record(2, EventType.DECISION_RECORDED, allow.model_dump(mode="json"), ""),
        _record(3, EventType.OUTCOME_RECORDED, done.model_dump(mode="json"), ""),
        _record(4, EventType.DECISION_RECORDED, deny.model_dump(mode="json"), ""),
        _record(5, EventType.OUTCOME_RECORDED, broken.model_dump(mode="json"), ""),
    ]


def write_package(package_dir: Path, records: list[SignedEventRecord]) -> Path:
    """Write a minimal valid package: manifest.json + events.ndjson."""
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest = PackageManifest(
        gateway_id=GATEWAY_ID,
        execution_id="exec-1",
        event_count=len(records),
        final_hash=records[-1].hash if records else "0" * 64,
        key_id=KEY_ID,
        created_at=FIXED_AT,
    )
    (package_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    (package_dir / "events.ndjson").write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n", encoding="utf-8"
    )
    return package_dir


@pytest.fixture()
def package_dir(tmp_path: Path) -> Path:
    return write_package(tmp_path / "pkg-exec-1", _package_events())


@pytest.fixture()
def adapter() -> EvidenceTimelineAdapter:
    return EvidenceTimelineAdapter()


class TestLoadPackage:
    def test_maps_entries_with_line_refs(self, adapter, package_dir):
        summary = adapter.load_package(package_dir)

        assert summary.package_name == "pkg-exec-1"
        assert summary.execution_id == "exec-1"
        assert summary.manifest is not None
        assert summary.manifest.event_count == 5
        assert [entry.seq for entry in summary.entries] == [1, 2, 3, 4, 5]
        assert summary.error is None

        started, allow, done, deny, broken = summary.entries

        # Row-level linkage: run_id on the right rows, provenance everywhere.
        assert started.event_type == EventType.EXECUTION_STARTED
        assert started.run_id == "run-42"
        assert started.principal == "svc-claims"
        assert started.call_id is None

        assert allow.decision == "allow"
        assert allow.call_id == "call-1"
        assert allow.tool_name == "update_claim_status"
        assert allow.run_id == "run-42"

        assert done.outcome_status == OutcomeStatus.SUCCESS
        assert done.outcome_code == "updated"
        assert done.call_id == "call-1"

        assert deny.decision == "deny"
        assert deny.call_id == "call-2"

        assert broken.outcome_status == OutcomeStatus.UNKNOWN
        assert broken.call_id == "call-2"

        for entry in summary.entries:
            assert entry.gateway_id == GATEWAY_ID
            assert entry.key_id == KEY_ID
            assert entry.verified_source == f"evidence-gateway:{GATEWAY_ID}"

        # 1-based line numbers point back at the original signed records.
        assert [entry.original_ref for entry in summary.entries] == [
            f"pkg-exec-1#events.ndjson:L{i}" for i in range(1, 6)
        ]

    def test_redaction_masks_secret_in_decision_reason(self, adapter, package_dir):
        summary = adapter.load_package(package_dir)
        allow = summary.entries[1]

        assert AWS_EXAMPLE_KEY not in (allow.reason or "")
        assert "[AWS_ACCESS_KEY]" in (allow.reason or "")
        # Non-payload strings pass through untouched.
        assert allow.call_id == "call-1"
        assert allow.original_ref == "pkg-exec-1#events.ndjson:L2"

    def test_find_by_call_id_returns_decision_and_outcome(self, adapter, package_dir):
        summary = adapter.load_package(package_dir)
        rows = adapter.find_by_call_id(summary, "call-1")
        assert [row.seq for row in rows] == [2, 3]
        assert [row.event_type for row in rows] == [
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]
        assert adapter.find_by_call_id(summary, "call-missing") == []

    def test_malformed_ndjson_line_is_flagged_not_fatal(self, adapter, package_dir):
        with (package_dir / "events.ndjson").open("a", encoding="utf-8") as fh:
            fh.write("{not json at all}\n")

        summary = adapter.load_package(package_dir)

        assert len(summary.entries) == 5  # intact lines still map
        assert summary.error is not None
        assert "line 6" in summary.error

    def test_missing_manifest_raises_package_load_error(self, adapter, tmp_path):
        empty = tmp_path / "pkg-empty"
        empty.mkdir()
        with pytest.raises(PackageLoadError):
            adapter.load_package(empty)

    def test_flagged_summary_identifies_package(self, tmp_path):
        flagged = flagged_package_summary(tmp_path / "pkg-broken", "manifest.json not found")
        assert flagged.execution_id == "pkg-broken"
        assert flagged.integrity == "failed"
        assert flagged.error == "manifest.json not found"


class TestApplyVerification:
    def test_ok_result_marks_package_and_entries_verified(self, adapter, package_dir):
        summary = adapter.apply_verification(
            adapter.load_package(package_dir),
            VerificationResult(
                ok=True,
                package_path=str(package_dir),
                execution_id="exec-1",
                integrity=IntegrityVerdict(ok=True, verified_events=5, verified_key_ids=[KEY_ID]),
                coverage=CoverageVerdict(complete=True),
            ),
        )

        assert summary.integrity == "verified"
        assert summary.coverage == "complete"
        assert summary.verification is not None and summary.verification.ok
        assert {entry.integrity for entry in summary.entries} == {"verified"}
        assert {entry.coverage for entry in summary.entries} == {"complete"}

    def test_integrity_failure_marks_failed_with_entry_localization(self, adapter, package_dir):
        summary = adapter.apply_verification(
            adapter.load_package(package_dir),
            VerificationResult(
                ok=False,
                execution_id="exec-1",
                integrity=IntegrityVerdict(
                    ok=False,
                    verified_events=2,
                    findings=[IntegrityFinding(kind="hash_mismatch", detail="seq 3", seq=3)],
                ),
                coverage=CoverageVerdict(complete=False, missing_final_checkpoint=True),
            ),
        )

        assert summary.integrity == "failed"
        assert summary.coverage == "incomplete"
        by_seq = {entry.seq: entry.integrity for entry in summary.entries}
        assert by_seq == {1: "verified", 2: "verified", 3: "failed", 4: "failed", 5: "failed"}

    def test_no_verification_result_leaves_unverified(self, adapter, package_dir):
        summary = adapter.load_package(package_dir)

        assert summary.verification is None
        assert summary.integrity == "unverified"
        assert summary.coverage == "unknown"
        assert {entry.integrity for entry in summary.entries} == {"unverified"}
        assert {entry.coverage for entry in summary.entries} == {"unknown"}
