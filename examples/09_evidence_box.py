#!/usr/bin/env python3
"""Agent Evidence Box demo: controlled MCP flow → signed package → offline verification.

Runs the full pilot pipeline from ``docs/plans/agent-evidence-box.md``
against the bundled fake MCP server (an insurance claim-status tool):

1. discover the tool behind the gateway and bind name+schema;
2. run one controlled execution — allowed call, denied dangerous tool,
   and a repeated request whose idempotency key prevents a duplicate
   mutation;
3. persist every decision/outcome into the SQLite chain ledger;
4. finalize the independent checkpoint store (audit-team side);
5. export the evidence package (manifest.json, events.ndjson, signature);
6. verify the package OFFLINE with the ``peaky-peek-evidence`` CLI —
   then tamper with a copy and watch the verifier fail it.

No API server needed; everything runs in ``--out`` (default
``traces/evidence-demo``).  Inspect the package afterwards:

    cat traces/evidence-demo/package/manifest.json
    .venv-ci/bin/python -m evidence.cli verify \\
        --package traces/evidence-demo/package \\
        --keys traces/evidence-demo/keys.json \\
        --checkpoint traces/evidence-demo/checkpoint.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence.cli import main as evidence_main
from evidence.gateway import GatewayConfig, build_runtime, finalize_execution
from evidence.gateway.rpc import StdioUpstream
from evidence.gateway.runtime import write_launcher_example
from evidence.package import export_package
from evidence.schema import ToolBinding, input_schema_hash
from evidence.signing import key_id_for_public_pem

FIXTURE_SERVER = Path(__file__).resolve().parent.parent / "tests/evidence/fixtures/fake_mcp_server.py"

GATEWAY_ID = "gw-demo"
PRINCIPAL = "svc-claims-agent"
IDEMPOTENCY_ARG = "idempotency_key"


def section(title: str) -> None:
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


def discover_binding() -> ToolBinding:
    upstream = StdioUpstream([sys.executable, str(FIXTURE_SERVER)], timeout_s=10.0)
    try:
        upstream.initialize({"name": "evidence-demo", "version": "0"})
        tools = {t["name"]: t for t in upstream.request("tools/list", {})["result"]["tools"]}
        schema = tools["update_claim_status"]["inputSchema"]
    finally:
        upstream.close()
    return ToolBinding(
        tool_name="update_claim_status",
        input_schema_hash=input_schema_hash(schema),
        approved_server="fake-claims-service",
        config_version="claims-config-v1",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="traces/evidence-demo", help="workspace directory")
    args = parser.parse_args()
    workspace = Path(args.out)
    workspace.mkdir(parents=True, exist_ok=True)

    section("1. Trust boundary: gateway identity, keys, ledger, checkpoint store")
    binding = discover_binding()
    launcher = write_launcher_example(
        workspace / "gateway.json",
        GatewayConfig(
            gateway_id=GATEWAY_ID,
            principal=PRINCIPAL,
            policy_version="pilot-v1",
            config_version=binding.config_version,
            bindings=[binding],
            upstream_command=[sys.executable, str(FIXTURE_SERVER)],
            idempotency_argument_name=IDEMPOTENCY_ARG,
            upstream_timeout_s=10.0,
        ),
        runtime={
            "gateway_key_pem": str(workspace / "gateway_key.pem"),
            "sink_db": str(workspace / "ledger.db"),
            "checkpoint_dir": str(workspace / "checkpoint-store"),
        },
    )
    runtime = build_runtime(launcher)
    signer, ledger, checkpoints = runtime.signer, runtime.ledger, runtime.checkpoints
    assert ledger is not None and checkpoints is not None
    print(f"  launcher      : {launcher} (durable runtime: key, ledger, checkpoints)")
    print(f"  gateway id     : {GATEWAY_ID}")
    print(f"  gateway key id : {signer.key_id}")
    print(f"  checkpoint key : {checkpoints.key_id} (independent, audit-team side)")

    section("2. Bind the tool: name + input-schema hash, approved server identity")
    print(f"  {binding.tool_name}  schema={binding.input_schema_hash[:16]}…  server={binding.approved_server}")

    section("3. Controlled execution through the gateway (fake MCP server)")
    os.environ["FAKE_IDEMPOTENCY_ARG"] = IDEMPOTENCY_ARG
    gateway = runtime.gateway

    def send(message: dict) -> dict:
        response = gateway.handle_message(json.dumps(message))
        assert response is not None
        return response

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    print(f"  tools/list shows only approved tools: {[t['name'] for t in listed['result']['tools']]}")

    ok = send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "update_claim_status", "arguments": {"claim_id": "CLM-001", "status": "approved"}}})
    print(f"  allowed call  : CLM-001 → {ok['result']['outcomeCode']}")

    denied = send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "delete_everything", "arguments": {"confirm": True}}})
    print(f"  denied call   : delete_everything → {denied['error']['code']} ({denied['error']['data']['reason']})")

    replay_args = {"claim_id": "CLM-002", "status": "denied", IDEMPOTENCY_ARG: "idem-client-1"}
    send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
        "name": "update_claim_status", "arguments": replay_args}})
    replayed = send({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
        "name": "update_claim_status", "arguments": replay_args}})
    print(f"  repeated call : same idempotency key → {replayed['result']['outcomeCode']} (target applied it once)")

    section("4. Evidence ledger: one signed chain, every step accounted for")
    execution_id = gateway.execution_id
    head = ledger.head(execution_id)
    assert head is not None
    problems = ledger.verify_chain(execution_id, signer.public_pem())
    print(f"  execution     : {execution_id}")
    print(f"  events        : {head.event_count} (chain head {head.last_hash[:16]}…)")
    print(f"  ledger check  : {'clean' if not problems else problems}")
    for record in ledger.events(execution_id):
        event = record.event
        print(f"    seq {event.seq}  {event.type.value:<19} {event.payload.get('decision', ''):<5}"
              f" {event.payload.get('status') or ''}")

    section("5. Independent checkpoint + package export")
    # finalize_execution is what `python3 -m evidence.gateway` runs on a
    # clean shutdown: ledger head → signed final checkpoint.
    final = finalize_execution(runtime)
    assert final is not None
    checkpoint_file = workspace / "checkpoint.json"
    checkpoints.dump_checkpoint(execution_id, checkpoint_file)
    print(f"  checkpoint    : {final.event_count} events, head {final.final_hash[:16]}… signed by {checkpoints.key_id}")
    package_dir = workspace / "package"
    export_package(
        package_dir, ledger.events(execution_id), signer, gateway_id=GATEWAY_ID,
        gateway_public_pem=signer.public_pem(), checkpoint=final,
    )
    print(f"  package       : {package_dir}/ (manifest.json, events.ndjson, signature)")

    registry = workspace / "keys.json"
    checkpoint_public = (workspace / "checkpoint-store" / "checkpoint_key.pub.pem").read_text()
    registry_entries = [
        {"key_id": signer.key_id, "public_key_pem": signer.public_pem().decode(),
         "status": "active", "role": "gateway"},
        {"key_id": key_id_for_public_pem(checkpoint_public), "public_key_pem": checkpoint_public,
         "status": "active", "role": "checkpoint"},
    ]
    registry.write_text(json.dumps({"keys": registry_entries}, indent=2), encoding="utf-8")

    runtime.close()

    section("6. Offline verification (the auditor's machine)")
    rc = evidence_main([
        "verify", "--package", str(package_dir), "--keys", str(registry),
        "--checkpoint", str(checkpoint_file),
    ])

    section("7. Tamper detection: modify one event payload, verify again")
    tampered = workspace / "tampered-package"
    if not tampered.exists():
        tampered.mkdir()
        for name in ("manifest.json", "events.ndjson", "signature"):
            (tampered / name).write_bytes((package_dir / name).read_bytes())
        lines = (tampered / "events.ndjson").read_text().splitlines()
        record = json.loads(lines[1])
        record["event"]["payload"]["tool_name"] = "harmless_tool"
        lines[1] = json.dumps(record)
        (tampered / "events.ndjson").write_text("\n".join(lines) + "\n")
    evidence_main(["verify", "--package", str(tampered), "--keys", str(registry),
                   "--checkpoint", str(checkpoint_file)])

    section(f"Done — artifacts in {workspace}/")
    print("  package/manifest.json   what the auditor receives")
    print("  checkpoint.json         obtained independently from the checkpoint store")
    print("  keys.json               the customer-controlled public key registry")
    print("  tampered-package/       the same package with one forged event (verification fails)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
