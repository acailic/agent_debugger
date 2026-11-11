# Agent Evidence Box

The Agent Evidence Box gives an auditor **signed, offline-verifiable
evidence for controlled MCP tool flows**: an MCP gateway in front of the
tool records every request decision and observed outcome into a
per-execution Ed25519 hash chain, an independent checkpoint store pins the
expected executions, and an exporter bundles a package
(`manifest.json` + `events.ndjson` + signature) that a separately
distributed CLI verifies offline — before, and independently of, anything
Peaky Peek itself reports. The investigation side then maps those
verified events onto the Peaky Peek timeline so an operator can open the
same event in an incident investigation. Full plan, competition analysis
and pilot criteria: [docs/plans/agent-evidence-box.md](plans/agent-evidence-box.md).

## Trust boundary (summary)

| Approach | Coverage and cost |
| --- | --- |
| Signing at existing SDK ingest | Fastest to integrate; proves integrity only from the moment of receipt, and event selection stays inside the agent process. |
| **Gateway on the path to the MCP tool (pilot choice)** | Independently records calls for tools infrastructure places behind the gateway. Requires access control on the target service; adds latency. |
| Isolated runtime with network/process supervision | Could extend coverage to shell, files and direct API calls. Additional per-environment integration; only if customers confirm the need. |

The package proves **what the gateway received, decided, forwarded and
which acknowledgement it observed**, within the declared MCP flow. Shell,
local files, model-provider calls and direct calls to other services are
out of scope. The gateway, its key and the offline verifier are inside the
trust boundary; the agent is not. An independent checkpoint store (audit
team controlled) records execution starts and a signed final checkpoint,
so a missing package or a truncated chain is detectable.

Two deliberately separate signals in the UI and API:

- **Cryptographic verification** (`integrity`, `coverage` on packages and
  entries) — the offline verifier's verdict over the signed records.
- **Behavioral assessment** (trust score, claim verification in the audit
  engine) — Peaky Peek's existing heuristics over the recorded trace.

One never overwrites the other; both are displayed next to each other.

## Investigation-side integration (this slice)

- `evidence/adapter.py` — `EvidenceTimelineAdapter` parses exported
  packages (plain JSON + pydantic against the shared
  `evidence/schema.py` contract), maps each signed event to an
  `EvidenceEntry` timeline row (`run_id`, `call_id`, `verified_source`,
  `original_ref` = `<package>#events.ndjson:L<line>`), merges a verifier
  `VerificationResult` onto the package/entries, and applies the existing
  redaction pipeline (`redaction/pipeline.py`, via
  `apply_payload_redaction` → `RedactionPipeline.scrub_payload`) to every
  payload-origin string before display.
- `api/evidence_routes.py` — read-only Audit API surface (below).
- `frontend/src/components/EvidencePanel.tsx` — collapsible Evidence
  section inside the AuditPanel: package summaries, per-event decision /
  outcome badges, and the integrity badge as a separate field from the
  behavioral assessment.
