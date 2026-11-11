"""Evidence Box API route tests.

Uses the shared ``api_client`` fixture (httpx ASGITransport against the
real app) and points ``EVIDENCE_PACKAGE_DIR`` at a per-test tmp directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidence.schema import (
    GENESIS_PREV_HASH,
    DecisionKind,
    DecisionPayload,
    EventType,
    EvidenceEvent,
    OutcomePayload,
    OutcomeStatus,
    PackageManifest,
    SignedEventRecord,
    event_hash,
)

FIXED_AT = datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
GATEWAY_ID = "gw-route-test"
KEY_ID = "ed25519:deadbeefdeadbeef"


def _record(seq: int, event_type: EventType, payload: dict) -> SignedEventRecord:
    event = EvidenceEvent(
        type=event_type,
        execution_id="exec-routes",
        seq=seq,
        prev_hash=GENESIS_PREV_HASH if seq == 1 else "ab" * 32,
        gateway_id=GATEWAY_ID,
        key_id=KEY_ID,
        recorded_at=FIXED_AT,
        payload=payload,
    )
    return SignedEventRecord(event=event, hash=event_hash(event), signature="ff" * 64)


def write_package(root: Path, name: str = "exec-routes") -> Path:
    """Write one valid package directory under *root*."""
    package_dir = root / name
    package_dir.mkdir(parents=True)
    records = [
        _record(
            1, EventType.EXECUTION_STARTED, {"principal": "svc-claims", "policy_version": "pol-1", "run_id": "run-7"}
        ),
        _record(
            2,
            EventType.DECISION_RECORDED,
            DecisionPayload(
                decision=DecisionKind.ALLOW,
                reason="policy permits update",
                call_id="call-1",
                principal="svc-claims",
                policy_version="pol-1",
                tool_name="update_claim_status",
                input_schema_hash="ab" * 32,
                config_version="cfg-1",
                run_id="run-7",
            ).model_dump(mode="json"),
        ),
        _record(
            3,
            EventType.OUTCOME_RECORDED,
            OutcomePayload(call_id="call-1", status=OutcomeStatus.SUCCESS, outcome_code="updated").model_dump(
                mode="json"
            ),
        ),
        _record(
            4,
            EventType.OUTCOME_RECORDED,
            OutcomePayload(call_id="call-2", status=OutcomeStatus.UNKNOWN).model_dump(mode="json"),
        ),
    ]
    manifest = PackageManifest(
        gateway_id=GATEWAY_ID,
        execution_id="exec-routes",
        event_count=len(records),
        final_hash=records[-1].hash,
        key_id=KEY_ID,
        created_at=FIXED_AT,
    )
    (package_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    (package_dir / "events.ndjson").write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n", encoding="utf-8"
    )
    return package_dir


@pytest.fixture()
def evidence_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "evidence"
    root.mkdir()
    monkeypatch.setenv("EVIDENCE_PACKAGE_DIR", str(root))
    return root


@pytest.mark.asyncio
async def test_list_returns_empty_array_when_no_packages(api_client, evidence_root):
    resp = await api_client.get("/api/evidence/packages")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_package_summaries(api_client, evidence_root):
    write_package(evidence_root)

    resp = await api_client.get("/api/evidence/packages")

    assert resp.status_code == 200
    summaries = resp.json()
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["execution_id"] == "exec-routes"
    assert summary["package_name"] == "exec-routes"
    assert summary["created_at"].startswith("2026-11-11T10:00:00")
    assert summary["event_count"] == 4
    assert summary["integrity"] == "unverified"
    assert summary["coverage"] == "unknown"
    assert summary["outcomes_known"] == 1
    assert summary["outcomes_unknown"] == 1
    assert summary["run_ids"] == ["run-7"]
    assert summary["gateway_id"] == GATEWAY_ID
    assert summary["key_id"] == KEY_ID


@pytest.mark.asyncio
async def test_detail_returns_entries_and_manifest(api_client, evidence_root):
    write_package(evidence_root)

    resp = await api_client.get("/api/evidence/packages/exec-routes")

    assert resp.status_code == 200
    detail = resp.json()
    assert detail["execution_id"] == "exec-routes"
    assert detail["manifest"]["gateway_id"] == GATEWAY_ID
    assert detail["verification"] is None
    assert [entry["seq"] for entry in detail["entries"]] == [1, 2, 3, 4]
    decision = detail["entries"][1]
    assert decision["decision"] == "allow"
    assert decision["call_id"] == "call-1"
    assert decision["run_id"] == "run-7"
    assert decision["verified_source"] == f"evidence-gateway:{GATEWAY_ID}"
    assert decision["original_ref"] == "exec-routes#events.ndjson:L2"
    unknown = detail["entries"][3]
    assert unknown["outcome_status"] == "unknown"


@pytest.mark.asyncio
async def test_unknown_execution_returns_404(api_client, evidence_root):
    resp = await api_client.get("/api/evidence/packages/no-such-execution")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "no-such-execution" in body["detail"]


@pytest.mark.asyncio
async def test_malformed_package_is_flagged_in_list_and_detail(api_client, evidence_root):
    broken = evidence_root / "exec-broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("{ not json", encoding="utf-8")

    listing = await api_client.get("/api/evidence/packages")
    assert listing.status_code == 200
    summaries = listing.json()
    assert len(summaries) == 1
    assert summaries[0]["execution_id"] == "exec-broken"
    assert summaries[0]["integrity"] == "failed"
    assert summaries[0]["error"] is not None

    detail = await api_client.get("/api/evidence/packages/exec-broken")
    assert detail.status_code == 200
    body = detail.json()
    assert body["integrity"] == "failed"
    assert body["error"] is not None
    assert body["entries"] == []
    assert body["manifest"] is None
