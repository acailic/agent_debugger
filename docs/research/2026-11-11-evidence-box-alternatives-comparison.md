# Evidence Box alternatives comparison: build gateway, integrate recorder, or stop

**Compared:** 2026-11-11. This is the Week-1 deliverable from
[docs/plans/agent-evidence-box.md](../plans/agent-evidence-box.md) §"Dokazi i
konkurencija": the same use case compared against Obsign and alternatives on
four axes — coverage, integration time, investigation time, export usability.
The result gates the commercial decision (build the gateway / integrate an
existing recorder / stop). Our column uses facts from
[docs/evidence-box.md](../evidence-box.md) and the repo; the demo
(`examples/09_evidence_box.py --out /tmp/evidence-demo-check`) was run fresh
today and both the passing and the tampered verification behaved as documented.
All competitor claims come from primary sources fetched 2026-11-11 (list at the
end); nothing below was verified by installing or running their code.

Provenance marks: **[measured]** = exercised or asserted in this repo (artifact
named inline); **[documented]** = stated by the fetched primary source (linked
inline); **[not documented]** = the source is silent, and we do not guess.

## Use case (from the plan)

A B2B team building insurance-claims agents already has one MCP tool that
mutates claim status. Pilot runs on staging with synthetic claims and that one
approved tool. A platform/security lead puts a gateway in front of the tool; a
person from internal audit receives an evidence package and verifies it offline
on another machine; an operator opens the same verified event inside a Peaky
Peaky investigation. The audit questions: which workload requested the change,
which policy applied, what the tool returned, and whether that execution's
history is complete within the supervised flow. Source:
[plan §"Prvi slučaj upotrebe"](../plans/agent-evidence-box.md).

