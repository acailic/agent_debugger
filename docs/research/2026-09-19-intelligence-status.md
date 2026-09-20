# Intelligence, audit, and research status audit

Audit started 2026-09-19 and completed 2026-09-20 (Europe/Belgrade), against
`3597b6b` plus the existing working tree. This is an evidence note supporting
the [living roadmap](../ROADMAP.md), not a competing delivery plan. No product
code was changed; existing user changes were preserved.

The repository has substantial working audit and research infrastructure.
Its principal gap is independent validation and completion of operator
workflows. Several old “not started” labels overlook implemented features;
several old “full” labels overstate what tests and benchmarks establish.

## Status meaning

- **DONE**: the explicitly named implementation slice exists and has inspected
  tests or a directly observed execution result. This does not certify a whole
  product theme or prove research effectiveness.
- **PARTIAL**: useful implementation exists, with the missing integration,
  semantics, evaluation, or workflow stated explicitly.
- **NOT STARTED**: no implementation of the narrowly named proposed capability
  was found in the searched SDK, collector, API, frontend, or test sources.
- **UNVERIFIED**: a claim requires evidence beyond the source inspection and
  targeted execution performed here.

“Tests exist,” “tests passed in this audit,” and “historically reported” are
separate evidence levels. Test names and old documentation are not proof that
a scientific claim is true.

## Capability register

| Capability and scoped status | Evidence present | What remains or limits the claim |
|---|---|---|
| **DONE — deterministic audit report, claim taxonomy, component scores** | [Audit engine](../../collector/audit/audit_engine.py), [audit routes](../../api/audit_routes.py), [audit tests](../../tests/test_audit_engine.py); audit tests passed in this audit. | **UNVERIFIED** as a calibrated probability of correctness. The trust score is an explicit weighted formula. Claim verification uses trace structure and evidence metadata, rather than proving natural-language entailment. |
| **DONE — evidence provenance, citation coverage, decision justification** | The engine builds an evidence graph, flags uncited facts, calculates `evidence_coverage`, and returns decision justifications. [EvidenceGraphPanel](../../frontend/src/components/EvidenceGraphPanel.tsx) exists. | **PARTIAL** for citation quality: the fraction of decisions carrying references is not the fraction with sufficient, relevant, current, independently checked evidence. A `source` label can contribute to a verified classification. |
| **DONE — failure narrative bundle** | [Narrative builder](../../collector/audit/failure_narrative.py), [AuditPanel](../../frontend/src/components/AuditPanel.tsx), [narrative tests](../../tests/test_failure_narrative.py). Tests passed here. | **UNVERIFIED** operator benefit on unseen failures. Cause confidence is heuristic; an unlocalized narrative is explicitly capped at 0.4 and warns of weakness. |
| **DONE — minimal re-execution set planning** | [Planner](../../collector/audit/reexecution.py), [API](../../api/audit_routes.py), [tests](../../tests/test_reexecution.py). Tests passed here. | **PARTIAL** for an executable confirmation workflow. The function names a dependency set and read-only nodes; it does not run tools or prove globally minimal intervention cost. |
| **DONE — goal-drift series and success-flow advisory** | [Audit engine](../../collector/audit/audit_engine.py), [success-flow API](../../api/audit_routes.py), [success-flow tests](../../tests/test_success_flow.py). Relevant tests passed here. | **UNVERIFIED** semantic drift accuracy and usefulness across tasks. Token overlap and observed flow divergence are proxies. A valid alternate solution may diverge from the reference. |
| **PARTIAL — causal localization and backward attribution** | [Collector CausalAnalyzer](../../collector/causal_analysis.py), [SDK causal graph](../../agent_debugger_sdk/core/causal_tracer.py), [SDK attribution](../../agent_debugger_sdk/core/error_attribution.py), [API causal service](../../api/services/causal.py), [research routes](../../api/research_routes.py). Collector and route tests passed here. | Multiple analysis paths exist and need a common edge/unknownness contract. `get_failure_causes` echoes `failure_event_id` but computes session-wide analysis. Root-cause accuracy, graph completeness, and counterfactual validity remain **UNVERIFIED**. |
| **PARTIAL — frame lifetime tracing** | [SDK frame tracer](../../agent_debugger_sdk/core/frame_tracer.py), [frame capture tests](../../tests/test_frame_capture.py), [research report service](../../api/services/research.py), [route tests](../../tests/test_research_routes_api.py). Route tests passed here; frame-capture tests were only inspected. | The API projects captured events into frames; its tree returns the first root only, and depth traversal has no explicit visited-set guard. Complete multiple-root, cyclic, concurrent, or dropped-span trace handling is not established. |
| **PARTIAL — uncertainty reports and intervals** | [API formulas](../../api/services/research.py), [SDK scorer](../../agent_debugger_sdk/core/conformal_scorer.py), [research tests](../../tests/research/test_research_features.py). API route tests passed here. | Actual conformal calibration is **NOT STARTED in the inspected scoring paths**. The API uses `(1-confidence)*confidence_level`; the SDK uses a Gaussian z-score times a configured scale. Neither fits held-out nonconformity quantiles. No-ground-truth SDK classifications can still say `WELL_COVERED`; this is not measured coverage. |
| **PARTIAL — external Who&When evaluation** | [Normalizer](../../scripts/fetch_who_when.py), [evaluator](../../collector/audit/who_when.py), [CLI](../../scripts/benchmark_who_when.py), [unit tests](../../tests/test_who_when.py), and locally present 184-record corpus. The full local run reproduced the historical numbers. | Default step indexing is incompatible with the upstream global convention; CLI self-test fails. The evaluator is a separate text-marker heuristic and never calls the native audit/causal engine. Details below. |

