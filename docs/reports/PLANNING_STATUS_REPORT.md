# Planning status report — 2026-09-20

**Audience:** project maintainers and contributors.

**Verified source/release:** `main` at `5a807cf` (v0.4.0).

**Focused local validation:** `f9dc240`, before the concurrent release's version/documentation changes.

CI recovery and benchmark-protocol repair are complete. The contract checker has
also landed. The next work is to consolidate existing test PRs, close the concrete
hosted-boundary gaps, and complete the local capture → evidence → restore journey.
[v0.4.0](https://github.com/acailic/agent_debugger/releases/tag/v0.4.0) was published
by concurrent release work during this refresh; issue #324 is now closed.
The release's [CI](https://github.com/acailic/agent_debugger/actions/runs/35480454666)
and [SDK/server publication jobs](https://github.com/acailic/agent_debugger/actions/runs/35480455352)
passed; clean-install behavior still needs Q12 validation.

This report replaces the 2026-03-24 report. Its “100% cloud-ready,” blanket replay
completion and fixed SaaS-launch schedule were not supported by the later audit.
The [roadmap](../ROADMAP.md) remains the only priority queue; this report summarizes
evidence and links to the detailed implementation plans.

## What is done

| Item | Evidence | Exact completion boundary |
|---|---|---|
| Q01 — xdist failure diagnosis and repair | `09ec3dc`, [DISCOVERIES](../../DISCOVERIES.md) | Three isolation/lifecycle causes fixed; earlier serial and twelve local parallel runs recorded |
| Q02 — CI recovery observation | [Run 1](https://github.com/acailic/agent_debugger/actions/runs/35479465055), [run 2](https://github.com/acailic/agent_debugger/actions/runs/35479673383), [run 3](https://github.com/acailic/agent_debugger/actions/runs/35479946771) | Each passed Python 3.10/3.11/3.12 jobs and dependency security; three-run gate met |
| Q04 foundation — contract CI | `ac819c0`; fresh check passes 8 schemas, 3 enums, 72 routes | Field/enum/route checking and mutation tests shipped; payload/nullability coverage is still planned |
| Q05/E0 — Who&When correction | `9c2bd04` and [versioned manifest](../../benchmarks/results/who_when/2026-09-20-global-protocol.json) | Corrected global-index protocol and explicit metrics; native audit-engine effectiveness remains unmeasured |
| Earlier debugger capabilities | [Core](../research/2026-09-19-core-status.md) and [intelligence](../research/2026-09-19-intelligence-status.md) audits | Recording, evidence inspection, deterministic analysis, event replay and server semantic restore exist |

These are bounded completions, not a project-wide percentage. Three of sixteen
queue items are complete; several others contain substantial delivered components.
Counting modules, tests or checkboxes would conceal the remaining integration gaps.

## What is still open

| Area | Remaining result needed |
|---|---|
| Threshold tests (Q03) | One reviewed, passing merged PR. #321/#322/#325 all add the same absent-on-main test file; review #325 first |
| Contract coverage (Q04) | Real serialized responses validated for structural types, required fields and nullability; deliberate drift must fail CI |
| Hosted boundaries (Q06–Q08) | Real hosted-mode/two-tenant tests, checkpoint ownership, scoped derived data, no Python breakpoint evaluation and consistent redaction |
| Local capture and SDK restore (Q09/Q10) | No-key standalone SDK produces persisted data; SDK semantic restore uses authenticated server results and provenance |
| Browser and installed artifacts (Q11/Q12) | Seeded browser journey plus clean wheel/container startup and persistent restart |
| Optional scale/runtime work (Q13/Q15, W04/W11) | Real Redis/framework compatibility, PostgreSQL recovery, retention execution and one controlled continuation |
| Regression lab and pilot (Q14/Q16) | Sanitized reproducible incident comparison, then measured first value and repeat use |

See the [current capability snapshot](../guides/progress.md) for scope and the
[roadmap](../ROADMAP.md#next-delivery-slices) for file-level steps and acceptance.
No customer, benchmark-effectiveness or hosted-readiness claim follows from green CI.

## Tracker reconciliation

- **#324 is closed:** its code fix and CI recovery are delivered; closure was
  verified in the final tracker refresh.
- **#323 remains open:** the worker-variable correction is already in `09ec3dc`.
  It needs reconciliation as superseded, not another implementation.
- **#311 remains open:** none of the three threshold-test PRs is merged. #325's
  twelve cases make it the first review candidate; refresh against main, review
  async fallback/argument coverage and obtain new required checks.
- **#306–310 remain open:** evaluate dependency changes separately using recovered CI.

All tracker actions by this planning task were read-only. Concurrent release work
closed #324 and published v0.4.0; those changes were preserved and rechecked.
This task did not create, comment on, review, merge or close issues/PRs.
Old PR failures predate main's
repairs and do not establish whether a refreshed branch will pass.

## Next delivery plan

The [roadmap queue](../ROADMAP.md#first-implementation-queue) specifies sequence.
The [next delivery briefs](../ROADMAP.md#next-delivery-slices) now cover Q03, Q07,
Q06, Q09 and Q04, including touched modules, implementation steps and acceptance.
Follow-on handoffs cover redaction, restore, browser tests, packaging and regression
cases. Q07 can disable custom expressions independently; Q06 is required for its
hosted acceptance evidence. Q04 and Q09 can proceed on recovered main.

Keep one delivery slice plus one research experiment active per maintainer.
Additional framework support, teams/billing and runtime execution wait for their
specific evidence gates, rather than the superseded ten-week schedule.

## Validation and maintenance

Fresh local checks:

- 56 contract/benchmark tests passed in 4.11 seconds.
- Contract checker passed: 8 schemas, 3 enums, 72 routes, no drift.
- Offline Who&When CLI self-test passed.

[Delivery evidence](../research/2026-09-20-planning-evidence.md#delivery-refresh-after-the-fixes)
contains commands, commits, tracker observations and run links. Full CI results
were inspected remotely; no full local suite, browser, installed wheel, container
or production deployment was run for this refresh. Advisory checks and excluded
optional integrations remain outside the green-CI claim.

Refresh this report after a queue acceptance gate, a merged PR or a material
failed validation. Update the roadmap and progress page together. Preserve dated
audit evidence and distinguish implementation completion from tracker closure.