- Replay keeps using the existing flow when a suitable checkpoint exists;
  simulated replay with fixed synthetic-tool results and wider execution
  continuation follow [W04](ROADMAP.md#w04--from-inspection-to-controlled-replay-experiments).

## Operator runbook

The fastest walkthrough is the self-contained demo (no API server needed):

```bash
python3 examples/09_evidence_box.py --out traces/evidence-demo
```

It runs every step below against the bundled fake MCP server and prints
both a passing and a failing (tampered) offline verification.

Step by step:

```bash
# 1. Generate a role key pair (private key 0600; the printed JSON entry
#    goes into the customer's key registry).  Key id is content-derived:
#    ed25519:<16 hex>.  Retired keys stay in the registry so historical
#    packages keep verifying after rotation.
peaky-peek-evidence keygen --out /secure/keys --role gateway

# 2. Run the gateway in front of the MCP tool (single client, single
#    server, protocol 2025-06-18 over stdio; fail-closed: a request is
#    refused when its decision cannot be persisted first).  The config
#    JSON carries the gateway identity, principal, policy/config
#    versions, approved tool bindings (name + input-schema hash) and the
#    upstream command.  Durable wiring (SQLite ledger + checkpoint-store
#    hook) is assembled in code — see examples/09_evidence_box.py.
python3 -m evidence.gateway --config gateway.json

# 3. Finalize the independent checkpoint (event count + final hash) and
#    export the evidence package (manifest.json, events.ndjson,
#    signature) into the directory Peaky Peek reads
#    (EVIDENCE_PACKAGE_DIR, default data/evidence):
#    evidence.checkpoint.CheckpointStore.finalize/dump_checkpoint and
#    evidence.package.export_package — both shown in the demo.

# 4. Offline verification on the auditor's machine (stdlib +
#    cryptography only).  The checkpoint is obtained independently from
#    the checkpoint store; --expected-executions is optional (newline-
#    separated execution ids known to deserve packages).
peaky-peek-evidence verify \
  --package "$PACKAGE_DIR" \
  --keys keys.json \
  --checkpoint checkpoint.json \
  --expected-executions expected.txt
```

Exit codes: `0` verification passed, `1` verification failed,
`2` usage/environment error.  Output carries the three independent
sections — `INTEGRITY`, `COVERAGE`, `OUTCOMES` — plus `RESULT`.

### API endpoints

| Endpoint | Behavior |
| --- | --- |
| `GET /api/evidence/packages` | Summary rows for every package under `EVIDENCE_PACKAGE_DIR`: `execution_id`, `created_at`, `event_count`, `integrity`, `coverage`, `outcomes_known`/`outcomes_unknown`, `run_ids`, `gateway_id`, `key_id`. Empty list (not 404) when no packages exist. A malformed package keeps its directory-name identity with `integrity="failed"` and an `error` note. |
| `GET /api/evidence/packages/{execution_id}` | Full package: summary fields plus `manifest`, verifier `verification` (when merged) and timeline `entries` with `original_ref` line references. 404 for an unknown execution; a present-but-unparseable package returns the flagged result (`integrity="failed"`, `error`) rather than a 5xx. |

Both routes are read-only and follow the local-file-store exposure
pattern (open in local mode, valid Bearer key in hosted mode via
`require_hosted_auth`).

### Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `EVIDENCE_PACKAGE_DIR` | `data/evidence` | Directory holding exported evidence packages — one sub-directory per execution (resolved against the server working directory, like the analytics database). |

## Interoperability

The evidence contract is deliberately mappable onto the emerging
Internet-Drafts for agent audit trails, and onto OTel identifiers per
[W07 — Framework fidelity and open interoperability](ROADMAP.md#w07--framework-fidelity-and-open-interoperability).

| Evidence Box concept | AAT ([draft-sharif-agent-audit-trail](https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/)) | AIVS ([draft-stone-aivs](https://datatracker.ietf.org/doc/draft-stone-aivs/)) |
| --- | --- | --- |
| `SignedEventRecord` (canonical JSON + Ed25519) | signed audit record / trail entry | verifiable interaction record |
| `DecisionPayload` (allow/deny, policy version, tool binding) | agent action decision with policy evaluation | authorization decision |
| `OutcomePayload` (status, outcome code, idempotency key) | tool result / outcome entry | service response receipt |
| `prev_hash`/`seq`/`final_hash` chain | tamper-evident log chaining | hash-chained records |
| `PackageManifest` + signature | exportable audit trail bundle | evidence package |
| `FinalCheckpoint` / `CheckpointRef` | third-party attestation / anchor | signed checkpoint anchor |
| `VerificationResult` (integrity / coverage / outcomes) | verification report | validation result |
| `principal` + `identity_source` | actor identity | user/session identity |

### OTel identifier linkage (W07)

W07 requires a versioned OTel mapping that preserves source IDs and
distinguishes imported generic spans from native evidence-rich events.
The pilot linkage is:

- `run_id` ↔ OTel **trace id** of the agent run (the SDK session
  correlation id); carried on every `ExecutionStartedPayload` and
  `DecisionPayload` so evidence rows align with the Peaky Peek timeline.
- `call_id` ↔ OTel **span id** of the MCP `tools/call` span; stable
  across decision and outcome records, and the join key for
  event-level lookup (`EvidenceTimelineAdapter.find_by_call_id`).
- `gateway_id` / `key_id` ↔ resource attributes
  (`service.instance.id` of the gateway) and a verification attribute —
  they identify *who signed*, not where the span originated.
- Imported evidence events must preserve these source IDs as attributes
  (e.g. `evidence.gateway_id`, `evidence.key_id`,
  `evidence.original_ref`) rather than reissuing native event IDs, so an
  imported row is always distinguishable from a natively captured one —
  the "no invented provenance" gate of W07.