Threat grounding: [Qin et al. 2026](https://arxiv.org/abs/2609.30266) showed
every tested local agent harness except one (Muse Code) let the agent delete
its own traces, and explicitly recommend that "trace logging happens through an
independent interception mechanism outside of the agent's control". That is the
load-bearing argument for gateway-side (or otherwise external) recording, and
it applies to every row of the table below.

## Approaches compared

- **Peaky Peek Evidence Box** (server-v0.7.0) — MCP gateway + per-execution
  Ed25519 hash chain + independent checkpoint store + offline CLI.
- **[Obsign](https://github.com/obsign/obsign)** — MCP gateway + ledger +
  control plane + offline verifier; Apache-2.0, Rust.
- **[Agent Flight Recorder](https://arxiv.org/abs/2609.01931)** (Bindschaedler,
  Botha, Siebenbrunner; BCCA 2026) — structured event recording, hash chain,
  Merkle batches, on-chain anchoring. Compared here as the SDK-side recorder
  row of the plan's trust-boundary table; see the honesty note on interception
  point below.
- **[Golem audit trail](https://docs.golem.team/guides/audit-trail)** —
  per-machine service recording coding agents via hooks plus an MCP gateway;
  signed, hash-chained entries with 15-minute Merkle roots.
- Format references (not recorders): [AIVS](https://datatracker.ietf.org/doc/draft-stone-aivs/)
  (`draft-stone-aivs-01`, informational, no IETF standing) and
  [AAT](https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/)
  (`draft-sharif-agent-audit-trail-09`, intended standards track, not IETF-endorsed).

## What each approach covers

| | Peaky Peek Evidence Box | Obsign | Agent Flight Recorder | Golem-style signed logs |
|---|---|---|---|---|
| Interception point | Gateway on the path to the MCP tool; own identity, key, store; target service accepts mutations only from the gateway identity [documented, our runbook](../evidence-box.md) | Same: proxy over stdio or Streamable HTTP; arbitrates tools/call, resources/read, prompts/get, subscriptions, completion, server-initiated sampling/elicitation; default-deny method space [documented] | Not stated in the abstract — the paper's full text was not fetched; treated as SDK-side per the plan's trust-boundary framing, **could not verify from primary source** | Outside the agent: per-machine service fed by agent hooks plus Golem's MCP gateway; multi-harness (Claude Code, Cursor, Codex, Copilot, Gemini CLI, Devin, Antigravity, Hermes, OpenClaw) [documented] |
| Tamper model | Agent cannot alter records (it is outside the trust boundary); gateway + key + verifier are inside; independent checkpoint store makes missing/truncated packages detectable; fail-closed: a request whose decision cannot be persisted first is refused [documented, our design](../evidence-box.md) | Gateway holds no signing key; sealing away from the gateway via HSM/PKCS#11; forged record = "three independent things held by three different keys" (chain, signature, Merkle root); fully rewritten consistent WAL refused as DivergedLog; honest limits: without --trusted-keys "a forged pack signed with a made-up key validates itself" [documented] | Post-hoc edit, delete, reorder and fork detected "at 100% with zero false positives" in their evaluation; abstract does not state what an agent can alter at recording time [documented] | Entries signed at record time with a machine-enrolled key (COSE_Sign1/ES256 over canonical CBOR), each carries the previous hash, Merkle root over chain tips every 15 min; "tamper-evident, not tamper-proof"; payloads hold only SHA-256 hashes [documented] |
| MCP-specific coverage | Protocol 2025-06-18, one client + one server, stdio; tools/list filtered to approved tools; allow only on name AND input-schema hash match (schema change → deny); idempotency key injection (verified in demo: repeated call applied once); interrupt-after-forward yields outcome `unknown`, never auto-retried [measured: demo run 2026-11-11, `evidence/gateway/policy.py`, `evidence/gateway/proxy.py`] | Deepest MCP coverage of the set: signed tool catalogue authoritative (undisclosed tools refused), argument-level Cedar policy, sampling/elicitation arbitration. Idempotency and unknown outcomes **not documented** — effects record only "ok"/"blocked" [documented] | Not mentioned in the abstract (no MCP, tools/list, idempotency or partial-failure semantics) [not documented] | MCP gateway named as an interception path (details on a page we did not fetch); tool calls and results via hooks; manual commands and unwired tools appear only as "Shadow AI" by name/machine [documented] |
| Offline verification | `peaky-peek-evidence verify`: stdlib + cryptography only; three independent sections (INTEGRITY / COVERAGE / OUTCOMES); exit 0/1/2; unknown key = failure; missing checkpoint = incomplete, integrity still reported [measured: demo run 2026-11-11, `evidence/cli.py`] | `obsign verify` evidence packs against a two-key trusted set (seal + ops); exit code 3 = "consistent but unproven"; sample warns `identity_not_attested` (no TPM enrolment) [documented] | "Any verifier with the disclosed payload and Merkle proof"; export-package/offline flow not described in the abstract [documented / not documented] | Public record-format spec (`golem.team/ledger-format.md`) plus a verify.py to check records "without trusting Golem"; offline verification of exported packages **not documented** on the fetched page [documented / not documented] |
| Key rotation | Customer-managed registry; retired keys stay so historical packages keep verifying after rotation [measured: `tests/evidence/test_verify.py::test_retired_gateway_key_still_verifies_historical_package`] | IdP JWKS hot rotation on unknown kid (bounded, one attempt/second), reloads recorded as config_reload; sealer rotation under a new key id tested [documented] | Not mentioned in the abstract [not documented] | Not mentioned on the fetched page [not documented] |
| Export format / interop | `manifest.json` + `events.ndjson` + signature per execution; AAT/AIVS mapping is a concept table in our docs, **no wire-format export exists yet**; Merkle partial exports deliberately deferred [documented, our docs](../evidence-box.md) | JSON evidence packs; Cedar policies, OIDC/RFC 8693 token exchange, RFC 3161 timestamps, PKCS#11, Merkle with CVE-2012-2459-safe promotion; hand-rolled canonical encoding, JSON is transport only [documented] | Merkle inclusion proofs, 32-byte epoch roots anchored on-chain ($2.30 per 100K events, 100-event epochs); bundle format not described in the abstract [documented / not documented] | Public ledger-format spec + verify script; raw content goes to the customer's bucket, only hashes in the ledger [documented] |

Draft-format references, because export interoperability gates on them: AAT
defines a concrete JSONL wire format with `tool_call`/`tool_response`/
`decision` action types, an optional `tool_server` URI field naming the MCP
server, pre-execution record phases, RFC 8785 JCS hashing, optional
Ed25519/ECDSA/ML-DSA signatures, `key_rotation` lifecycle events and Merkle
inclusion proofs [documented](https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/).
AIVS defines a .tar.gz bundle (hash-chained JSONL + Ed25519 over the chain
hash + manifest + embedded Python-stdlib verifier), signature explicitly
optional, and honestly states "a malicious agent could fabricate actions and
produce a valid chain" [documented](https://datatracker.ietf.org/doc/draft-stone-aivs/).
Both are individual drafts without IETF standing.

## Four-axis comparison

| Axis | Peaky Peek Evidence Box | Obsign | Agent Flight Recorder | Golem |
|---|---|---|---|---|
| Coverage | Decisions + outcomes for tools placed behind the gateway, incl. tools/list binding, idempotency, unknown outcomes; shell/model calls/direct APIs out of scope [measured: demo 2026-11-11] | Broadest MCP method arbitration + argument-level policy + HSM sealing; no idempotency/unknown-outcome model documented [documented] | Generic agent actions with anchoring; MCP-specific semantics absent from abstract [not documented] | Hooks + gateway capture for many coding harnesses; claims-agent workloads outside its documented focus; idempotency not documented [documented / not documented] |
| Integration time | One-command self-contained demo [measured: single run today, exit 0]; durable wiring (gateway key, SQLite ledger, checkpoint store) is a "runtime" section in the launcher JSON (`python3 -m evidence.gateway --config gateway.json`) [measured: tests/evidence/test_gateway_runtime.py, demo run], and the gateway requires access control on the target service — **no real-team integration measured yet** (Week-1 customer conversations pending) | Deployment artifacts exist (docker compose, Keycloak, TLS, backup/restore runbooks); a time figure is **not documented** | **Not documented** (abstract reports runtime cost: ~48 µs median/event, 512 B/event) | Enroll machines per host; a time figure **not documented** |
| Investigation time | Operator journey exists (EvidencePanel maps verified events onto the timeline, integrity kept separate from behavioral score) [measured: repo code + docs]; the "≥ 30% faster on the same audit question" pilot target is a working assumption, **not yet measured** [estimated, plan criteria] | Verify CLI documented; an investigation UI / time-to-answer figure **not documented** in what we fetched | Forensic queries: 1.0 precision on guardrail/delegation lookups vs 0.013/0.077 for unstructured search — their evaluation, our use case untested [documented] | **Not documented** |
| Export usability | Auditor gets package + CLI with three verdict sections and exit codes; runs offline with stdlib + cryptography [measured: demo 2026-11-11]; no standards-format export yet | Evidence packs + offline `obsign verify` with honest "unproven" exit code [documented] | Merkle inclusion proofs; package story absent from abstract [documented / not documented] | Public format spec + verify script; offline package export not documented on fetched page [documented / not documented] |

Tamper-detection depth, ours: the verifier's test suite asserts detection of
modified payload, inserted duplicate, reorder, deleted middle event, truncated
tail (manifest totals), truncated chain with fixed manifest (caught by the
checkpoint), edited checkpoint count, bad/unknown key, and manifest lies
resigned with the right key [measured: `tests/evidence/test_verify.py`]; the
payload-modification class was additionally exercised live in today's demo run.

## Decision-gate readout

The plan's decision rule: if a customer already runs Obsign or similar, test
evidence import + investigation first; if no team can introduce a gateway and
has no signed-evidence source, stop after week one. What this comparison adds:

(a) **Teams already on Obsign.** Obsign covers the same interception point with
stronger sealing assumptions (HSM-held key the gateway never sees, RFC 3161
anchors) and broader MCP method coverage than our pilot scope [documented].
Rebuilding that would duplicate a working Apache-2.0 system. What Obsign does
not document — idempotency handling, `unknown` outcomes, and a coverage verdict
against an independent checkpoint — is narrow. The plan's path is correct:
import their evidence packs into our investigation timeline rather than sell
them a second gateway. That import needs an `evidence.json` adapter (follow-up
1).

(b) **Teams with no recorder.** The gateway path remains the defensible one:
Qin et al. rule out SDK-side signing as evidence-grade for local agents
[documented], Obsign adoption implies Keycloak/Cedar/HSM operations a small
insurance team may not run, and the Agent Flight Recorder abstract does not
document an MCP-specific or offline-package story. Our pilot deliberately
trades breadth (one client, one server, stdio) for the one thing none of the
alternatives document end to end: verifier output feeding an operator's
incident investigation. That trade is only worth keeping if the Week-1
conversations confirm a team can (i) put one tool behind a gateway and (ii)
include a platform engineer and an audit user.

(c) **Stop condition.** Unchanged and now sharper: if nobody can put a tool
behind a gateway, the SDK-signing fallback is not an evidence-grade escape
hatch per Qin et al., and there is no signed-evidence source to import — stop
after week one and return to customer conversations. Do not reinterpret
SDK-ingest signing as a pilot deliverable.

## What we should import vs build

1. **AAT wire-format export (build, small).** AAT is the only draft with an
   explicit MCP `tool_server` field, pre-execution phases and `key_rotation`
   events; our concept table already maps every field
   ([docs/evidence-box.md](../evidence-box.md)). An exporter emitting
   AAT-conformant JSONL alongside the native package is cheap and makes
   packages readable by any AAT verifier. Track draft revisions — it is an
   individual I-D, not a stable standard.
2. **Merkle inclusion proofs for partial/redacted exports (build, on demand —
   as the plan already defers).** Needed the first time an auditor must verify
   a redacted subset without the full chain; AAT specifies single-record
   inclusion proofs and Obsign documents CVE-2012-2459-safe promotion
   [documented]. Both are prior art to copy, not invent.
3. **Obsign evidence-pack import adapter (build only if path (a) materializes).**
   Parse `obsign` evidence packs into `EvidenceTimelineAdapter` rows so
   Obsign-running teams get our investigation view without a second gateway.
   README-level knowledge only — verify the pack format against the Obsign
   repo before writing the parser.
4. **RFC 3161 anchoring for checkpoints (import, optional).** Obsign and AAT
   both layer trusted timestamps; AIVS recommends it explicitly. Anchoring the
   final checkpoint would weaken the "checkpoint signer backdates the summary"
   concern. Defer until a customer asks; the independent store already covers
   the pilot's omission/truncation cases.

## Source access log (2026-11-11)

All six primary sources fetched successfully via their canonical pages:
[Obsign README](https://github.com/obsign/obsign) (README only — code not
inspected line by line), [Agent Flight Recorder abstract](https://arxiv.org/abs/2609.01931)
(full paper not retrieved — interception point, key rotation and package
format remain unverified), [Qin et al. abstract](https://arxiv.org/abs/2609.30266),
[AIVS-01](https://datatracker.ietf.org/doc/draft-stone-aivs/),
[AAT-09](https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/),
[Golem audit-trail guide](https://docs.golem.team/guides/audit-trail) (the
linked MCP-gateway control page was not fetched; `golem.team/ledger-format.md`
was not fetched — cited as the source states it). Our column: demo run of
`examples/09_evidence_box.py` (exit 0, passing + tampered verification) and
source/test inspection in this checkout at server-v0.7.0.
