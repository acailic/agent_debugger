# Planning evidence: delivery state, standards, and strategic choices

Audit started 2026-09-19 and completed 2026-09-20 (Europe/Belgrade).
Local baseline: `main`, commit `3597b6b`. This is a research snapshot, not a
release certification. [ROADMAP](../ROADMAP.md) owns priorities; these notes
record the evidence behind them.

## Evidence map

| Question | Primary evidence | What it establishes |
|---|---|---|
| What captures and restores real traces? | [Core audit](2026-09-19-core-status.md) | SDK, transports, adapters, replay, checkpoint and execution boundaries |
| Which analysis capabilities exist and what is measured? | [Intelligence audit](2026-09-19-intelligence-status.md) | Audit engine, research backlog, evaluation methodology and focused checks |
| Is the platform ready for shared hosting? | [Platform audit](2026-09-19-platform-status.md) | UI, packaging, tenant and privacy paths, storage and quality gates |
| Is delivery currently healthy? | GitHub observations below | Current issue/PR/run states, independent of historical test-count claims |
| Which external patterns are useful? | Official documentation below | Design inputs; not evidence that Peaky Peek implements them |

## GitHub delivery snapshot

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
