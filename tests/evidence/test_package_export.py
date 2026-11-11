"""Evidence package exporter tests (fail-closed validation + verifiable layout)."""

import json

import pytest

from evidence.contracts import InMemoryEvidenceSink
from evidence.package import PackageError, export_package, read_events, read_manifest
from evidence.schema import (
    DEFAULT_COVERAGE,
    EVENT_SCHEMA_VERSION,
    PACKAGE_FORMAT_VERSION,
    CoverageDescription,
    DecisionKind,
    DecisionPayload,
    EventDraft,
    EventType,
    ExecutionStartedPayload,
    FinalCheckpoint,
    OutcomePayload,
    OutcomeStatus,
    manifest_bytes,
    utc_now,
)
from evidence.signing import EvidenceSigner, verify_signature

GATEWAY_ID = "gw-test"


def draft(event_type: EventType, execution_id: str = "exec-1", **payload) -> EventDraft:
    return EventDraft(
        type=event_type, execution_id=execution_id, recorded_at=utc_now(), payload=payload
    )


def full_chain(sink: InMemoryEvidenceSink, execution_id: str = "exec-1"):
    """One allow-listed chain: start -> allow decision -> success outcome."""
    started = ExecutionStartedPayload(principal="svc-claims", policy_version="policy-7")
    decision = DecisionPayload(
        decision=DecisionKind.ALLOW,
        reason="tool bound and approved",
        call_id="call-1",
        principal="svc-claims",
        policy_version="policy-7",
        tool_name="records.search",
        input_schema_hash="ab" * 32,
        config_version="cfg-3",
    )
    outcome = OutcomePayload(call_id="call-1", status=OutcomeStatus.SUCCESS, duration_ms=12)
    return [
        sink.append(draft(EventType.EXECUTION_STARTED, execution_id, **started.model_dump(mode="json"))),
        sink.append(draft(EventType.DECISION_RECORDED, execution_id, **decision.model_dump(mode="json"))),
        sink.append(draft(EventType.OUTCOME_RECORDED, execution_id, **outcome.model_dump(mode="json"))),
    ]


@pytest.fixture()
def signer() -> EvidenceSigner:
    return EvidenceSigner.generate()


@pytest.fixture()
def sink(signer: EvidenceSigner) -> InMemoryEvidenceSink:
    return InMemoryEvidenceSink(signer, gateway_id=GATEWAY_ID)


def export(out_dir, records, signer, **kwargs):
    return export_package(out_dir, records, signer, GATEWAY_ID, signer.public_pem(), **kwargs)


class TestHappyPathExport:
    def test_export_writes_all_three_package_files(self, tmp_path, sink, signer):
        out = tmp_path / "pkg"
        export(out, full_chain(sink), signer)
        assert (out / "manifest.json").is_file()
        assert (out / "events.ndjson").is_file()
        assert (out / "signature").is_file()

    def test_manifest_fields_describe_the_chain(self, tmp_path, sink, signer):
        records = full_chain(sink)
        manifest = export(tmp_path / "pkg", records, signer)
        assert manifest.gateway_id == GATEWAY_ID
        assert manifest.execution_id == "exec-1"
        assert manifest.event_count == 3
        assert manifest.final_hash == records[-1].hash
        assert manifest.key_id == signer.key_id
        assert manifest.schema_version == EVENT_SCHEMA_VERSION
        assert manifest.package_format_version == PACKAGE_FORMAT_VERSION
        assert manifest.coverage == DEFAULT_COVERAGE
        assert manifest.checkpoint is None

    def test_ndjson_has_one_line_per_event_in_seq_order(self, tmp_path, sink, signer):
        out = tmp_path / "pkg"
        export(out, full_chain(sink), signer)
        lines = (out / "events.ndjson").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert [json.loads(line)["event"]["seq"] for line in lines] == [1, 2, 3]

    def test_signature_file_verifies_over_canonical_manifest(self, tmp_path, sink, signer):
        out = tmp_path / "pkg"
        export(out, full_chain(sink), signer)
        sig = json.loads((out / "signature").read_text(encoding="utf-8"))
        assert sig["algorithm"] == "ed25519"
        assert sig["key_id"] == signer.key_id
        assert sig["signed_object"] == "manifest.canonical"
        assert verify_signature(
            signer.public_pem(), manifest_bytes(read_manifest(out)), sig["signature"]
        ) is True

    def test_read_events_roundtrips_input_records(self, tmp_path, sink, signer):
        records = full_chain(sink)
        export(tmp_path / "pkg", records, signer)
        assert read_events(tmp_path / "pkg") == records

    def test_read_manifest_roundtrips_exported_manifest(self, tmp_path, sink, signer):
        manifest = export(tmp_path / "pkg", full_chain(sink), signer)
        assert read_manifest(tmp_path / "pkg") == manifest


