# Visualization of Test Information to Assist Fault Localization (Tarantula)

Paper: [doi:10.1145/581396.581397](https://doi.org/10.1145/581396.581397) (ICSE 2002)

## Core Idea

The founding paper of spectrum-based fault localization. Run the test suite, record which lines execute in passing versus failing tests (the program spectrum), then rank every line by suspiciousness — how much more strongly it associates with failures than with passes — and visualize the whole program as a color-coded heat map from red to green. The developer's attention is ordered by evidence from many runs instead of one stack trace.

## Why It Matters Here

A single session gives the repo a causal chain. A regression-lab bundle gives it a spectrum: many runs of the same scenario, each already stamped with a deterministic pass/fail verdict. That is the exact raw material Tarantula needs, and the committed baseline bundles already hold it.

The suspiciousness computation is arithmetic — count each node's co-occurrence with failed and passed runs, take a ratio. No training, no learning, no judge. It is the same math Tarantula ran on code lines, applied to decision nodes and evidence sources instead.

This is what first-bad-decision localization is missing when more than one run exists: a deterministic pre-ranking. Decisions that only ever appear in failed runs jump out before the operator reads anything.

## Key Takeaways For The Repo

### 1. Many runs turn a chain into a spectrum

The regression lab's baseline bundles are the pass/fail corpus. Per-run verdicts are already deterministic output, so the spectrum costs nothing new to collect.

### 2. Suspiciousness is counting, not learning

A Tarantula or Ochiai score over the recorded spectrum is deterministic arithmetic over decision nodes rather than code lines — fully inside the no-LLM-judge stance, with no learned deviation score anywhere in it.

### 3. It orders candidates before localization

Score each decision node and evidence source across a bundle's runs and pre-rank the first-bad-decision candidates deterministically, so localization starts from an evidence-ordered list rather than trace order.

## Concrete Opportunities

- add a spectrum view to the regression lab: aggregate a bundle's runs and compute a Tarantula/Ochiai-style suspiciousness per decision node and per evidence source
- pre-rank first-bad-decision candidates by suspiciousness whenever multiple runs of a scenario exist in a bundle
- gate engine changes on spectrum shifts: a decision that moves from passed-and-failed to failed-only after a change blocks the change
- color-code decision nodes red-to-green in session analysis when spectrum data exists — Tarantula's visualization carried over to the chain

## Caution

SBFL ranks, it does not convict. A decision that correlates with failure may be a symptom — chosen only when the run was already off the rails — not the cause. Suspiciousness must stay an ordering over the causal chain and never be presented as a verification outcome: it assigns none of the verified / partially verified / contradicted / unsupported / unverified / stale statuses, and it cannot mark a decision bad on correlation alone.

## Best Next Experiment

Take one bundle with several recorded runs of the same scenario, some passed and some failed. Compute an Ochiai-style suspiciousness per decision node with a small script over the existing per-run verdicts — no ML, no new infrastructure — and check whether the top-ranked node agrees with the engine's first-bad-decision localization on the failed runs.
