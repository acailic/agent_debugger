"""Durable gateway runtime wiring tests (launcher JSON → ledger + checkpoints)."""

from __future__ import annotations

import io
import json
import stat
import sys
from pathlib import Path

import pytest

from evidence.checkpoint import CheckpointError
from evidence.gateway import build_runtime, finalize_execution
from evidence.gateway.config import GatewayConfig
from evidence.gateway.rpc import StdioUpstream
from evidence.gateway.runtime import write_launcher_example
from evidence.schema import EventType, input_schema_hash

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
PRINCIPAL = "svc-claims-agent"


def _fixture_schema_hash() -> str:
    """Discover the live input schema of the mutating tool (real hash)."""
    upstream = StdioUpstream([sys.executable, str(FIXTURE_SERVER)], timeout_s=10.0)
    try:
        upstream.initialize({"name": "runtime-tests", "version": "0"})
        tools = {t["name"]: t for t in upstream.request("tools/list", {})["result"]["tools"]}
        return input_schema_hash(tools["update_claim_status"]["inputSchema"])
    finally:
        upstream.close()


def _launcher(tmp_path: Path, runtime: dict | None) -> Path:
    document = {
        "gateway_id": "gw-runtime",
        "principal": PRINCIPAL,
        "policy_version": "pilot-v1",
        "config_version": "claims-config-v1",
        "bindings": [
            {
                "tool_name": "update_claim_status",
                "input_schema_hash": _fixture_schema_hash(),
                "approved_server": "fake-claims-service",
                "config_version": "claims-config-v1",
            }
        ],
        "upstream_command": [sys.executable, str(FIXTURE_SERVER)],
        "idempotency_argument_name": "idempotency_key",
    }
    if runtime is not None:
        document["runtime"] = runtime
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _allow_call(runtime, msg_id: int) -> dict:
    response = runtime.gateway.handle_message(json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
        "params": {"name": "update_claim_status",
                   "arguments": {"claim_id": "CLM-001", "status": "approved"}},
    }))
    assert response is not None
    return response


class TestDurableWiring:
    def test_first_start_generates_key_with_0600(self, tmp_path):
        runtime = build_runtime(_launcher(tmp_path, {
            "gateway_key_pem": str(tmp_path / "keys" / "gateway_key.pem"),
            "sink_db": str(tmp_path / "ledger.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        }))
        try:
            assert runtime.durable
            key_path = tmp_path / "keys" / "gateway_key.pem"
            mode = stat.S_IMODE(key_path.stat().st_mode)
            assert mode == 0o600
            assert runtime.signer.key_id == runtime.sink.key_id
        finally:
            runtime.close()

    def test_restart_reuses_key_and_keeps_history(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_MODE", "normal")
        monkeypatch.delenv("FAKE_APPLY_LOG", raising=False)
        monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", "idempotency_key")
        launcher = _launcher(tmp_path, {
            "gateway_key_pem": str(tmp_path / "gateway_key.pem"),
            "sink_db": str(tmp_path / "ledger.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        })

        first = build_runtime(launcher)
        try:
            first.gateway.handle_message(json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
            _allow_call(first, 2)
            first_execution = first.gateway.execution_id
        finally:
            first.close()

        second = build_runtime(launcher)
        try:
            # Same gateway identity across restarts...
            assert second.signer.key_id == first.signer.key_id
            # ...and the earlier execution's attempt history is still readable.
            events = second.ledger.events(first_execution)
            assert [record.event.type for record in events] == [
                EventType.EXECUTION_STARTED,
                EventType.DECISION_RECORDED,
                EventType.OUTCOME_RECORDED,
            ]
            assert second.ledger.verify_chain(first_execution, second.signer.public_pem()) == []
        finally:
            second.close()

    def test_checkpoint_start_recorded_before_first_forward(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_MODE", "normal")
        monkeypatch.delenv("FAKE_APPLY_LOG", raising=False)
        monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", "idempotency_key")
        runtime = build_runtime(_launcher(tmp_path, {
            "sink_db": str(tmp_path / "ledger.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        }))
        try:
            _allow_call(runtime, 1)
            start = runtime.checkpoints.get_start(runtime.gateway.execution_id)
            assert start is not None
            assert start.principal == PRINCIPAL
            assert start.gateway_id == "gw-runtime"
        finally:
            runtime.close()

    def test_finalize_execution_matches_ledger_head(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_MODE", "normal")
        monkeypatch.delenv("FAKE_APPLY_LOG", raising=False)
        monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", "idempotency_key")
        runtime = build_runtime(_launcher(tmp_path, {
            "sink_db": str(tmp_path / "ledger.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        }))
        try:
            runtime.gateway.handle_message(json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
            _allow_call(runtime, 2)
            head = runtime.ledger.head(runtime.gateway.execution_id)
            checkpoint = finalize_execution(runtime)
            assert checkpoint is not None and head is not None
            assert checkpoint.event_count == head.event_count
            assert checkpoint.final_hash == head.last_hash
            assert runtime.checkpoints.verify_final(checkpoint)
            with pytest.raises(CheckpointError):
                finalize_execution(runtime)
        finally:
            runtime.close()


class TestDemoModeAndValidation:
    def test_no_runtime_section_is_in_memory(self, tmp_path):
        runtime = build_runtime(_launcher(tmp_path, None))
        try:
            assert not runtime.durable
            assert runtime.ledger is None
            assert runtime.checkpoints is None
            assert finalize_execution(runtime) is None
        finally:
            runtime.close()

    def test_unknown_runtime_key_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="unknown runtime keys"):
            build_runtime(_launcher(tmp_path, {"sink_db": str(tmp_path / "l.db"), "nope": "x"}))

    def test_runtime_section_type_checked(self, tmp_path):
        with pytest.raises(ValueError, match="must be an object"):
            build_runtime(_launcher(tmp_path, ["not", "a", "dict"]))

    def test_launchers_roundtrip_through_write_helper(self, tmp_path):
        config = GatewayConfig(
            gateway_id="gw-x", principal="p", policy_version="v1", config_version="c1",
            bindings=[], upstream_command=["true"],
        )
        path = write_launcher_example(tmp_path / "sub" / "gw.json", config, {"sink_db": "l.db"})
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["runtime"] == {"sink_db": "l.db"}
        assert document["gateway_id"] == "gw-x"


class TestMainWiring:
    def test_main_serves_durable_and_finalizes(self, tmp_path, monkeypatch):
        from evidence.gateway.proxy import main as gateway_main

        monkeypatch.setenv("FAKE_MODE", "normal")
        monkeypatch.delenv("FAKE_APPLY_LOG", raising=False)
        monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", "idempotency_key")
        launcher = _launcher(tmp_path, {
            "gateway_key_pem": str(tmp_path / "gateway_key.pem"),
            "sink_db": str(tmp_path / "ledger.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        })
        requests = "".join(json.dumps(message) + "\n" for message in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "update_claim_status",
                "arguments": {"claim_id": "CLM-009", "status": "review"},
            }},
        ])
        stdin, stdout, stderr = io.StringIO(requests), io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)

        assert gateway_main(["--config", str(launcher)]) == 0

        assert "finalized checkpoint" in stderr.getvalue()
        # The durable artifacts exist on disk after the process "exits".
        assert (tmp_path / "ledger.db").exists()
        assert (tmp_path / "checkpoints" / "checkpoints.db").exists()
        # serve() must use the CURRENT sys.stdout, not a def-time default:
        # the responses landed in our StringIO, not the real stdout.
        assert '"id": 2' in stdout.getvalue()
        assert "claim_status_updated" in stdout.getvalue()
