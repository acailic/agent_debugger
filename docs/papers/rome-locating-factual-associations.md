# Locating and Editing Factual Associations in GPT (ROME)

Paper: [arXiv:2202.05262](https://arxiv.org/abs/2202.05262) (NeurIPS 2022)

## Core Idea

The paper that gave "causal tracing" its modern meaning: a causal intervention on model internals that identifies which activations are decisive for a factual prediction. The method runs the model clean, corrupts the run, then restores activations piecewise and measures which restores recover the correct output. It localizes factual recall to mid-layer feed-forward modules processing the subject tokens, and ROME edits a specific factual association through a rank-one weight update while preserving behavior elsewhere.

## Why It Matters Here

The lineage claim is methodological. Attribution by controlled intervention — clean run, corrupted run, measure what restores — is the experimental logic behind "causal tracing," and this repo can run the same logic at the evidence layer of a recorded trace, deterministically, with no access to model internals.

The trace-level translation is evidence ablation: for a chosen decision, remove or replace one recorded evidence item and observe whether the decision or its claims change. Removal is the corruption; restoring the original or swapping in a better item is the restore test.

The stale verdict gets the sharpest use. "Acted on evidence a newer fact superseded" currently reports a timing fact; ablation turns it into an experiment — replace the superseded item with the superseding fact and show whether the decision flips.

## Key Takeaways For The Repo

### 1. Attribution by intervention, not inspection

The clean/corrupt/restore triad is the citable methodology behind causal tracing; at trace level it becomes remove-one-evidence and replace-one-evidence over a recorded decision.

### 2. Staleness becomes testable

For any stale verdict, the decisive experiment is already defined: swap the superseding fact in and check whether the decision changes. That is the difference between flagging a decision stale and showing the staleness mattered.

### 3. Ablation is deterministic and per-item

Computed from recorded traces with no LLM and no model access, a causal-importance score per evidence item is cheap enough to run on demand in session analysis for suspect decisions.

## Concrete Opportunities

- implement evidence ablation in the audit panel: for a chosen decision, replay the recorded checks with one evidence item removed or replaced and report which claim statuses or classifications change
- attach a per-evidence-item causal-importance score to decisions in session analysis, computed on demand
- back the stale check with an ablation wherever a superseding fact is recorded: swap it in, report whether the decision flips
- name the feature "evidence ablation" in the UI and cite ROME as the methodological lineage in docs

## Caution

ROME operates on weights and activations inside one model; this repo operates on recorded evidence. Trace-level ablation shows which recorded inputs the outcome was sensitive to — never what the network believed, and the docs must not claim neural-level explanation. Ablation also cannot re-run the model itself; it measures the sensitivity of the recorded, deterministic checks. Run it on demand for suspect decisions, not wholesale over every session.

## Best Next Experiment

Take one recorded session carrying a stale verdict. Write a script that re-runs the deterministic claim-verification checks with the superseded evidence item replaced by the superseding fact, and report which claim statuses change. One session, no ML, no model internals — it uses only what the recorder already holds.
