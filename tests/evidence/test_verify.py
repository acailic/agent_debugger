"""Offline verifier detection matrix (docs/plans/agent-evidence-box.md, pilot criteria).

Fixtures are built programmatically from the shared contract only:
``InMemoryEvidenceSink`` + ``EvidenceSigner`` produce the signed chain,
plain file IO writes the documented package layout, and every tamper
is applied to a fresh copy of a valid package in ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence.contracts import InMemoryEvidenceSink
from evidence.schema import (
    EventDraft,
    EventType,
    FinalCheckpoint,
    OutcomeSummary,
    PackageManifest,
    SignedEventRecord,
    checkpoint_body_bytes,
    manifest_bytes,
    utc_now,
)
from evidence.signing import EvidenceSigner
from evidence.verify import KeyRegistry, verify_package

GW_ID = "gw-test"
EXEC_ID = "exec-1"
UNKNOWN_KEY_ID = "ed25519:0000000000000000"


# ---------------------------------------------------------------------------
# Programmatic fixture builders
# ---------------------------------------------------------------------------


def _decision_payload(call_id: str) -> dict:
    return {
        "decision": "allow",
        "reason": "policy allows claims.update for svc-claims",
        "call_id": call_id,
        "principal": "svc-claims",
        "identity_source": "declared",
        "policy_version": "pv-1",
        "tool_name": "claims.update",
        "input_schema_hash": "ab" * 32,
        "config_version": "cv-1",
    }


def _outcome_payload(call_id: str, status: str) -> dict:
    return {"call_id": call_id, "status": status, "outcome_code": "updated", "duration_ms": 12}


def build_records(gateway_signer: EvidenceSigner):
    """Five-event chain: start, 2 decisions, 2 outcomes (1 unknown)."""
    sink = InMemoryEvidenceSink(gateway_signer, gateway_id=GW_ID)
    sink.append(
        EventDraft(
            type=EventType.EXECUTION_STARTED,
            execution_id=EXEC_ID,
            recorded_at=utc_now(),
            payload={"principal": "svc-claims", "policy_version": "pv-1"},
        )
    )
    sink.append(
        EventDraft(
            type=EventType.DECISION_RECORDED,
            execution_id=EXEC_ID,
            recorded_at=utc_now(),
            payload=_decision_payload("call-1"),
        )
    )
    sink.append(
        EventDraft(
            type=EventType.OUTCOME_RECORDED,
            execution_id=EXEC_ID,
            recorded_at=utc_now(),
            payload=_outcome_payload("call-1", "success"),
        )
    )
    sink.append(
        EventDraft(
            type=EventType.DECISION_RECORDED,
            execution_id=EXEC_ID,
            recorded_at=utc_now(),
            payload=_decision_payload("call-2"),
        )
    )
    sink.append(
        EventDraft(
            type=EventType.OUTCOME_RECORDED,
            execution_id=EXEC_ID,
            recorded_at=utc_now(),
            payload=_outcome_payload("call-2", "unknown"),
        )
    )
    return sink.events(EXEC_ID)


def build_manifest(records, gateway_signer: EvidenceSigner) -> PackageManifest:
    return PackageManifest(
        gateway_id=GW_ID,
        execution_id=EXEC_ID,
        event_count=len(records),
        final_hash=records[-1].hash,
        key_id=gateway_signer.key_id,
        created_at=utc_now(),
    )


def build_checkpoint(manifest: PackageManifest, checkpoint_signer: EvidenceSigner) -> FinalCheckpoint:
    body = FinalCheckpoint(
        execution_id=manifest.execution_id,
        gateway_id=manifest.gateway_id,
        event_count=manifest.event_count,
        final_hash=manifest.final_hash,
        checkpoint_key_id=checkpoint_signer.key_id,
        recorded_at=utc_now(),
        signature="",
    )
    return body.model_copy(update={"signature": checkpoint_signer.sign(checkpoint_body_bytes(body))})


def write_package(directory: Path, records, manifest: PackageManifest, gateway_signer: EvidenceSigner) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (directory / "events.ndjson").write_text(
        "".join(record.model_dump_json() + "\n" for record in records), encoding="utf-8"
    )
    (directory / "signature").write_text(gateway_signer.sign(manifest_bytes(manifest)), encoding="utf-8")
    return directory


def registry_entry(signer: EvidenceSigner, role: str = "gateway", status: str = "active") -> dict:
    return {
        "key_id": signer.key_id,
        "public_key_pem": signer.public_pem().decode("ascii"),
        "status": status,
        "valid_from": utc_now().isoformat(),
        "valid_to": None,
        "role": role,
    }


def read_ndjson(package: Path) -> list[str]:
    return (package / "events.ndjson").read_text(encoding="utf-8").splitlines()


def write_ndjson(package: Path, lines: list[str]) -> None:
    (package / "events.ndjson").write_text("\n".join(lines) + "\n", encoding="utf-8")


def finding_kinds(result) -> set[str]:
    return {finding.kind for finding in result.integrity.findings}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gateway_signer() -> EvidenceSigner:
    return EvidenceSigner.generate()


@pytest.fixture(scope="module")
def checkpoint_signer() -> EvidenceSigner:
    return EvidenceSigner.generate()


@pytest.fixture(scope="module")
def parts(gateway_signer, checkpoint_signer):
    records = build_records(gateway_signer)
    manifest = build_manifest(records, gateway_signer)
    checkpoint = build_checkpoint(manifest, checkpoint_signer)
    return records, manifest, checkpoint


@pytest.fixture()
def valid_package(tmp_path, parts, gateway_signer) -> Path:
    records, manifest, _ = parts
    return write_package(tmp_path / "pkg", records, manifest, gateway_signer)


@pytest.fixture()
def registry(gateway_signer, checkpoint_signer) -> KeyRegistry:
    return KeyRegistry.from_dict(
        {"keys": [registry_entry(gateway_signer, "gateway"), registry_entry(checkpoint_signer, "checkpoint")]}
    )


@pytest.fixture()
def checkpoint(parts) -> FinalCheckpoint:
    return parts[2]


# ---------------------------------------------------------------------------
# KeyRegistry
# ---------------------------------------------------------------------------


class TestKeyRegistry:
    def test_load_from_json_file_and_lookup(self, tmp_path, gateway_signer):
        path = tmp_path / "registry.json"
        path.write_text(json.dumps({"keys": [registry_entry(gateway_signer)]}), encoding="utf-8")
        registry = KeyRegistry.load(path)
        assert registry.is_known(gateway_signer.key_id)
        assert registry.pem_for(gateway_signer.key_id) == gateway_signer.public_pem().decode("ascii")

    def test_unknown_key_is_none_not_exception(self, registry):
        assert registry.pem_for(UNKNOWN_KEY_ID) is None
        assert not registry.is_known(UNKNOWN_KEY_ID)

    def test_known_key_ids_sorted(self, gateway_signer, checkpoint_signer):
        registry = KeyRegistry.from_dict(
            {"keys": [registry_entry(checkpoint_signer), registry_entry(gateway_signer)]}
        )
        assert registry.known_key_ids() == sorted([gateway_signer.key_id, checkpoint_signer.key_id])

    def test_missing_keys_list_rejected(self):
        with pytest.raises(ValueError):
            KeyRegistry.from_dict({"certificates": []})

    def test_duplicate_key_id_rejected(self, gateway_signer):
        with pytest.raises(ValueError, match="duplicate"):
            KeyRegistry.from_dict({"keys": [registry_entry(gateway_signer), registry_entry(gateway_signer)]})

    def test_non_ed25519_pem_rejected(self):
        entry = {"key_id": "k", "public_key_pem": "not a pem", "status": "active", "role": "any"}
        with pytest.raises(ValueError):
            KeyRegistry.from_dict({"keys": [entry]})


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


class TestValidPackage:
    def test_valid_package_with_checkpoint_and_expected_executions_passes(
        self, valid_package, registry, checkpoint
    ):
        result = verify_package(valid_package, registry, checkpoint, [EXEC_ID])
        assert result.ok is True
        assert result.integrity.ok is True
        assert result.integrity.findings == []
        assert result.coverage.complete is True
        assert result.coverage.missing_final_checkpoint is False
        assert result.execution_id == EXEC_ID
        assert result.integrity.verified_events == 5
        assert result.integrity.verified_key_ids == sorted(registry.known_key_ids())

    def test_valid_package_without_expected_executions_still_completes(self, valid_package, registry, checkpoint):
        result = verify_package(valid_package, registry, checkpoint)
        assert result.ok is True
        assert result.coverage.complete is True

    def test_retired_gateway_key_still_verifies_historical_package(
        self, tmp_path, parts, gateway_signer, checkpoint_signer, checkpoint
    ):
        records, manifest, _ = parts
        package = write_package(tmp_path / "pkg", records, manifest, gateway_signer)
        rotated = KeyRegistry.from_dict(
            {
                "keys": [
                    registry_entry(gateway_signer, role="gateway", status="retired"),
                    registry_entry(checkpoint_signer, role="checkpoint", status="retired"),
                ]
            }
        )
        result = verify_package(package, rotated, checkpoint)
        assert result.ok is True
        assert result.integrity.ok is True


# ---------------------------------------------------------------------------
# Event tampering
# ---------------------------------------------------------------------------


class TestEventTampering:
    def test_modified_event_payload_detected_as_hash_mismatch(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        record = SignedEventRecord.model_validate_json(lines[1])
        record.event.payload["reason"] = "tampered after export"
        lines[1] = record.model_dump_json()
        write_ndjson(valid_package, lines)

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "event_hash_mismatch" in kinds
        assert result.integrity.ok is False
        assert result.ok is False

    def test_inserted_duplicate_line_detected(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        lines.insert(3, lines[2])  # extra copy of the first outcome event
        write_ndjson(valid_package, lines)

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "seq_duplicate" in kinds
        assert result.integrity.ok is False

    def test_reordered_lines_break_the_chain(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        lines[1], lines[2] = lines[2], lines[1]  # swap decision and outcome
        write_ndjson(valid_package, lines)

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "chain_broken" in kinds
        assert "seq_duplicate" not in kinds
        assert "seq_gap" not in kinds

    def test_deleted_middle_line_leads_to_seq_gap_and_broken_chain(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        del lines[2]  # remove seq 3
        write_ndjson(valid_package, lines)

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "seq_gap" in kinds
        assert "chain_broken" in kinds
        seq_gap = next(f for f in result.integrity.findings if f.kind == "seq_gap")
        assert "3" in seq_gap.detail

    def test_truncated_tail_keeps_chain_but_fails_manifest_totals(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        write_ndjson(valid_package, lines[:-1])  # drop the last event, fix nothing

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "count_mismatch" in kinds
        assert "final_hash_mismatch" in kinds
        assert "chain_broken" not in kinds
        assert "seq_gap" not in kinds

    def test_malformed_ndjson_line_reported_with_line_number(self, valid_package, registry, checkpoint):
        lines = read_ndjson(valid_package)
        lines[2] = "{definitely not json"
        write_ndjson(valid_package, lines)

        result = verify_package(valid_package, registry, checkpoint)
        findings = [f for f in result.integrity.findings if f.kind == "event_malformed"]
        assert len(findings) == 1
        assert "line 3" in findings[0].detail

    def test_missing_events_file_reported(self, valid_package, registry, checkpoint):
        (valid_package / "events.ndjson").unlink()

        result = verify_package(valid_package, registry, checkpoint)
        assert "event_malformed" in finding_kinds(result)
        assert result.integrity.ok is False

    def test_unknown_event_key_id_is_a_failure_not_an_exception(self, valid_package, checkpoint_signer, checkpoint):
        registry_without_gateway = KeyRegistry.from_dict({"keys": [registry_entry(checkpoint_signer, "checkpoint")]})

        result = verify_package(valid_package, registry_without_gateway, checkpoint)
        kinds = finding_kinds(result)
        assert "unknown_key" in kinds
        assert result.integrity.ok is False
        assert result.ok is False

    def test_execution_mismatch_when_event_swapped_into_other_execution(
        self, tmp_path, gateway_signer, registry, checkpoint
    ):
        records = build_records(gateway_signer)
        stranger = InMemoryEvidenceSink(gateway_signer, gateway_id=GW_ID).append(
            EventDraft(
                type=EventType.DECISION_RECORDED,
                execution_id="exec-other",
                recorded_at=utc_now(),
                payload=_decision_payload("call-9"),
            )
        )
        records = records[:2] + [stranger] + records[3:]
        manifest = build_manifest(records, gateway_signer)
        package = write_package(tmp_path / "pkg", records, manifest, gateway_signer)

        result = verify_package(package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "execution_mismatch" in kinds
        assert "chain_broken" in kinds  # the inserted event does not link


# ---------------------------------------------------------------------------
# Manifest tampering
# ---------------------------------------------------------------------------


class TestManifestTampering:
    def test_manifest_lie_without_resigning_fails_manifest_signature(self, valid_package, registry, checkpoint):
        manifest = PackageManifest.model_validate_json(
            (valid_package / "manifest.json").read_text(encoding="utf-8")
        )
        lied = manifest.model_copy(update={"event_count": 4})
        (valid_package / "manifest.json").write_text(lied.model_dump_json(indent=2), encoding="utf-8")

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "manifest_signature_invalid" in kinds
        assert result.integrity.ok is False

    def test_manifest_event_count_lie_resigned_with_right_key(self, valid_package, registry, gateway_signer):
        manifest = PackageManifest.model_validate_json(
            (valid_package / "manifest.json").read_text(encoding="utf-8")
        )
        lied = manifest.model_copy(update={"event_count": 4})
        (valid_package / "manifest.json").write_text(lied.model_dump_json(indent=2), encoding="utf-8")
        (valid_package / "signature").write_text(
            gateway_signer.sign(manifest_bytes(lied)), encoding="utf-8"
        )

        result = verify_package(valid_package, registry)  # no checkpoint: isolate the manifest-vs-events lie
        assert finding_kinds(result) == {"count_mismatch"}
        assert result.integrity.ok is False

    def test_manifest_final_hash_lie_resigned_with_right_key(self, valid_package, registry, checkpoint, gateway_signer):
        manifest = PackageManifest.model_validate_json(
            (valid_package / "manifest.json").read_text(encoding="utf-8")
        )
        lied = manifest.model_copy(update={"final_hash": "ff" * 32})
        (valid_package / "manifest.json").write_text(lied.model_dump_json(indent=2), encoding="utf-8")
        (valid_package / "signature").write_text(
            gateway_signer.sign(manifest_bytes(lied)), encoding="utf-8"
        )

        result = verify_package(valid_package, registry, checkpoint)
        assert finding_kinds(result) == {"final_hash_mismatch", "checkpoint_mismatch"}

    def test_manifest_key_id_unknown_to_registry(self, valid_package, registry, checkpoint, gateway_signer):
        manifest = PackageManifest.model_validate_json(
            (valid_package / "manifest.json").read_text(encoding="utf-8")
        )
        relabelled = manifest.model_copy(update={"key_id": UNKNOWN_KEY_ID})
        (valid_package / "manifest.json").write_text(relabelled.model_dump_json(indent=2), encoding="utf-8")
        (valid_package / "signature").write_text(
            gateway_signer.sign(manifest_bytes(relabelled)), encoding="utf-8"
        )

        result = verify_package(valid_package, registry, checkpoint)
        kinds = finding_kinds(result)
        assert "unknown_key" in kinds
        assert result.integrity.ok is False

    def test_malformed_manifest_reported(self, valid_package, registry, checkpoint):
        (valid_package / "manifest.json").write_text("{oops", encoding="utf-8")

        result = verify_package(valid_package, registry, checkpoint)
        assert "manifest_malformed" in finding_kinds(result)
        assert result.integrity.ok is False
        assert result.ok is False

    def test_signature_file_malformed_reported(self, valid_package, registry, checkpoint):
        (valid_package / "signature").write_text("zzzz-not-hex", encoding="utf-8")

        result = verify_package(valid_package, registry, checkpoint)
        assert "signature_file_malformed" in finding_kinds(result)
        assert result.integrity.ok is False

    def test_missing_package_directory_reported(self, tmp_path, registry):
        result = verify_package(tmp_path / "nope", registry)
        assert "manifest_malformed" in finding_kinds(result)
        assert result.ok is False


# ---------------------------------------------------------------------------
# Checkpoint — how truncation and omission are caught
# ---------------------------------------------------------------------------


class TestCheckpointVerification:
    def test_truncated_chain_with_fixed_manifest_caught_by_checkpoint(
        self, tmp_path, parts, gateway_signer, registry, checkpoint
    ):
        records, _, _ = parts
        shortened = records[:4]
        manifest = build_manifest(shortened, gateway_signer)  # consistent lie: count 4, final hash of event 4
        package = write_package(tmp_path / "pkg", shortened, manifest, gateway_signer)

        result = verify_package(package, registry, checkpoint)  # checkpoint pins 5 events / true final hash
        assert finding_kinds(result) == {"checkpoint_mismatch"}
        assert result.integrity.ok is False
        assert result.ok is False

    def test_checkpoint_count_edited_gives_checkpoint_mismatch(
        self, valid_package, registry, checkpoint, checkpoint_signer
    ):
        edited_body = checkpoint.model_copy(update={"event_count": checkpoint.event_count + 1, "signature": ""})
        edited = edited_body.model_copy(
            update={"signature": checkpoint_signer.sign(checkpoint_body_bytes(edited_body))}
        )
        result = verify_package(valid_package, registry, edited)
        assert finding_kinds(result) == {"checkpoint_mismatch"}
        assert "event_count" in result.integrity.findings[0].detail

    def test_checkpoint_bad_signature_detected(self, valid_package, registry, checkpoint):
        forged = checkpoint.model_copy(update={"signature": "00" * 64})
        result = verify_package(valid_package, registry, forged)
        assert finding_kinds(result) == {"checkpoint_signature_invalid"}

    def test_checkpoint_unknown_key_detected(self, valid_package, registry, checkpoint, checkpoint_signer):
        relabelled_body = checkpoint.model_copy(update={"checkpoint_key_id": UNKNOWN_KEY_ID, "signature": ""})
        relabelled = relabelled_body.model_copy(
            update={"signature": checkpoint_signer.sign(checkpoint_body_bytes(relabelled_body))}
        )
        result = verify_package(valid_package, registry, relabelled)
        assert finding_kinds(result) == {"unknown_key"}


class TestMissingCheckpoint:
    def test_missing_checkpoint_marks_incomplete_but_integrity_still_passes(self, valid_package, registry):
        result = verify_package(valid_package, registry, checkpoint=None)
        assert result.integrity.ok is True  # what is present is still verified
        assert result.integrity.findings == []
        assert result.coverage.missing_final_checkpoint is True
        assert result.coverage.complete is False
        assert result.ok is False
        assert "missing final checkpoint" in result.coverage.detail


# ---------------------------------------------------------------------------
# Coverage section
# ---------------------------------------------------------------------------


class TestCoverageVerdict:
    def test_unexpected_execution_fails_coverage(self, valid_package, registry, checkpoint):
        result = verify_package(valid_package, registry, checkpoint, ["exec-other"])
        assert result.integrity.ok is True
        assert result.coverage.complete is False
        assert result.ok is False
        assert "unexpected execution" in result.coverage.detail
        assert result.coverage.missing_executions == ["exec-other"]

    def test_expected_execution_matching_package_completes_coverage(self, valid_package, registry, checkpoint):
        result = verify_package(valid_package, registry, checkpoint, [EXEC_ID])
        assert result.coverage.complete is True
        assert result.coverage.missing_executions == []

    def test_multiple_expected_executions_do_not_fill_missing_list(self, valid_package, registry, checkpoint):
        result = verify_package(valid_package, registry, checkpoint, ["exec-a", "exec-b"])
        # this package covers neither expected id, but missing_executions only
        # applies when the caller pinned exactly one expected id
        assert result.coverage.complete is False
        assert result.coverage.missing_executions == []
        assert "unexpected execution" in result.coverage.detail


# ---------------------------------------------------------------------------
# Outcome knownness
# ---------------------------------------------------------------------------


class TestOutcomeSummary:
    def test_outcome_counts_and_unknown_call_ids(self, valid_package, registry, checkpoint):
        result = verify_package(valid_package, registry, checkpoint)
        assert result.outcomes.known == 1
        assert result.outcomes.unknown == 1
        assert result.outcomes.unknown_call_ids == ["call-2"]

    def test_all_known_outcomes(self, tmp_path, gateway_signer, registry, checkpoint_signer):
        sink = InMemoryEvidenceSink(gateway_signer, gateway_id=GW_ID)
        for call_id, status in (("call-1", "success"), ("call-2", "error"), ("call-3", "success")):
            sink.append(
                EventDraft(
                    type=EventType.DECISION_RECORDED,
                    execution_id=EXEC_ID,
                    recorded_at=utc_now(),
                    payload=_decision_payload(call_id),
                )
            )
            sink.append(
                EventDraft(
                    type=EventType.OUTCOME_RECORDED,
                    execution_id=EXEC_ID,
                    recorded_at=utc_now(),
                    payload=_outcome_payload(call_id, status),
                )
            )
        records = sink.events(EXEC_ID)
        manifest = build_manifest(records, gateway_signer)
        package = write_package(tmp_path / "pkg", records, manifest, gateway_signer)
        checkpoint = build_checkpoint(manifest, checkpoint_signer)

        result = verify_package(package, registry, checkpoint)
        assert result.ok is True
        assert result.outcomes == OutcomeSummary(known=3, unknown=0, unknown_call_ids=[])
