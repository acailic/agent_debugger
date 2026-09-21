# Model or Harness? An Interaction-Centric Taxonomy for Localizing Agent Failures

Paper: [arXiv:2607.28802](https://arxiv.org/abs/2607.28802) (2026)

## Core Idea

Existing evaluations reduce agent failures to system-level outcomes, obscuring where the fault originated and which intervention would improve performance. This paper localizes failures to interactions rather than components: 41 failure modes, each assigned to an edge between two components (model, harness, user, tools, memory, environment) plus a fault side indicating where the repair belongs. Reproducibility was tested with independent reasoning agents as judges across four frontier models; the strongest judge reached Cohen's κ = 0.76 against human category labels.

## Why It Matters Here

The edge-plus-fault-side pair is the missing output shape for first-bad-decision localization. This repo already finds the node in the causal chain; the paper's argument is that the node alone is not actionable — the operator needs the interaction the bad step occurred on (decision→tool, tool→model, memory→decision) and the side at fault. Both fields are derivable from recorded trace facts: which two components the bad step connects, and where the bad artifact originated.

Fault side is also the honest answer to "is it the model?" A bad step whose corrupt data was harness-recorded or tool-returned exonerates the model and redirects attention — which is exactly the next-inspection-point slot in the failure narrative, filled deterministically instead of by guesswork.

Where the trace cannot decide, the answer is "undetermined". A two-field output with an explicit undetermined state beats a guessed attribution: it tells the operator the recorder lacked the evidence, which is itself a completeness finding.

## Key Takeaways For The Repo

### 1. Extend the first-bad-decision record with interaction_edge + fault_side

interaction_edge names the two components the bad step connects; fault_side says model-produced / harness-recorded / tool-returned. Both inferred from trace facts, never from a judge.

### 2. "Undetermined" is a required value, not a failure

When the trace cannot show where the bad artifact originated, the field says undetermined. Fabricating a side to fill the slot would trade the deterministic guarantee for a cosmetic gain.

### 3. Fault side feeds the next inspection point

The failure narrative's next-inspection-point slot can be derived from fault_side: model-produced points back into the reasoning chain, harness-recorded points at instrumentation, tool-returned points at the data source.

## Concrete Opportunities

- add interaction_edge and fault_side as deterministic fields on the first-bad-decision record, derived from where the bad data originated in the causal chain
- render fault_side on the verdict card so the posture (act / verify-first / do-not-act) reads together with the locus at fault
- propagate the component pair to downstream-damage nodes so the damage radius carries its edge
- report the undetermined rate per session as a completeness signal — a high rate means the recorder is missing origin facts

## Caution

Their reproducibility result (κ = 0.76) was achieved with LLM judges, and it took four frontier models to get there. The fields this repo emits must be trace-derived — read from which component emitted the bad artifact — and where the trace cannot decide, the field says undetermined. Borrowing the judge to squeeze the undetermined rate down would trade the repo's core guarantee for a number.

## Best Next Experiment

On a batch of recorded failing sessions, derive interaction_edge and fault_side from trace facts for each first bad decision and measure the undetermined rate. That number says whether the recorder captures component origins well enough to make the fields useful — and which origins to capture next.
