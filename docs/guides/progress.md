# Implementation progress

**Verified: 2026-09-20. Source: `main` at `f832204`.
Release v0.4.0 remains `5a807cf`; later source changes are listed below.**

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
| Semantic restore server API and SDK (Q10) | SDK calls authenticated semantic restore, adopts returned IDs/provenance and labels legacy fallback; source remains unchanged | `e61f04d`; real-server restore tests pass. Browser integration and agent continuation remain separate |
| Explicit no-key endpoint delivery (Q09) | Standalone configured endpoint delivers persisted traces; disabled/no-endpoint controls and offline behavior pass | `bd37ce0`; installed-artifact onboarding remains Q12 |
| Configured redaction boundaries (Q08) | Stored event fields/metadata, live fan-out, checkpoints, session config and NDJSON spill share the configured policy | `7f95046`; policy is opt-in. Auth and future sink coverage remain separate |
| Deterministic analysis surfaces | Audit, claim verification, evidence graph, narratives, drift and advisory trust bands | [Intelligence audit](../research/2026-09-19-intelligence-status.md); usefulness and calibrated probabilities are separate claims |

[v0.4.0](https://github.com/acailic/agent_debugger/releases/tag/v0.4.0) was
published with successful SDK/server publication jobs. Later Q06–Q10/Q13 changes
are on main; they are not part of that tag. Publication does not replace Q12's
clean-install acceptance.

## Partial or not yet verified

| Area | Current limitation | Roadmap work |
|---|---|---|
| Delivery recovery | Retry and partial-write recovery exist; pending memory batches are not crash-durable | W02 / W11 |
| Framework continuation | Generic runtime continuation and cached tool/model replay are not implemented | W04 |
| Hosted identity and ownership | Cluster/session ownership fixes and ASGI matrix landed; absent-key rejection, analytics scope, event/session consistency and real hosted startup remain | Q06 / W10 |
| Breakpoint conditions | Constrained interpreter replaces eval; creation/import still accept invalid predicates and evaluation needs complete work/output budgets | Q07 / W10 |
| Clean installed artifacts | SDK/server package definitions and bundled UI paths exist; wheel/container first-run and restart proof is missing | Q12 / W11 |
| Redis/PostgreSQL | Redis constructor/URL/reconnect fixes landed; optional Redis tests skipped locally. Real-service acceptance and PostgreSQL recovery remain unverified | Q13 / W11 |
| Browser workflows | API scenarios and component tests exist; seeded browser acceptance in CI remains open | Q11 / W08 |
| Failure memory and clustering | Components exist; measured retrieval quality, tenant scope and retention/deletion lifecycle remain | W06 / W10 / W11 |
| Framework and OTel coverage | Adapters/exporter setup exist; real version/capability tests and native-event span wiring remain | Q15 / W07 |
| Teams, billing and adoption | Hosted product surfaces are not implemented; repeat use and willingness to pay are unmeasured | Q16 / W12 |

The docs/site/examples already exist. The old plan's “build a landing page” and
“start comparison/clustering” labels are not a reliable inventory. Keep the
existing surfaces and finish their validated workflows.

## Next work

Follow the [implementation queue](../ROADMAP.md#first-implementation-queue) and
[file-level delivery briefs](../ROADMAP.md#next-delivery-slices). #325 now has a
[passing local review](../reports/2026-09-20-pr325-review.md); branch refresh,
required CI and merge remain Q03. Deliver the locally verified secret-scan
correction, confirm a new GitHub run and finish Q06/Q07 acceptance.
Q04 payload contracts and Q12 installed artifacts are
ready to proceed; Q11 must connect the delivered SDK restore to a browser journey.
The worker-variable change in #323 is already on main and needs reconciliation.

## Validation and maintenance

Latest local validation: **86 tests passed** on `f832204` plus the exact #325 test
file, including real TCP delivery and SDK restore. A separate earlier selection
passed **123 stepper tests**, with **two Redis modules skipped**. PR-specific
validation passed **38 alert tests** with **100% targeted module coverage** and
Ruff; these selections overlap. [Commands and limits](../research/2026-09-20-delivery-followup.md).

Latest main CI passed; the separate scan failed on one synthetic fixture. A narrow
local correction passes the failed range in two Gitleaks versions, retains
new-commit detection and passes **43 redaction tests**. GitHub confirmation and the
separate 19-finding historical baseline remain open. No full local suite, browser,
clean package, container or Redis service was exercised. Earlier contract/benchmark
results remain in the [dated evidence](../research/2026-09-20-planning-evidence.md).

Update this page when a roadmap acceptance gate passes or new evidence changes a
capability's scope. Link the commit and validation artifact. Accepted ADRs record
decisions; they do not prove delivery. Keep historical audit dates visible.
