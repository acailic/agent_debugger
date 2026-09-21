# AgentRewind: Recoverable Execution for Long-Horizon LLM Agents

Paper: [arXiv:2608.14380](https://arxiv.org/abs/2608.14380) (2026)

## Core Idea

Prevention is not enough for long-horizon agents, because errors made early spread through both the agent's context and the external environment in hard-to-reverse ways. AgentRewind is a runtime recovery framework that records aligned checkpoints of the agent's internal context and the controlled environment, so a rewind executor can restore both and let the agent roll back and retry using information from prior attempts. The paper introduces MettleBench, a benchmark for long-horizon engineering assignments that scores task completion and partial progress, and reports gains in success rate and checklist progress over baselines across tasks, models, strategies, and harnesses.

## Why It Matters Here

The aligned-checkpoint insight states the correctness constraint for adaptive replay: a rewind is only well-defined if the agent's context and the mutated environment — filesystem, database — restore in lockstep. Restoring the conversation but not the files the agent already wrote produces a replay of a state that never existed. This repo's replay exists to explain what happened, so it has the same obligation: replay-from-here must be anchored to a point where context and environment actually aligned.

That makes environment fingerprints a session-bundle concern. Hashes of external state captured at decision points let the replay engine verify alignment before rewinding — and refuse unsafe rewinds where the state cannot be confirmed restorable, instead of silently presenting a bogus reconstruction.

The first-bad-decision record gains a boundary. Alongside the decision node, the localization should name the checkpoint boundary it belongs to, so "replay from just before the first bad decision" is a well-defined operation rather than a hopeful one.

## Key Takeaways For The Repo

### 1. Rewind correctness means context and environment in lockstep

Adaptive replay must treat the agent context and the mutated environment as one unit. A point where only one of the two can be restored is not a rewind point.

### 2. Environment fingerprints belong in session bundles

State hashes at decision points are cheap to record and are the only way to verify alignment later. They extend the black-box recorder's remit from the causal chain to the world the chain mutated.

### 3. Unsafe rewinds should be refused, not approximated

When the trace cannot show that context and environment align at a candidate rewind point, adaptive replay should say so and decline. A refused rewind is honest evidence; a half-restored one is a fabricated session.

## Concrete Opportunities

- record environment fingerprints (hashes of touched files / database state) at each decision point into the session bundle
- add an alignment check to adaptive replay: verify context and environment agree at the requested rewind point, and refuse the rewind when they do not
- attach the checkpoint boundary to the first-bad-decision record so replay-from-the-failure is well defined
- score replayed runs with a checklist-style partial-progress measure (MettleBench's pattern) instead of a binary recovered/not-recovered flag

## Caution

AgentRewind rewinds so a live agent can retry; this repo replays so an operator can understand. The retry machinery — strategy selection, re-execution, progress on subsequent attempts — is out of scope, and pulling it into the replay UX would turn an audit console into an agent orchestrator. Expose checkpoint alignment as evidence and leave execution policy with the operator.

## Best Next Experiment

In one demo session whose agent mutates the filesystem, hash the touched files at each recorded decision and store the hashes as environment fingerprints. Then have adaptive replay attempt a rewind to the first bad decision and report whether context and environment could be confirmed aligned — including one deliberately unrestorable case that must be refused.
