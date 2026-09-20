# Planning status report — 2026-09-20

**Verified source:** local and remote `main` at `f832204`.
**Latest checked release:** v0.4.0 at `5a807cf`; later changes are on main only.

Local no-key delivery, SDK semantic restore and the configured redaction boundary
are now implemented and tested. PR #325 has passed local review and focused tests.
The failed secret scan is diagnosed and corrected locally. The next work is to
confirm that correction in CI, complete hosted/predicate acceptance, and verify
installed artifacts and browser workflows.

The [roadmap](../ROADMAP.md) owns priorities. This report replaces older completion
claims, including the March cloud-readiness claim and the earlier three-item tally.
Completion here is scoped to an observed behavior and its evidence.

## What is done

| Deliverable | Evidence | Boundary |
|---|---|---|
| Q01/Q02 — CI isolation repair and recovery gate | `09ec3dc` and [three-run evidence](../research/2026-09-20-planning-evidence.md#delivery-refresh-after-the-fixes) | Issue #324 closed; later workflow failures are tracked separately |
| Q04 foundation — field/enum/route contracts | `ac819c0`; earlier 8-schema/3-enum/72-route check | Real payload structural types/nullability remain |
| Q05 — benchmark protocol correction | `9c2bd04`, [manifest](../../benchmarks/results/who_when/2026-09-20-global-protocol.json) | Standalone heuristic measurement; native-engine effectiveness remains open |
| Q08 — configured redaction | `7f95046`; fresh sentinel boundary tests | Existing database/buffer/SSE/checkpoint/metadata/config/spill paths; opt-in policy |
| Q09 — explicit no-key endpoint delivery | `bd37ce0`; fresh TCP and real-server tests | Disabled/no-endpoint and offline behavior covered; installed-wheel onboarding remains Q12 |
| Q10 — SDK semantic restore | `e61f04d`; fresh real-server source-immutability/provenance tests | Authenticated POST and returned IDs; legacy fallback labeled; no agent execution |
| Q06/Q07/Q13 foundations | Cluster scope/checkpoint session check; constrained predicate interpreter; Redis wiring/reconnect | Delivered components, with original acceptance still incomplete below |

## What is not complete

| Slice | Remaining acceptance | Evidence / next step |
|---|---|---|
| Q03 | Actual PR-head CI, reviewed merge and duplicate cleanup | [#325 review](2026-09-20-pr325-review.md): no substantive spec blocker; two small standards notes; pre-existing coroutine warning recorded |
| Q04 | Serialized payload types, required fields and nullability | Extend existing checker and prove incompatible payload mutations fail |
| Q06 | Missing hosted credentials, unscoped analytics, real hosted startup, checkpoint event/session consistency and full negative route matrix | Existing ASGI tests intentionally allow anonymous cloud access; they do not meet the original rejection gate |
| Q07 | Pre-mutation predicate creation/import validation, API 4xx errors and aggregate evaluation budgets | Safe probe reproduced acceptance now and rejection only during evaluation |
| Q11 | Three actual browser journeys, including restore provenance and delayed navigation | SDK/API tests do not establish UI completion |
| Q12 | Clean SDK/server installation, bundled UI, migrations and persistent non-root container restart | Published packages have not been exercised outside the checkout in this audit |
| Q13 | Real Redis service run that cannot silently skip | Both Redis test modules skipped here because the client dependency is unavailable |
| Q14–Q16 | Regression-case workflow, supported framework versions and measured pilot outcomes | Preserve existing implementations; expand after their dependencies pass |

Q06/Q07/Q13 are **PARTIAL**, correcting the overly broad DONE labels from the
last delivery update. Keep the delivered fixes; complete the remaining acceptance
under those same IDs. Q08 redaction does not resolve Q06 authentication gaps.

## Repository workflow status

[Main CI](https://github.com/acailic/agent_debugger/actions/runs/35483421378) on
`f832204` passed all three Python jobs and dependency security. The separate
[secret scan](https://github.com/acailic/agent_debugger/actions/runs/35483421310)
failed on one synthetic redaction fixture. Exact historical fingerprints now pass
the failed push range in Gitleaks 8.24.3 and 8.30.1; both still reject a different
synthetic value at the same file/line in a new commit. The local patch has not been
validated by a new GitHub run. A complete-history scan still reports 19 older
findings, classified as historical test/documentation fixtures and kept separate
from this correction. See the
[diagnosis and evidence](../research/2026-09-20-delivery-followup.md#secret-scan-diagnosis-and-local-correction).

The v0.4.0 release and its publication jobs succeeded earlier. That history does
not establish current installed-package behavior or make every later workflow green.

## PR review outcome

#325 covers all nine requirements of #311, adds useful fallback cases, and passed
38 warning-strict alert tests with 100% coverage of `collector.alerts.base`.
Ruff passed. Prefer it over duplicate #321/#322. Resolve the small commit/type-hint
notes, add chosen robustness cases, and explicitly record the existing coroutine
warning decision before refreshing the actual PR branch and obtaining new checks.

The sync fallback warning is pre-existing; closing a coroutine inside the test
only keeps that test clean. No production fix is implied. No PR was approved,
commented on, merged or closed by this planning task. #323's worker-variable
correction is already on main; reconcile that superseded PR separately.

## Written next plans

The [delivery briefs](../ROADMAP.md#next-delivery-slices) now distinguish delivered
Q09 scope from remaining Q06/Q07 work. They include concrete Q04 contract steps,
a clean-install/container plan for Q12, and a seeded browser/restore plan for Q11.
File scope, dependencies, observable outcomes and failure artifacts are specified.

The immediate order is delivery/CI confirmation of the scan correction and Q03
handoff, then Q06/Q07 closure. Retain the older scan baseline under W01.
Q04 and Q12 are independent local-workflow slices; Q11 follows the response contract
and reuses delivered semantic restore. Keep one delivery slice active per maintainer.

## Validation and maintenance

- `f832204` plus the exact #325 file: **86 tests passed**, including no-key TCP
  delivery, real-server SDK restore, redaction and the current ASGI tenant matrix.
  Two dependency deprecation warnings were emitted.
- Earlier `e8e6696` selection: **123 passed, two Redis modules skipped**.
- PR-specific selection: **38 passed**, **100% targeted coverage**, Ruff passed.
- Secret-scan correction: failed-range and negative-control checks pass in two
  scanner versions; **43 redaction tests passed**. Full history is not clean.

Counts overlap and are not a unique full-suite total. Detailed commands and
scope are in the [follow-up evidence](../research/2026-09-20-delivery-followup.md).
No full local suite, browser, installed-artifact, Docker or Redis-service run was
performed. Update this report and the roadmap together after an acceptance gate,
changed PR head, workflow finding or release. Preserve each audit's exact revision.