The “conformal,” “calibrated,” and “guaranteed coverage” endpoint descriptions
in [research routes](../../api/research_routes.py) exceed the evidence supplied
by their implementation. Fixing the labels and handling unknown confidence
is a prerequisite to presenting these as decision-support guarantees.

## Reconcile the paper-inspired backlog

The [March concept audit](code-audit-paper-concepts.md) and superseded
[implementation plan](research-implementation-plan.md) are useful historical
context, but their percentages and missing-file claims should not drive work.
The statuses below refer to this repository's transferable capability, not to
reproduction of the original papers' training procedures.

| Theme | Corrected status and evidence | Remaining experiment |
|---|---|---|
| AgentTrace | **PARTIAL**. Explicit/inferred relations and ranked upstream suspects already exist in [CausalAnalyzer](../../collector/causal_analysis.py); [DecisionTree](../../frontend/src/components/DecisionTree.tsx) has causal-edge styling. | **NOT STARTED — a measured completeness audit** against independently labeled root-cause queries and deliberately missing spans. Compare collector, SDK, and API graph outputs. |
| FailureMem | **PARTIAL**. [FailureMemory](../../collector/failure_memory.py) stores/query-matches signatures with fix annotations; [RepairAttemptEvent](../../agent_debugger_sdk/core/events/repair.py), [SDK recorder](../../agent_debugger_sdk/core/recorders.py), [EventDetail repair sequences](../../frontend/src/components/EventDetail.tsx), [similar-failure API service](../../api/services/similarity.py), and [SimilarFailuresPanel](../../frontend/src/components/SimilarFailuresPanel.tsx) exist. Memory, repair, and seeded workflow tests passed here. | **UNVERIFIED — effective cross-session repair reuse**. No production `FailureMemory` caller was found in API/collector search; the current API uses a separate SQL and keyword matcher. A persistent, tenant-scoped retrieval-to-repair outcome loop and its benefit need demonstration. Do not plan `RepairAttemptEvent` as new work. |
| MSSR / adaptive replay | **PARTIAL**. [Replay ranking](../../collector/intelligence/compute.py) already includes age decay, failure recency, novelty, checkpoint and evidence bonuses; [retention classification](../../collector/intelligence/event_utils.py), [cross-session clustering](../../collector/clustering/cross_session.py), and [seeded recent/stale tests](../../tests/research/test_research_workflows.py) exist. Workflow tests passed here. | **UNVERIFIED — replay value predicts actual debugging benefit**. Compare to chronological, severity-only, and random ordering. Retention labels are not by themselves proof of physical storage-tier enforcement or safe deletion. |
| Act-or-Refuse | **PARTIAL**. [Safety and refusal events](../../agent_debugger_sdk/core/events/safety.py), refusal-aware [replay](../../collector/replay.py), audit failure narratives, and [policy/refusal E2E scenarios](../../tests/e2e/test_s6_policy_refusal.py) exist. Seeded refusal workflow passed here; E2E tests were not rerun. | Distinguish correct refusal, harmful execution, unnecessary refusal, and uncertain evaluation. Refusal currently participates in failure/risk ranking, so “refusal exists” does not establish appropriate safety interpretation. |
| Policy-Parameterized Prompts | **PARTIAL**. [Parameter-change analysis](../../collector/policy_analysis.py), [session comparison](../../api/comparison_routes.py), [ConversationPanel](../../frontend/src/components/ConversationPanel.tsx), [SessionComparisonPanel](../../frontend/src/components/SessionComparisonPanel.tsx), and [SwimlanePanel](../../frontend/src/components/SwimlanePanel.tsx) exist. Policy analysis tests passed here. | A controlled policy comparison with matched tasks, outcome/cost deltas, seed/version identity, and attribution uncertainty remains **UNVERIFIED**. Old references to `PolicyDiffView.tsx` are stale; it is not the current component. |
| CXReasonAgent / evidence grounding | **PARTIAL overall; DONE — basic coverage metric**. Audit `evidence_coverage`, evidence graph, missing-evidence signals, and comparison `grounded_decision_count`/grounding ratio exist in [engine](../../collector/audit/audit_engine.py) and [comparison API](../../api/comparison_routes.py). | Evaluate evidence sufficiency, reference resolution, freshness, contradiction, and abstention separately. Do not equate having a citation with truth or relevance. |
| REST / guided exploration | **PARTIAL**. [DecisionTree](../../frontend/src/components/DecisionTree.tsx) already scores failure proximity, evidence weakness, uninspected nodes, low confidence, tool diversity and checkpoints; `Next Best Branch` updates inspected state. [Component tests](../../frontend/src/__tests__/DecisionTree.test.tsx) exist but were not run here. | **UNVERIFIED — reduced investigation time** on large graphs. Measure clicks/time, missed causes and accessibility; separate actual information gain from additive heuristic priority. Do not schedule the existing navigation button as new work. |
| XAI for failures | **DONE — structured narrative slice**, as above. | **UNVERIFIED — explanation fidelity and operator usefulness**; test whether each stated mechanism is supported, with deliberate ambiguous/missing evidence. |
| Provenance survey | **DONE — evidence graph and re-execution-set planner**, as above. | **NOT STARTED — validated intervention runner** in the inspected planner. Preserve side-effect constraints and compare replayed outcomes with the predicted confirmation/refutation. |
| Goal drift / OAT / calibrated trust | **DONE — drift score, flow advisory, stakes and named bands** in the [audit engine](../../collector/audit/audit_engine.py) and [routes](../../api/audit_routes.py). | **UNVERIFIED — calibration, utility and generalization**. The labels and deterministic formulas are not experimental validation of the papers' hypotheses. |
| Neural Debugger | **PARTIAL — debugger interaction foundations** in [replay](../../collector/replay.py) and [stepper](../../api/stepper_routes.py). | **NOT STARTED — learned pre-execution prediction** in the inspected runtime. Treat that as a separate stretch experiment, not a missing basic replay control. |
| NeuroSkill | **PARTIAL — live monitoring foundations** in [live monitor](../../collector/live_monitor.py), [rolling summaries](../../collector/rolling.py), and event alerts. | **NOT STARTED — operator cognitive-state inference** in the inspected runtime. Defer unless a concrete user need and consented, measurable input justify it. |