class TestFailClosedValidation:
    def test_tampered_payload_after_signing_rejected(self, tmp_path, sink, signer):
        records = full_chain(sink)
        records[1].event.payload["reason"] = "nothing to see here"
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", records, signer)

    def test_records_signed_by_other_key_rejected(self, tmp_path, sink, signer):
        records = full_chain(sink)
        stranger = EvidenceSigner.generate()
        with pytest.raises(PackageError):
            export_package(tmp_path / "pkg", records, stranger, GATEWAY_ID, stranger.public_pem())

    def test_off_allowlist_payload_key_rejected(self, tmp_path, sink, signer):
        leaked = sink.append(
            draft(EventType.DECISION_RECORDED, arguments={"cmd": "rm -rf /"}, decision="allow")
        )
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", [leaked], signer)

    def test_off_allowlist_key_alongside_valid_fields_rejected(self, tmp_path, sink, signer):
        decision = DecisionPayload(
            decision=DecisionKind.ALLOW,
            reason="ok",
            call_id="call-1",
            principal="svc-claims",
            policy_version="policy-7",
            tool_name="records.search",
            input_schema_hash="ab" * 32,
            config_version="cfg-3",
        ).model_dump(mode="json")
        decision["result"] = {"rows": 42}
        record = sink.append(draft(EventType.DECISION_RECORDED, **decision))
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", [record], signer)

    def test_non_contiguous_sequence_rejected(self, tmp_path, sink, signer):
        records = full_chain(sink)
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", [records[0], records[2]], signer)

    def test_mixed_execution_ids_rejected(self, tmp_path, sink, signer):
        records = full_chain(sink)
        other = full_chain(sink, execution_id="exec-2")
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", [records[0], other[0]], signer)

    def test_empty_chain_rejected(self, tmp_path, signer):
        with pytest.raises(PackageError):
            export(tmp_path / "pkg", [], signer)

    def test_nothing_written_when_validation_fails(self, tmp_path, sink, signer):
        records = full_chain(sink)
        records[1].event.payload["reason"] = "rewritten"
        out = tmp_path / "pkg"
        with pytest.raises(PackageError):
            export(out, records, signer)
        assert not out.exists()


class TestCheckpointAndCoverage:
    def test_checkpoint_populates_manifest_checkpoint_ref(self, tmp_path, sink, signer):
        records = full_chain(sink)
        checkpoint = FinalCheckpoint(
            execution_id="exec-1",
            gateway_id=GATEWAY_ID,
            event_count=len(records),
            final_hash=records[-1].hash,
            checkpoint_key_id="ed25519:deadbeefdeadbeef",
            recorded_at=utc_now(),
            signature="ff" * 64,
        )
        manifest = export(tmp_path / "pkg", records, signer, checkpoint=checkpoint)
        assert manifest.checkpoint is not None
        assert manifest.checkpoint.event_count == checkpoint.event_count
        assert manifest.checkpoint.final_hash == checkpoint.final_hash
        assert manifest.checkpoint.checkpoint_signature == checkpoint.signature

    def test_missing_checkpoint_leaves_manifest_ref_none(self, tmp_path, sink, signer):
        manifest = export(tmp_path / "pkg", full_chain(sink), signer)
        assert manifest.checkpoint is None

    def test_custom_coverage_overrides_default(self, tmp_path, sink, signer):
        coverage = CoverageDescription(in_scope=["tools/call via gateway"], out_of_scope=["shell"])
        manifest = export(tmp_path / "pkg", full_chain(sink), signer, coverage=coverage)
        assert manifest.coverage == coverage
        assert manifest.coverage != DEFAULT_COVERAGE


class TestHumanAuditableManifest:
    def test_manifest_file_is_pretty_printed(self, tmp_path, sink, signer):
        out = tmp_path / "pkg"
        export(out, full_chain(sink), signer)
        text = (out / "manifest.json").read_text(encoding="utf-8")
        assert "\n" in text
        assert '  "' in text  # two-space JSON indentation

    def test_canonical_signature_bytes_are_not_the_pretty_file(self, tmp_path, sink, signer):
        out = tmp_path / "pkg"
        export(out, full_chain(sink), signer)
        sig = json.loads((out / "signature").read_text(encoding="utf-8"))
        canonical = manifest_bytes(read_manifest(out))
        pretty = (out / "manifest.json").read_bytes()
        assert canonical != pretty
        # Compact between tokens regardless of prose content: re-dumping the
        # parsed canonical JSON with no separators must reproduce it exactly.
        compact = json.dumps(json.loads(canonical), separators=(",", ":"), ensure_ascii=False)
        assert canonical == compact.encode("utf-8")
        assert verify_signature(signer.public_pem(), canonical, sig["signature"]) is True
