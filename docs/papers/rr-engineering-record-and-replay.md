# Engineering Record and Replay for Deployability (rr)

Paper: [arXiv:1705.05937](https://arxiv.org/abs/1705.05937) (rr extended technical report, 2017)

## Core Idea

The paper behind rr, the record-and-replay debugger. rr captures only an execution's nondeterministic events — notably system-call results — so the entire run replays bit-for-bit later, entirely in user space on stock hardware, compilers, runtimes, and OS. Deterministic replay then enables reverse-execution debugging, reproduction of intermittent failures, and forensic analysis of recorded executions. Quinn and Alvaro's 2025 CACM restatement of the lineage compresses the recipe: record only the nondeterministic.

## Why It Matters Here

This is the founding recipe for the recorder's economics. The repo does not need to record everything — only the nondeterministic inputs. For an agent that means model responses, tool results, and timestamps; the prompt, code, and config are deterministic context.

Recorded runs become reproducible artifacts rather than souvenirs. That is what makes the regression lab's baseline bundles a real gate on engine changes, and adaptive replay scientifically sound rather than theatrical: a re-run either reproduces the recorded causal chain or something is missing.

The replay check doubles as a diagnostic. If re-running the audit engine over a bundle diverges from the recorded chain, the session was incompletely captured — session completeness diagnostics get a mechanical definition.

## Key Takeaways For The Repo

### 1. Record only the nondeterministic

Model outputs, tool results, timestamps. Everything else is deterministic context pinned inside the bundle. Small bundles, cheap recorder, complete sessions.

### 2. A bundle is a reproducibility contract

Baseline bundles gate engine changes only if replay is verified: an engine change that alters a baseline's recorded causal chain fails the gate, whatever the aggregate metrics say.

### 3. Say precisely what replay does

rr replays machine execution; agent replay re-runs nondeterministic LLM inference only where recorded outputs are reused. Adaptive replay replays recorded evidence deterministically — it does not make live model calls reproducible, and the UI wording must not imply it does.

## Concrete Opportunities

- specify the session bundle format as "deterministic core + nondeterministic log": recorded model responses, tool results, and timestamps against a pinned prompt/config/code version
- add a replay checker that verifies a re-run reproduces the recorded causal chain, and flag divergent replays in session completeness diagnostics
- gate regression-lab engine changes on causal-chain reproducibility across the baseline bundles
- word the adaptive replay UI precisely: "replays recorded evidence deterministically," never "reruns the model"

## Caution

rr's guarantee is bit-for-bit machine replay against a recorded kernel interface; an agent session has no such substrate, so do not promise reproducibility beyond the recorded chain. The "only the nondeterministic" cut also has limits: harness versions, tool schemas, and config are deterministic only if pinned inside the bundle, and drift between record time and replay time breaks the contract silently.

## Best Next Experiment

Take one existing session bundle, split it into deterministic core (prompt, config, code version) and nondeterministic log (model responses, tool results, timestamps), then write a checker that re-runs the audit engine over the log and asserts the causal chain matches the recording. One session, no ML, no new infrastructure — divergences name the first missing-event diagnostic and the first draft of the bundle-format spec.