## Who&When: reproducible numbers, invalid current comparison

The local manifest names upstream commit
`b2bae5c5b06d681d04ea5e9b63b7a30525c04925`, 126 algorithm-generated and 58
hand-crafted records. Corpus and result files are gitignored runtime state;
their presence on this machine is not a published, immutable result artifact.
The [fetch script](../../scripts/fetch_who_when.py) records a fetched commit,
but its default clone is not a fixed-revision fetch. Reproduction needs the
recorded source revision, normalized hashes, evaluator revision and settings.

### Results executed during this audit

| Run | Records | Localized | Exact agent | Exact agent AND step |
|---|---:|---:|---:|---:|
| Current default, `--step-scope agent` | 184 | 98 | 49/184 = 26.6% | 10/184 = 5.4% |
| Existing alternative, `--step-scope global` | 184 | 98 | 49/184 = 26.6% | 28/184 = 15.2% |
| Default, algorithm-generated split | 126 | 66 | 32.54% | 7.94% |
| Default, hand-crafted split | 58 | 32 | 13.79% | 0.00% |

These are results of the current evaluator, not newly established native
engine accuracy. [The evaluator](../../collector/audit/who_when.py) turns a
message containing broad strings such as `failed to` into an error, then picks
the message immediately preceding the first error. It abstains when no marker
appears. It does not invoke `SessionAuditEngine`, `CausalAnalyzer`, or native
captured evidence links.

