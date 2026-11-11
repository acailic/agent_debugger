"""End-to-end tests for the ``peaky-peek-evidence`` CLI (evidence.cli)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from evidence.cli import main
from evidence.contracts import InMemoryEvidenceSink
from evidence.schema import (
    EventDraft,
    EventType,
    FinalCheckpoint,
    PackageManifest,
    SignedEventRecord,
    checkpoint_body_bytes,
    manifest_bytes,
    utc_now,
)
from evidence.signing import EvidenceSigner, key_id_for_public_pem

GW_ID = "gw-cli"
EXEC_ID = "exec-cli"


# ---------------------------------------------------------------------------
# Programmatic fixture builders (same recipe as test_verify.py)
# ---------------------------------------------------------------------------


def _decision_payload(call_id: str) -> dict:
    return {
        "decision": "allow",
        "reason": "policy allows claims.update",
        "call_id": call_id,
        "principal": "svc-claims",
        "identity_source": "declared",
        "policy_version": "pv-1",
        "tool_name": "claims.update",
        "input_schema_hash": "ab" * 32,
        "config_version": "cv-1",
    }


def _outcome_payload(call_id: str, status: str) -> dict:
    return {"call_id": call_id, "status": status, "duration_ms": 10}


def build_records(gateway_signer: EvidenceSigner):
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


def registry_entry(signer: EvidenceSigner, role: str = "gateway") -> dict:
    return {
        "key_id": signer.key_id,
        "public_key_pem": signer.public_pem().decode("ascii"),
        "status": "active",
        "valid_from": utc_now().isoformat(),
        "valid_to": None,
        "role": role,
    }


def write_registry_file(path: Path, *entries: dict) -> Path:
    path.write_text(json.dumps({"keys": list(entries)}), encoding="utf-8")
    return path


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
def package(tmp_path, parts, gateway_signer) -> Path:
    records, manifest, _ = parts
    return write_package(tmp_path / "pkg", records, manifest, gateway_signer)


@pytest.fixture()
def registry_path(tmp_path, gateway_signer, checkpoint_signer) -> Path:
    return write_registry_file(
        tmp_path / "registry.json", registry_entry(gateway_signer, "gateway"),
        registry_entry(checkpoint_signer, "checkpoint"),
    )


@pytest.fixture()
def checkpoint_path(tmp_path, parts) -> Path:
    _, _, checkpoint = parts
    path = tmp_path / "checkpoint.json"
    path.write_text(checkpoint.model_dump_json(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestCliVerify:
    def test_valid_package_exits_zero_with_three_sections(
        self, capsys, package, registry_path, checkpoint_path
    ):
        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(checkpoint_path),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "INTEGRITY: PASS" in out
        assert "COVERAGE: COMPLETE" in out
        assert "OUTCOMES: 1 known, 1 unknown" in out
        assert "- unknown call ids: call-2" in out
        assert "RESULT: PASS" in out

    def test_tampered_package_exits_one_with_finding_lines(self, capsys, package, registry_path, checkpoint_path):
        ndjson = package / "events.ndjson"
        lines = ndjson.read_text(encoding="utf-8").splitlines()
        record = SignedEventRecord.model_validate_json(lines[1])
        record.event.payload["reason"] = "tampered after export"
        lines[1] = record.model_dump_json()
        ndjson.write_text("\n".join(lines) + "\n", encoding="utf-8")

        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(checkpoint_path),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "INTEGRITY: FAIL" in out
        assert "- [event_hash_mismatch] line 2:" in out
        assert "RESULT: FAIL" in out

    def test_missing_package_directory_exits_two(self, capsys, tmp_path, registry_path):
        rc = main(["verify", "--package", str(tmp_path / "nope"), "--keys", str(registry_path)])
        assert rc == 2

    def test_missing_registry_file_exits_two(self, capsys, package, tmp_path):
        rc = main(["verify", "--package", str(package), "--keys", str(tmp_path / "no-registry.json")])
        assert rc == 2

    def test_malformed_registry_exits_two(self, capsys, package, tmp_path):
        bad = tmp_path / "bad-registry.json"
        bad.write_text('{"keys": [{"key_id": "x"}]}', encoding="utf-8")
        rc = main(["verify", "--package", str(package), "--keys", str(bad)])
        assert rc == 2

    def test_malformed_checkpoint_file_exits_two(self, capsys, package, registry_path, tmp_path):
        bad = tmp_path / "bad-checkpoint.json"
        bad.write_text("{not json", encoding="utf-8")
        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(bad),
            ]
        )
        assert rc == 2

    def test_missing_checkpoint_marks_coverage_incomplete_but_integrity_passes(
        self, capsys, package, registry_path
    ):
        rc = main(["verify", "--package", str(package), "--keys", str(registry_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "INTEGRITY: PASS" in out
        assert "COVERAGE: INCOMPLETE" in out
        assert "- missing final checkpoint" in out
        assert "RESULT: FAIL" in out

    def test_expected_executions_file_matching_package_passes(
        self, capsys, package, registry_path, checkpoint_path, tmp_path
    ):
        ids = tmp_path / "ids.txt"
        ids.write_text("exec-other\nexec-cli\n", encoding="utf-8")
        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(checkpoint_path),
                "--expected-executions",
                str(ids),
            ]
        )
        assert rc == 0

    def test_expected_executions_file_without_package_id_fails(
        self, capsys, package, registry_path, checkpoint_path, tmp_path
    ):
        ids = tmp_path / "ids.txt"
        ids.write_text("exec-other\n", encoding="utf-8")
        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(checkpoint_path),
                "--expected-executions",
                str(ids),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "- unexpected execution: exec-cli" in out
        assert "- missing executions: exec-other" in out


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------


class TestCliKeygen:
    def test_keygen_creates_files_with_private_key_0600(self, capsys, tmp_path):
        out_dir = tmp_path / "keys"
        rc = main(["keygen", "--out", str(out_dir), "--role", "gateway"])
        assert rc == 0

        private_path = out_dir / "gateway_key.pem"
        public_path = out_dir / "gateway_key.pub.pem"
        assert private_path.is_file()
        assert public_path.is_file()
        assert stat.S_IMODE(private_path.stat().st_mode) == 0o600

        entry = json.loads(capsys.readouterr().out)
        assert entry["key_id"] == key_id_for_public_pem(entry["public_key_pem"])
        assert entry["public_key_pem"] == public_path.read_text(encoding="utf-8")
        assert entry["status"] == "active"
        assert entry["valid_to"] is None
        assert entry["role"] == "gateway"
        assert entry["valid_from"]

    def test_keygen_role_checkpoint_names_files(self, capsys, tmp_path):
        out_dir = tmp_path / "keys"
        rc = main(["keygen", "--out", str(out_dir), "--role", "checkpoint"])
        assert rc == 0
        assert (out_dir / "checkpoint_key.pem").is_file()
        assert (out_dir / "checkpoint_key.pub.pem").is_file()
        assert json.loads(capsys.readouterr().out)["role"] == "checkpoint"

    def test_registry_built_from_two_keygen_outputs_verifies_package_signed_by_first(
        self, capsys, tmp_path
    ):
        keys_dir = tmp_path / "keys"

        assert main(["keygen", "--out", str(keys_dir), "--role", "gateway"]) == 0
        gateway_entry = json.loads(capsys.readouterr().out)
        assert main(["keygen", "--out", str(keys_dir), "--role", "checkpoint"]) == 0
        checkpoint_entry = json.loads(capsys.readouterr().out)

        registry_path = write_registry_file(tmp_path / "registry.json", gateway_entry, checkpoint_entry)

        gateway_signer = EvidenceSigner.from_pem((keys_dir / "gateway_key.pem").read_bytes())
        checkpoint_signer = EvidenceSigner.from_pem((keys_dir / "checkpoint_key.pem").read_bytes())
        assert gateway_signer.key_id == gateway_entry["key_id"]

        records = build_records(gateway_signer)
        manifest = build_manifest(records, gateway_signer)
        package = write_package(tmp_path / "pkg", records, manifest, gateway_signer)
        checkpoint = build_checkpoint(manifest, checkpoint_signer)
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text(checkpoint.model_dump_json(), encoding="utf-8")

        rc = main(
            [
                "verify",
                "--package",
                str(package),
                "--keys",
                str(registry_path),
                "--checkpoint",
                str(checkpoint_file),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "RESULT: PASS" in out
