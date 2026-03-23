# XAI for Coding Agent Failures: Transforming Raw Execution Traces into Actionable Insights

Paper: [arXiv:2603.05941](https://arxiv.org/abs/2603.05941)

## Core Idea

This paper focuses on converting raw coding-agent execution traces into structured, human-interpretable explanations that make failures easier to diagnose and act on.

## Why It Matters Here

Raw traces are necessary, but they are not the same thing as understanding.

That matters for this repo because a good debugger should reduce operator effort by turning a long trace into a compact explanation that still points back to source evidence.

## Key Takeaways For The Repo

### 1. Explanation should be a first-class debugging surface

The repo should not assume that users want to read every event manually. It can provide structured failure narratives such as:

- observed symptom
- likely failure mechanism
- supporting evidence
- best next inspection point

### 2. Failure modes should be normalized

Repeated issues become much easier to compare when the system can label patterns such as:

- invalid tool arguments
- stale context or missing evidence
- bad decomposition or planning
- incorrect repair attempt

### 3. Explanations should stay anchored to trace evidence

The right pattern is not "replace the trace." It is:

- compress the trace into an explanation
- keep links back to the underlying events
- show uncertainty when the explanation is weak

## Concrete Opportunities

- add explanation cards to failure and replay views
- create a small failure-mode taxonomy for agent sessions
- generate session summaries with symptom, cause, evidence, and next step
- support side-by-side raw trace and explanation review

## Caution

Explanation is a compression layer and can hide nuance. The repo should preserve evidence links and confidence markers so users can audit the summary.

## Best Next Experiment

For one failed session, generate a structured explanation bundle:

- symptom
- likely cause
- supporting events
- recommended next inspection point
