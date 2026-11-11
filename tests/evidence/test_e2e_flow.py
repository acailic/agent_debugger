"""End-to-end synthetic evidence flow: gateway → ledger → checkpoint → package → offline CLI.

Exercises the pilot-criteria subset of docs/plans/agent-evidence-box.md
§"Kriterijumi za pilot" against the real subprocess fake MCP server:
an allowed call, a denied call, a repeated request with the same
idempotency key (no duplicate mutation), and an interruption *after*
forwarding (unknown outcome).  Then exports the package, obtains the
checkpoint independently, and drives the offline CLI: PASS on the
honest package, FAIL on a modified copy, a truncated copy, and a
missing checkpoint.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from evidence.checkpoint import CheckpointStore
from evidence.cli import main as evidence_main
from evidence.contracts import EvidenceSink
from evidence.gateway import EvidenceGateway, GatewayConfig
from evidence.gateway.rpc import StdioUpstream
from evidence.ledger import ChainLedger
from evidence.package import EVENTS_FILENAME, export_package
from evidence.schema import EventType, ToolBinding, input_schema_hash
from evidence.signing import EvidenceSigner, key_id_for_public_pem

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"

GATEWAY_ID = "gw-e2e"
PRINCIPAL = "svc-claims-agent"
POLICY_VERSION = "pilot-v1"
IDEMPOTENCY_ARG = "idempotency_key"


def _discover_binding() -> ToolBinding:
    """Discover the fake server's live schema and bind the mutating tool."""
    upstream = StdioUpstream([sys.executable, str(FIXTURE_SERVER)], timeout_s=10.0)
    try:
        upstream.initialize({"name": "e2e-discovery", "version": "0"})
        response = upstream.request("tools/list", {})
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        schema = tools["update_claim_status"]["inputSchema"]
    finally:
        upstream.close()
    return ToolBinding(
        tool_name="update_claim_status",
        input_schema_hash=input_schema_hash(schema),
        approved_server="fake-claims-service",
        config_version="claims-config-v1",
    )


def _build_gateway(
    tmp_path: Path, ledger_dir: str, mode: str, apply_log: Path | None, monkeypatch: pytest.MonkeyPatch
) -> tuple[EvidenceGateway, ChainLedger, EvidenceSigner, CheckpointStore]:
    monkeypatch.setenv("FAKE_MODE", mode)
    if apply_log is not None:
        monkeypatch.setenv("FAKE_APPLY_LOG", str(apply_log))
    else:
        monkeypatch.delenv("FAKE_APPLY_LOG", raising=False)
    monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", IDEMPOTENCY_ARG)

    signer = EvidenceSigner.generate()
    ledger = ChainLedger(tmp_path / f"{ledger_dir}.db", signer, gateway_id=GATEWAY_ID)
    checkpoint_store = CheckpointStore(tmp_path / f"{ledger_dir}-checkpoint")
    config = GatewayConfig(
        gateway_id=GATEWAY_ID,
        principal=PRINCIPAL,
        policy_version=POLICY_VERSION,
        config_version="claims-config-v1",
        bindings=[_discover_binding()],
        upstream_command=[sys.executable, str(FIXTURE_SERVER)],
        idempotency_argument_name=IDEMPOTENCY_ARG,
        upstream_timeout_s=10.0,
    )
    upstream = StdioUpstream(config.upstream_command, timeout_s=config.upstream_timeout_s)
    gateway = EvidenceGateway(
        config,
        sink=ledger,
        upstream=upstream,
        on_execution_started=lambda execution_id: checkpoint_store.record_execution_start(
            execution_id, gateway_id=GATEWAY_ID, principal=PRINCIPAL, policy_version=POLICY_VERSION
        ),
    )
    return gateway, ledger, signer, checkpoint_store


def _send(gateway: EvidenceGateway, message: dict) -> dict:
    response = gateway.handle_message(json.dumps(message))
    assert response is not None
    return response


