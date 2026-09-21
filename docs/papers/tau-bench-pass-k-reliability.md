# τ-bench: A Benchmark for Tool-Agent-User Interaction

Paper: [arXiv:2406.12045](https://arxiv.org/abs/2406.12045) (2024)

## Core Idea

A benchmark emulating dynamic user–agent conversations with domain-specific API tools (retail, airline), and the origin of pass^k — the requirement that the agent succeed on all k repeated trials of the same task. The findings: even state-of-the-art function-calling agents such as gpt-4o succeed on under 50% of tasks and are quite inconsistent, with pass^8 under 25% in the retail domain. Success is judged by comparing the end-of-conversation database state against the goal state — a check on outcomes, not on prose.

## Why It Matters Here

pass^k is the honest reliability metric for the regression lab. Mean pass rate hides the failure that lands 1 run in 8; worst-of-k over repeated trials exposes it. An engine change is not "fixed" if a committed baseline bundle still fails one run in eight — gating CI on all-k success is strictly stronger than gating on the mean, and τ-bench is the published argument that this is the right gate. Re-running the engine k times over the same bundle also catches nondeterminism the engine itself introduces: a change that makes verdicts flaky fails pass^8 even when every individual run looks correct.

The grading scheme is a template for the verdict card's outcome check. τ-bench compares final database state to goal state, deterministically, with no judge model in the loop. That is exactly the shape of the "with what result" answer: compare the recorded end state of the run against the goal it stated, and let the state diff speak.

The pass^8 finding also calibrates the audit view. Inconsistency across repeated trials of the same task is the norm for tool-using agents, not an anomaly; a console showing one green run and one red run of the same task is showing the real distribution.

## Key Takeaways For The Repo

### 1. Worst-of-k beats mean pass rate as a gate

A bundle that passes 7 of 8 trials is a failing bundle under pass^8. The regression lab should gate engine changes on all-k success over baseline bundles, which also exposes flakiness the engine introduces.

### 2. Final state vs goal state is the deterministic outcome check

τ-bench grades outcomes by state comparison with no judge. The verdict card's "with what result" slot should follow the same pattern: recorded end state against stated goal, expressed as a diff.

### 3. Reliability numbers belong on bundle reports

A "reliability: pass^8" figure per baseline bundle makes the regression lab's gate legible at a glance and gives every engine change a number to hold constant.

## Concrete Opportunities

- add pass^k as a first-class regression-lab metric: run each baseline-bundle scenario k times (and/or across k recorded variants of the same task) and gate CI on all-k success
- display per-bundle reliability (e.g. "reliability: pass^8") on bundle reports
- implement a deterministic outcome check for verdict cards: recorded final state vs the goal the run stated, rendered as a state diff
- group repeated trials of the same task as comparable sessions so cross-trial inconsistency is visible in the audit view

## Caution

τ-bench tasks come with an oracle goal state; real audited runs do not. The transferable parts are the repeated-trial reliability math and the state-vs-goal comparison pattern — not the benchmark's domains and not any claim of measuring task success. Where a run's goal was never stated precisely, there is nothing to diff against, and the outcome check must say so rather than improvise a goal after the fact.

## Best Next Experiment

Pick one committed baseline bundle, run the engine over it k = 8 times in the regression lab, and compute pass^8 from the existing per-run verdicts. If the number is stable across two engine commits, wire it into CI as that bundle's gate metric.
