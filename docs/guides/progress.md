# Implementation progress

**Verified: 2026-09-20. Source/release: `main` at `5a807cf` (v0.4.0).
Focused local validation: `f9dc240`.**

The [roadmap](../ROADMAP.md) owns priorities and acceptance gates. This page is
its concise implementation snapshot, replacing the March claims that cloud
hardening and replay depth were complete. Existing components do not establish a
complete installed, hosted or execution-continuation workflow.

## Completed, within the stated scope

| Capability | What is complete | Evidence / remaining boundary |
|---|---|---|
| CI isolation repair (Q01) | Lifespan engine cleanup, idempotent per-process test setup and correct xdist worker variable | `09ec3dc`; [root-cause record](../../DISCOVERIES.md). Issue #324 is closed |
| CI recovery gate (Q02) | Three consecutive successful Python 3.10/3.11/3.12 matrices and dependency-security jobs | [Run evidence](../research/2026-09-20-planning-evidence.md#delivery-refresh-after-the-fixes); optional integrations and advisory tools are outside this claim |
| Contract gate foundation | Live model fields, enums, frontend HTTP routes/methods and mutation regressions | `ac819c0`; 8 schemas, 3 enums and 72 routes pass. Payload types/nullability remain Q04 |
| Who&When protocol correction (Q05/E0) | Global indexing, exact named metrics, pinned corpus provenance and result manifest | [Artifact](../../benchmarks/results/who_when/2026-09-20-global-protocol.json); native-engine accuracy remains unevaluated |
| Trace model and manual recording | Typed events, decisions, checkpoints, context and recording primitives | [Core audit](../research/2026-09-19-core-status.md); complete delivery is separate |
| Recorded-event investigation | Session inspection, replay/filtering/comparison and recorded-event stepping | [Core audit](../research/2026-09-19-core-status.md); these operations do not resume agent execution |
| Semantic restore server API | Copies a source prefix with remapped references, restore marker and checkpoint | [Core audit](../research/2026-09-19-core-status.md); SDK integration remains partial |
| Deterministic analysis surfaces | Audit, claim verification, evidence graph, narratives, drift and advisory trust bands | [Intelligence audit](../research/2026-09-19-intelligence-status.md); usefulness and calibrated probabilities are separate claims |

[v0.4.0](https://github.com/acailic/agent_debugger/releases/tag/v0.4.0) was
published during this refresh by concurrent release work. Its publish workflow
succeeded; this does not replace Q12's clean-install acceptance.

## Partial or not yet verified

| Area | Current limitation | Roadmap work |
|---|---|---|
| SDK local first run | Standalone no-key initialization does not select HTTP delivery; configuration and transport exist | Q09 / W02 |
| Delivery recovery | Retry and partial-write recovery exist; pending memory batches are not crash-durable | W02 / W11 |
| SDK semantic restore | Existing SDK restore does not use the complete server restore contract | Q10 / W04 |
| Framework continuation | Generic runtime continuation and cached tool/model replay are not implemented | W04 |
| Hosted identity and ownership | Auth/repository primitives exist; route, checkpoint-reference, stream and derived-data coverage is incomplete | Q06 / W10 |
| Breakpoint conditions | Custom Python expressions still evaluate in the server context | Q07 / W10 |
| Redaction | Persisted event filtering exists; consistent live-buffer, checkpoint and metadata policy coverage remains | Q08 / W10 |
| Clean installed artifacts | SDK/server package definitions and bundled UI paths exist; wheel/container first-run and restart proof is missing | Q12 / W11 |
| Redis/PostgreSQL | Redis has concrete constructor/URL wiring gaps; real-service database migration/recovery is unverified | Q13 / W11 |
| Browser workflows | API scenarios and component tests exist; seeded browser acceptance in CI remains open | Q11 / W08 |
| Failure memory and clustering | Components exist; measured retrieval quality, tenant scope and retention/deletion lifecycle remain | W06 / W10 / W11 |
| Framework and OTel coverage | Adapters/exporter setup exist; real version/capability tests and native-event span wiring remain | Q15 / W07 |
| Teams, billing and adoption | Hosted product surfaces are not implemented; repeat use and willingness to pay are unmeasured | Q16 / W12 |

The docs/site/examples already exist. The old plan's “build a landing page” and
“start comparison/clustering” labels are not a reliable inventory. Keep the
existing surfaces and finish their validated workflows.

## Next work

Follow the [implementation queue](../ROADMAP.md#first-implementation-queue) and
[file-level delivery briefs](../ROADMAP.md#next-delivery-slices). Begin by reviewing
one threshold-test PR (Q03); #325 is the candidate, not an approved or merged change.
The worker-variable change in #323 is already on main and needs reconciliation.
The next code slices address custom predicates, hosted boundaries/redaction and
local delivery. Contract, restore, browser and package gates complete the first
useful investigation journey before pilot recruitment or hosted product expansion.

## Validation and maintenance

Fresh local validation: **56 tests passed**, the Who&When CLI self-test passed,
and the contract checker reported **8 schemas / 3 enums / 72 routes, no drift**.
Commands, run links and limits are in the
[delivery evidence](../research/2026-09-20-planning-evidence.md#delivery-refresh-after-the-fixes).
The complete suite was not rerun locally during this documentation refresh;
its delivery evidence is the inspected GitHub runs. No browser, clean package,
container or production deployment was exercised.

Update this page when a roadmap acceptance gate passes or new evidence changes a
capability's scope. Link the commit and validation artifact. Accepted ADRs record
decisions; they do not prove delivery. Keep historical audit dates visible.
