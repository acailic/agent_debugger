# AgentTrace: Causal Graph Tracing for Root Cause Analysis

Paper: [arXiv:2603.14688](https://arxiv.org/abs/2603.14688)

## Core Idea

This paper reconstructs a causal graph from workflow execution logs, then traces backward from an observed failure to rank the most likely upstream causes.

## Why It Matters Here

Chronological traces are useful, but they still make the operator do too much manual reconstruction.

That matters for this repo because a debugger should help answer:

- what failed
- what upstream event likely caused it
- how confident the system is in that diagnosis

## Key Takeaways For The Repo

### 1. Failures should be reviewed as dependency graphs, not only timelines

The current product already has event order and hierarchy. A stronger debugger would also surface causal relationships across:

- decisions
- tool calls
- evidence-producing events
- checkpoints
- downstream errors or refusals

### 2. Root-cause analysis should rank suspects

Large traces often contain many plausible upstream mistakes. The useful move is not just showing all ancestors, but prioritizing:

- the nearest meaningful cause
- the highest-impact upstream deviation
- repeated sources of downstream breakage

### 3. Causal inference should stay inspectable

If the debugger infers a likely cause, the operator still needs to see:

- which events support that hypothesis
- whether the link is explicit or inferred
- how strong the confidence is

## Concrete Opportunities

- derive causal edges from parent-child links, evidence references, and tool dependencies
- add a failure-to-cause drill-down panel for error and refusal events
- rank candidate root causes in session analysis
- annotate replay with inferred upstream causes

## Caution

This is a post-hoc diagnosis pattern, not a guarantee of true causality. The repo should expose confidence and evidence instead of presenting inferred causes as certainty.

## Best Next Experiment

Implement one failure investigation flow:

- pick an error event
- walk backward through explicit and inferred dependencies
- show the top three candidate causes
- link each cause to the supporting trace evidence