def _call(gateway: EvidenceGateway, msg_id: int, name: str, arguments: dict) -> dict:
    return _send(
        gateway,
        {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )


def _registry_file(path: Path, gateway_signer: EvidenceSigner, checkpoint_public_pem: str) -> Path:
    registry = {
        "keys": [
            {
                "key_id": gateway_signer.key_id,
                "public_key_pem": gateway_signer.public_pem().decode(),
                "status": "active",
                "role": "gateway",
            },
            {
                "key_id": key_id_for_public_pem(checkpoint_public_pem),
                "public_key_pem": checkpoint_public_pem,
                "status": "active",
                "role": "checkpoint",
            },
        ]
    }
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


class TestControlledFlow:
    def test_full_flow_and_offline_verification(self, tmp_path, monkeypatch, capsys):
        apply_log = tmp_path / "apply.log"
        gateway, ledger, signer, checkpoints = _build_gateway(
            tmp_path, "ledger", "normal", apply_log, monkeypatch
        )

        # --- the synthetic controlled MCP run -------------------------------
        init = _send(gateway, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["protocolVersion"] == "2025-06-18"

        listed = _send(gateway, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert [tool["name"] for tool in listed["result"]["tools"]] == ["update_claim_status"]

        # 1) allowed mutating call
        allowed = _call(gateway, 3, "update_claim_status", {"claim_id": "CLM-001", "status": "approved"})
        assert allowed["result"]["outcomeCode"] == "claim_status_updated"

        # 2) denied call: the dangerous tool exists upstream but is unapproved
        denied = _call(gateway, 4, "delete_everything", {"confirm": True})
        assert denied["error"]["code"] == -32001
        assert denied["error"]["data"]["reason"] == "unapproved_tool"

        # 3) repeated request with the SAME client idempotency key
        replay_arguments = {"claim_id": "CLM-002", "status": "denied", IDEMPOTENCY_ARG: "idem-client-1"}
        first_replay = _call(gateway, 5, "update_claim_status", replay_arguments)
        second_replay = _call(gateway, 6, "update_claim_status", replay_arguments)
        assert first_replay["result"]["outcomeCode"] == "claim_status_updated"
        assert second_replay["result"] == first_replay["result"]
        applied = [line for line in apply_log.read_text().splitlines() if line.strip()]
        # CLM-001 once + CLM-002 once (the retry was deduped by key) — and
        # delete_everything never applied because it was denied pre-forward.
        assert len(applied) == 2
        assert not any("ALL" in line for line in applied)

        # --- the ledger tells the whole story --------------------------------
        execution_id = gateway.execution_id
        events = ledger.events(execution_id)
        assert [record.event.type for record in events] == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,   # allow CLM-001
            EventType.OUTCOME_RECORDED,    # success
            EventType.DECISION_RECORDED,   # deny delete_everything (no outcome — never forwarded)
            EventType.DECISION_RECORDED,   # allow replay-1 (client key idem-client-1)
            EventType.OUTCOME_RECORDED,    # success (applied)
            EventType.DECISION_RECORDED,   # allow replay-2 (same key: its own decision, deduped tool-side)
            EventType.OUTCOME_RECORDED,    # success (replayed result)
        ]
        statuses = [
            record.event.payload.get("status")
            for record in events
            if record.event.type is EventType.OUTCOME_RECORDED
        ]
        assert statuses == ["success", "success", "success"]
        assert ledger.verify_chain(execution_id, signer.public_pem()) == []
        assert isinstance(ledger, EvidenceSink)

        # --- independent checkpoint + package export --------------------------
        head = ledger.head(execution_id)
        assert head is not None
        # the start record reached the independent store before the first forward
        start = checkpoints.get_start(execution_id)
        assert start is not None and start.principal == PRINCIPAL
        final = checkpoints.finalize(execution_id, GATEWAY_ID, head.event_count, head.last_hash)
        assert checkpoints.verify_final(final)

        package_dir = tmp_path / "package"
        export_package(
            package_dir, events, signer, gateway_id=GATEWAY_ID,
            gateway_public_pem=signer.public_pem(), checkpoint=final,
        )
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoints.dump_checkpoint(execution_id, checkpoint_file)

        checkpoint_public_pem = (tmp_path / "ledger-checkpoint" / "checkpoint_key.pub.pem").read_text()
        registry_file = _registry_file(tmp_path / "keys.json", signer, checkpoint_public_pem)
        expected_file = tmp_path / "expected.txt"
        expected_file.write_text(execution_id + "\n", encoding="utf-8")

        def verify(package: Path, *extra: str) -> tuple[int, str]:
            rc = evidence_main([
                "verify", "--package", str(package), "--keys", str(registry_file), *extra,
            ])
            out = capsys.readouterr().out
            return rc, out

        # --- the auditor's offline verdicts -----------------------------------
        rc, out = verify(
            package_dir,
            "--checkpoint", str(checkpoint_file), "--expected-executions", str(expected_file),
        )
        assert rc == 0
        assert "INTEGRITY: PASS" in out
        assert "COVERAGE: COMPLETE" in out
        assert "RESULT: PASS" in out
        assert "OUTCOMES: 3 known, 0 unknown" in out

        # modification: rewrite one event payload
        tampered = tmp_path / "tampered"
        shutil.copytree(package_dir, tampered)
        lines = (tampered / EVENTS_FILENAME).read_text().splitlines()
        record = json.loads(lines[0])
        record["event"]["payload"]["policy_version"] = "forged-v9"
        lines[0] = json.dumps(record)
        (tampered / EVENTS_FILENAME).write_text("\n".join(lines) + "\n")
        rc, out = verify(tampered, "--checkpoint", str(checkpoint_file))
        assert rc == 1
        assert "event_hash_mismatch" in out
        assert "RESULT: FAIL" in out

        # truncation: drop the last event, keep the manifest intact
        truncated = tmp_path / "truncated"
        shutil.copytree(package_dir, truncated)
        lines = (truncated / EVENTS_FILENAME).read_text().splitlines()
        (truncated / EVENTS_FILENAME).write_text("\n".join(lines[:-1]) + "\n")
        rc, out = verify(truncated, "--checkpoint", str(checkpoint_file))
        assert rc == 1
        assert "count_mismatch" in out

        # missing checkpoint: integrity of what exists still holds
        rc, out = verify(package_dir)
        assert rc == 1
        assert "INTEGRITY: PASS" in out
        assert "COVERAGE: INCOMPLETE" in out

    def test_interruption_after_forward_records_unknown_outcome(self, tmp_path, monkeypatch):
        apply_log = tmp_path / "apply.log"
        gateway, ledger, signer, _ = _build_gateway(
            tmp_path, "crash-ledger", "crash_after_apply", apply_log, monkeypatch
        )
        _send(gateway, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        lost = _call(gateway, 2, "update_claim_status", {"claim_id": "CLM-777", "status": "review"})
        assert lost["error"]["code"] == -32002

        # the mutation applied upstream but the response never arrived
        assert any("CLM-777" in line for line in apply_log.read_text().splitlines())
        events = ledger.events(gateway.execution_id)
        outcomes = [
            record.event.payload for record in events
            if record.event.type is EventType.OUTCOME_RECORDED
        ]
        assert outcomes == [{"call_id": outcomes[0]["call_id"], "status": "unknown",
                             "outcome_code": None, "error_kind": "upstream_lost",
                             "duration_ms": outcomes[0]["duration_ms"],
                             "idempotency_key": outcomes[0]["idempotency_key"]}]
        # exactly one forward happened — no automatic retry
        assert len(apply_log.read_text().splitlines()) == 1
        assert ledger.verify_chain(gateway.execution_id, signer.public_pem()) == []
