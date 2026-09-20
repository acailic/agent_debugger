# Planning evidence: delivery state, standards, and strategic choices

> **Later verification:** the [delivery follow-up at `f832204`](2026-09-20-delivery-followup.md)
> supersedes current-state claims below for Q06–Q10/Q13 and workflow health.
> This note preserves the earlier audit, release and test evidence at its named revisions.

Audit started 2026-09-19 and completed 2026-09-20 (Europe/Belgrade).
Local baseline: `main`, commit `3597b6b`. This is a research snapshot, not a
release certification. [ROADMAP](../ROADMAP.md) owns priorities; these notes
record the evidence behind them. The [delivery refresh](#delivery-refresh-after-the-fixes)
below supersedes the original delivery snapshot after fixes landed on main.

## Evidence map

| Question | Primary evidence | What it establishes |
|---|---|---|
| What captures and restores real traces? | [Core audit](2026-09-19-core-status.md) | SDK, transports, adapters, replay, checkpoint and execution boundaries |
| Which analysis capabilities exist and what is measured? | [Intelligence audit](2026-09-19-intelligence-status.md) | Audit engine, research backlog, evaluation methodology and focused checks |
| Is the platform ready for shared hosting? | [Platform audit](2026-09-19-platform-status.md) | UI, packaging, tenant and privacy paths, storage and quality gates |
| Is delivery currently healthy? | GitHub observations below | Current issue/PR/run states, independent of historical test-count claims |
| Which external patterns are useful? | Official documentation below | Design inputs; not evidence that Peaky Peek implements them |

## Original GitHub delivery snapshot (historical)

Read-only verification through `gh-axi issue list`, `pr list`,
`issue view 324 --full`, `issue view 311`, `pr view 323`, `pr view 325`,
`run list`, and `run view 34989987605` on 2026-09-19.

| Item | Verified status | Planning consequence |
|---|---|---|
| [Issue #324](https://github.com/acailic/agent_debugger/issues/324) | **OPEN / BLOCKED delivery**: reported full-suite xdist instability | Diagnose actual worker/database lifecycle before generating more test PRs. The issue's reported successful serial run is historical evidence, not a fresh run from this audit. |
| [Main CI run 34989987605](https://github.com/acailic/agent_debugger/actions/runs/34989987605) | **FAILED** on `3597b6b`; all three Python jobs and dependency-security job failed | Inspect each job independently. The observed failure does not establish that every job shares the same root cause. |
| [PR #323](https://github.com/acailic/agent_debugger/pull/323) | **OPEN, unmerged**, 2 passed / 4 failed checks at lookup | Worker-variable fix is partial; its description explicitly says it does not fix the underlying flake. |
| [Issue #311](https://github.com/acailic/agent_debugger/issues/311) | **OPEN**; threshold-resolution tests requested | Track the test work separately from infrastructure recovery. |
| [PR #321](https://github.com/acailic/agent_debugger/pull/321), [#322](https://github.com/acailic/agent_debugger/pull/322), [#325](https://github.com/acailic/agent_debugger/pull/325) | **OPEN, overlapping scope**; #325 reports 12 added tests and has failing checks | Select one implementation after review; do not count proposed tests as shipped to main. No PR was closed or merged during this audit. |
| Dependency PRs #306–310 | **OPEN** in the PR list | Review separately after obtaining a useful CI signal; an open bump is not an installed upgrade. |

The working tree already contained changes to CI, API-contract checking, frontend
requests/types, README and DISCOVERIES, plus untracked contract tests. They are
**local work in progress**, not new work from this planning task and not proof of
a merged release. The [platform audit](2026-09-19-platform-status.md) distinguishes
this boundary. No GitHub writes were performed.

## Delivery refresh after the fixes

Focused checks ran on 2026-09-20 against clean local and remote `main` at `f9dc240`,
before the documentation edits. Concurrent work then released `5a807cf` as
v0.4.0 (version/changelog/documentation changes) and closed #324; final source and
tracker observations incorporate those changes. GitHub observations used read-only
`gh-axi` run, issue and PR views/diffs/checks. Source inspection establishes what
landed; focused checks below establish only their tested scope.

### Completed work

| Deliverable | Commit / artifact | Verified boundary |
|---|---|---|
| Q01: full-suite xdist isolation repair | [`09ec3dc`](https://github.com/acailic/agent_debugger/commit/09ec3dcfaa4f29105e61dacc26b256230796cb85), [root causes](../../DISCOVERIES.md) | Lifespan engine cleanup, per-process conftest initialization and worker naming corrected. Earlier twelve local parallel runs are recorded evidence, not reruns in this refresh |
| Q02: three consecutive green CI matrices | [`423ab82` run](https://github.com/acailic/agent_debugger/actions/runs/35479465055), [`07efd4e` run](https://github.com/acailic/agent_debugger/actions/runs/35479673383), [`2e45fe7` run](https://github.com/acailic/agent_debugger/actions/runs/35479946771) | All three Python jobs (3.10/3.11/3.12) and dependency security succeeded in each run. Q02's observation gate is met |
| Contract gate foundation | [`ac819c0`](https://github.com/acailic/agent_debugger/commit/ac819c03de43e2e62b5a5c6ba080d58992662b87) | Live Pydantic field sets, SDK enum unions, TypeScript AST route/method extraction, failing-on-drift behavior and mutation tests committed. Q04 payload/type/nullability extension remains |
| Q05/E0: corrected Who&When protocol | [`9c2bd04`](https://github.com/acailic/agent_debugger/commit/9c2bd04537ec1c9c696702b8ba974802804485e7), [published result manifest](../../benchmarks/results/who_when/2026-09-20-global-protocol.json) | Global indexing, pinned source, explicit denominators and repaired self-test. Artifact contains 184 rows: agent 49/184, step 28/184, joint 28/184, abstentions 86/184; zero invalid indices and six reported speaker mismatches |
| Frontend dependency audit repair | `423ab82`, successful dependency jobs above | The prior high-severity browserslist audit failure was cleared. Advisory tools remain advisory |

CI still uses `-k "not integration"`; its green status is not proof of all optional
integration modes. Pyright, Bandit, dependency review and Codecov upload remain
advisory/nonblocking under the inspected workflow. No browser, Docker, installed
wheel, Redis or PostgreSQL acceptance run was added by this refresh. The newer
[`f9dc240` run](https://github.com/acailic/agent_debugger/actions/runs/35480122316)
also completed successfully; Q02 had already been met by the prior three runs.

[v0.4.0](https://github.com/acailic/agent_debugger/releases/tag/v0.4.0) is published
on GitHub, and its [PyPI publish workflow](https://github.com/acailic/agent_debugger/actions/runs/35480455352)
reports both SDK and server publication jobs successful. Clean installed-package
behavior was not checked. Release-commit
[CI](https://github.com/acailic/agent_debugger/actions/runs/35480454666) also
completed successfully at final lookup: Python 3.10/3.11/3.12 and dependency
security all passed. This adds release evidence beyond the completed Q02 gate.

### Tracker state and remaining review

| Item | State at refresh | Next action |
|---|---|---|
| [#324](https://github.com/acailic/agent_debugger/issues/324) | CLOSED at final lookup; implementation and CI recovery gates complete | No remaining implementation or tracker task under Q01/Q02 |
| [#323](https://github.com/acailic/agent_debugger/pull/323) | OPEN; its functional worker-variable change is already on main | Reconcile as superseded; do not implement or merge the same correction again |
| [#311](https://github.com/acailic/agent_debugger/issues/311) | OPEN; dedicated threshold test file absent from main | Complete one reviewed test PR before closing |
| [#321](https://github.com/acailic/agent_debugger/pull/321) | OPEN; 9 tests; only GitGuardian result shown | Compare overlap; no full CI success established |
| [#322](https://github.com/acailic/agent_debugger/pull/322) | OPEN; 9 tests; three Python jobs and dependency security failing | Compare overlap; old checks predate recovered main |
| [#325](https://github.com/acailic/agent_debugger/pull/325) | OPEN; 12 tests; Python 3.11 passed, Python 3.10/3.12 and dependency security failed | First review candidate because it covers more fallback cases; update against main and obtain fresh CI before approval |

All three threshold PRs add `tests/alerts/test_alert_deriver_base.py`. #321's
async-getter fallback test leaves a coroutine unawaited; #322 suppresses the
warning; #325 closes test-created coroutines. None proves the production sync
fallback avoids that warning. Review this explicitly and fill any missing async
fallback/argument-forwarding cases. #325's
[old CI failure](https://github.com/acailic/agent_debugger/actions/runs/35403101890)
does not establish whether it passes on the repaired base.

Dependency PRs #306–310 also remain open. This planning task performed no GitHub
writes. Concurrent release work closed #324 and published v0.4.0; the final
read-only refresh verified those changes.

### Fresh local validation

```bash
.venv-ci/bin/python scripts/hooks/check_api_contract.py
# pass: 8 schemas, 3 enums, 72 routes; no drift

.venv-ci/bin/python scripts/benchmark_who_when.py --self-test
# self-test OK; two fixture records, global indexing

.venv-ci/bin/python -m pytest -q tests/contract \
  tests/test_benchmark_who_when_cli.py tests/test_fetch_who_when.py \
  tests/test_who_when.py --maxfail=3
# 56 passed in 4.11s
```

The full benchmark corpus was not rerun; its recorded rates above come from the
committed manifest. It evaluates a standalone text-marker heuristic, not the
native audit/causal engine. The local self-test result is a fixture check, not a
replacement corpus score.

### Source-checked gaps retained in the plan

- `TraceContext.__aenter__` still requires `config.api_key` to install transport
  hooks: Q09's standalone no-key delivery remains partial.
- Hosted auth still falls back to local identity without credentials; clustering
  hard-codes local scope; analytics and checkpoint reference checks remain Q06.
- Custom stepper conditions still use `eval`, including a state-import path:
  Q07 can reject this capability before the broader Q06 work finishes.
- The contract extractor still checks names/unions/routes, not payload structural
  types or nullability: the completed foundation does not close Q04.

The [next delivery briefs](../ROADMAP.md#next-delivery-slices) specify file scope,
implementation steps and acceptance. Earlier broad capability audits remain
historical evidence; only the named delivery/source findings were refreshed here.

## External research

Sources were accessed on 2026-09-19. Findings below are deliberately narrow;
adoption, market share, pricing and willingness to pay were not measured.
Agent Reach's configured Exa lookup failed because that MCP server was absent;
web lookup and its Jina Reader route supplied the official documentation.

### OpenTelemetry: interoperability needs a versioned mapping

The official GenAI attribute registry includes agent, workflow and tool operation
names marked Development. The former GenAI agent-spans page now points readers
to a separate GenAI semantic-conventions repository. Treat that mapping as a
versioned compatibility boundary, not a permanently fixed field list.
[Attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/),
[migration notice](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/).

**Proposed implication:** add a pinned schema mapping, round-trip fixtures,
preserved unknown attributes, and explicit provenance for imported spans.
Do not infer native decisions or evidence links from generic spans when the
source did not capture them. Exporter initialization alone is not traced-event
interoperability; see the [core audit](2026-09-19-core-status.md).

### LangGraph: restored data and resumed execution are different contracts

LangGraph documents checkpoints for thread state and stores for cross-thread
memory. Its time-travel API can resume or fork from a checkpoint; nodes after
that checkpoint execute again, including model and API calls, and can produce
different results. A branch preserves the original history.
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence),
[time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel).

**Proposed implication:** keep Peaky Peek's inspect, restore, cached replay and
live execution modes explicit. Implement one adapter-backed continuation before
offering a generic execution interface. Require tool-effect classification,
approval and cost limits for new execution; capture divergence as evidence.
This is a design proposal, not a claim of current integration support.

### Langfuse: versioned datasets and comparable experiments are a baseline

Langfuse documents datasets built from production traces, dataset-item versions,
and experiment comparisons. Its comparison guidance calls for the same dataset
version and evaluator definitions, with application/model/evaluator versions
recorded alongside results.
[Datasets](https://langfuse.com/docs/evaluation/experiments/datasets),
[comparison guidance](https://langfuse.com/docs/evaluation/experiments/compare-experiments).

**Proposed implication:** develop a local incident-to-regression workflow that
freezes data, evaluator and application provenance. Differentiate through
inspectable evidence and controlled reruns, then measure operator benefit.
Do not describe datasets or experiment comparison alone as unique to this repo.

## Assumptions to test before expanding investment

| Hypothesis | Smallest useful study | Decision rule proposed for the roadmap |
|---|---|---|
| Evidence inspection reduces diagnosis time | Five consenting developers investigate the same seeded failures with their existing workflow and Peaky Peek; counterbalance order | Continue UX investment if median time falls without lower diagnosis accuracy; report individual outcomes and sample size |
| A saved failure is useful as a regression | Three pilot projects each turn two real incidents into sanitized reproducible cases | Build orchestration only if cases are rerun and catch a real candidate regression |
| Framework-specific continuation is worth maintenance | One LangGraph flow with reads, a simulated write and an interrupted branch | Expand adapters only after restore/continuation fidelity and side-effect handling are demonstrated |
| Shared hosting is wanted | Interview pilot teams about collaboration, deployment and data constraints | Cloud/teams scope follows repeat demand and platform gates, not the old ten-week calendar |
| A paid offer is justified | Obtain explicit willingness-to-pay feedback against concrete retention/support/team capabilities | Revisit pricing ADR; do not reuse superseded prices as commitments |

These are future studies. No customers were contacted, deployments changed,
payments collected, or user data uploaded as part of this research.