The upstream prompt explicitly numbers each message in the whole conversation,
and its step-by-step implementation enumerates `chat_history` from zero.
This contradicts the local docstring's claimed per-agent convention.
[Pinned upstream inference helpers](https://github.com/mingyin1/Agents_Failure_Attribution/blob/b2bae5c5b06d681d04ea5e9b63b7a30525c04925/Automated_FA/Lib/utils.py#L81).
As an additional local consistency check, **95/184 annotations are outside the
range of messages spoken by their labeled mistake agent** under the current
normalization (65 algorithm-generated; 30 hand-crafted).

The upstream evaluation script scores agent and step separately and uses
substring membership. This repository requires exact agent equality and, for
step accuracy, a correct agent as well. These are different metrics.
[Pinned upstream evaluator](https://github.com/mingyin1/Agents_Failure_Attribution/blob/b2bae5c5b06d681d04ea5e9b63b7a30525c04925/Automated_FA/evaluate.py#L60).

The paper's abstract reports 53.5% agent and 14.2% step accuracy, but its
detailed results vary by method, split, and availability of the task's final
ground-truth answer. It reports averages across the two answer-availability
settings unless specified otherwise. Treat those abstract numbers as context,
not a matched single 184-record baseline row. The new 15.2% joint figure is
therefore **not evidence of beating the paper**.
[Primary paper, settings and Table 1](https://arxiv.org/html/2505.00212v3#S4.T1).

The documented CLI `--self-test` **fails**: its expected responsible agent is
`Verifier_Expert`, while the previous-message heuristic predicts
`Computer_terminal`. Existing evaluator unit tests passing did not catch this
command-level regression. Keep the benchmark capability **PARTIAL** until the
entry point, annotation convention and metric contract agree.

## Proposed experiments and acceptance gates

These are candidate delivery slices for the [roadmap](../ROADMAP.md), with
proposed acceptance gates rather than promises of measured improvements.
Complete E0 before publishing new research effectiveness claims.

| Priority / experiment | Build on / dependency | Proposed acceptance gate | Limit or stop condition |
|---|---|---|---|
| **E0 — evidence and benchmark integrity** | Current normalizer, evaluator, CLI, audit score descriptions | Default indexing agrees with pinned upstream conventions; zero invalid annotation indices; CLI self-test passes; export hashes, commits, split counts, exact independent agent/step, joint accuracy and abstention; include frozen prediction rows. Rename unsupported calibration guarantees. | No headline paper comparison without a matched scoring and input-information protocol. Legacy results remain labeled with their original settings. |
| **E1 — native causal attribution laboratory** | Collector/SDK graphs and failure narratives; E0 | At least 100 frozen native traces across tools, retrieval, policies, repairs and multiple agents, with independent annotations and disjoint development/evaluation sets; report top-1/top-3, abstention, missing-edge and irrelevant-span stress tests. Target at least 10 percentage points top-3 improvement over a frozen structural baseline without higher confident false attribution. | Synthetic correctness alone does not establish production accuracy; report disagreements and trace incompleteness explicitly. |
| **E2 — evidence quality and trust validation** | Existing references, freshness, score components; E0/E1 | Labeled supported/unsupported/stale/contradicted cases; disclose false-verification rate, coverage and per-source performance. For proposed probabilistic scores, use held-out reliability plots and Brier score. Unknown evidence must not silently become high trust. | If there are insufficient labels, retain explainable heuristic scores and remove probability/calibration language. |
| **E3 — repair memory that changes outcomes** | Existing repair sequences, SQL similarity, standalone vector memory; E1 | A tenant-scoped durable store with original failure, failed attempts, proposed fix, validation and outcome links; evaluate at least 50 held-out repair cases against no-memory and keyword baselines. Target a 20% reduction in repeated ineffective attempts without reducing verified fix success. | No automatic replay of a historical fix solely because signatures are similar. Isolate cross-tenant and stale-environment matches. |
| **E4 — replay and retention utility** | Existing age decay, rankings, clusters, checkpoints; E1 | Report ranked-debugging success and retained causal/evidence references at matched storage budgets. Target 50% storage reduction while retaining at least 95% of labeled diagnostic evidence, with deterministic retention explanations and dry-run review. | Physical deletion cannot precede referential-integrity checks and explicit retention policy; a score tier alone is not delivery. |
| **E5 — refusal and policy counterfactual matrix** | Safety events, comparison, conversation/swimlane views; E1/E2 | Matched tasks under at least three policies; separate justified refusal, unnecessary refusal, harmful action, recovery and unknown. Expose event-linked outcome/cost differences and policy/version identity; verify against independent labels. | Never improve an “agent success” number by counting every refusal as failure or every unblocked action as success. |
| **E6 — guided investigations at large trace sizes** | Existing Next Best Branch and narrative inspection points; E1 | Browser workflow on 1k/10k/100k-event fixtures with defined hardware budgets; compare investigation steps and elapsed time against chronology and current heuristic in a counterbalanced operator study. Target 25% fewer inspected nodes with no drop in correct localization. | No assumed information-gain benefit from the current additive priority score. Large-data filtering must preserve visible missing-context indicators. |
| **E7 — conformal prediction with a real target** | Current scorer contracts; E2 and sufficient labeled outcomes | First define the predicted quantity; fit quantiles on a separate calibration split; version datasets and exchangeability assumptions; report held-out empirical coverage, interval/set size, uncertainty and distribution-shift results. Preserve `unknown` when ground truth is absent. | Stop if confidence metadata is the only available “target.” A z-score interval or hand-written margin is not conformal calibration. |
| **E8 — intervention-based confirmation** | Existing re-execution planner, checkpoints, semantic restore; E1/E3 | Sandbox fixtures with deterministic tool doubles; each plan has inputs, permitted effects and outcome checks; unchanged replay is reproducible; targeted intervention tests explicitly confirm or refute a localized hypothesis, preserving an auditable link to original events. | Real external effects require a separate execution policy. The dependency set must never imply that native program state has already been restored. |

## Validation performed

Ran existing tests with the installed `.venv-ci` interpreter, sequentially and
without xdist or coverage, using temporary test databases. No service was
started, no model API was called, no dependency was installed, and no stored
user trace was replayed. This is scoped evidence, not a claim that all CI or
all frontend/E2E workflows pass.

```bash
.venv-ci/bin/python -m pytest -q -o addopts='' \
  tests/test_who_when.py tests/test_fetch_who_when.py \
  tests/test_audit_engine.py tests/research/test_research_workflows.py \
  tests/test_repair_event.py tests/test_feature_2_failure_memory.py \
  tests/test_causal_analysis.py tests/test_success_flow.py
# 181 passed in 3.34s

.venv-ci/bin/python -m pytest -q -o addopts='' \
  tests/test_reexecution.py tests/test_failure_narrative.py \
  tests/test_research_routes_api.py tests/test_policy_analysis.py
# 61 passed in 4.45s

.venv-ci/bin/python scripts/benchmark_who_when.py --self-test
# Exit 1: AssertionError; truth Verifier_Expert, prediction Computer_terminal

.venv-ci/bin/python scripts/benchmark_who_when.py \
  --data benchmarks/corpora/who_when/algorithm_generated.jsonl \
         benchmarks/corpora/who_when/hand_crafted.jsonl --step-scope agent
# 184 records; 98 localized; 26.6% exact agent; 5.4% joint agent+step

.venv-ci/bin/python scripts/benchmark_who_when.py \
  --data benchmarks/corpora/who_when/algorithm_generated.jsonl \
         benchmarks/corpora/who_when/hand_crafted.jsonl --step-scope global
# 184 records; 98 localized; 26.6% exact agent; 15.2% joint agent+step
```

The corpus range check counted a record as incompatible with per-agent
zero-based indexing when `int(mistake_step) >= len(messages_by_mistake_agent)`,
using the evaluator's `_speaker_of` normalization. Source inspection, two
targeted test invocations (**242 passed total**), the reproduced full-corpus
results, and the observed self-test failure support the statuses above.
