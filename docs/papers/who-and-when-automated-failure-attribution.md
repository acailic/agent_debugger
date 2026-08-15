# Which Agent Causes Task Failures and When? (Who&When)

Paper: [arXiv:2505.00212](https://arxiv.org/abs/2505.00212) (ICML 2025)

## Core Idea

Automated failure attribution — identifying which agent and which step caused a task failure in an LLM multi-agent system — is a distinct, underexplored task. The authors release a dataset of 127 failed multi-agent system logs annotated at fine granularity, and evaluate three automated attribution methods. The best reaches 53.5% accuracy on *which agent* failed but only 14.2% on *which step* — some methods score below random guessing, and frontier reasoning models are not practically usable for this.

## Why It Matters Here

This repo's audit engine already answers "where did it fail" deterministically from recorded evidence — and this paper is the strongest evidence that the LLM-judge alternative does not work. Step-level attribution is exactly the hard part (14.2%!), and deterministic trace-derived attribution sidesteps the failure mode entirely.

## Key Takeaways For The Repo

### 1. Step-level attribution is the open problem

Agent-level blame is half-solvable with LLMs; step-level is nearly unsolved. Any feature that pinpoints the first bad decision from recorded evidence is doing something the LLM-judge literature cannot yet do reliably.

### 2. Fine-grained annotations are the scarce resource

The dataset exists because annotating failure logs by hand is expensive. A debugger that emits machine-checkable failure localizations (first bad decision + downstream damage) produces training/eval data for free as a byproduct.

### 3. Positioning: deterministic beats prompting where traces exist

The paper's methods interrogate logs with LLMs. When the debugger has the full causal chain recorded, rule-based attribution over the graph is both cheaper and reproducible — a defensible product claim.

## Concrete Opportunities

- benchmark the audit engine's "where it failed" output against the Who&When dataset logs (public on GitHub) as an external validation set
- export failure attributions in the dataset's annotation format so the repo can serve as an attribution-data generator
- state the positioning explicitly in docs: no LLM judge in the attribution path, ever

## Caution

The dataset is multi-agent-system logs, which differ from single-agent traces this repo mostly records. Attribution difficulty does not transfer one-to-one; treat the benchmark as directional.

## Best Next Experiment

Run the failure-localization logic on a handful of the public Who&When failure logs and compare its first-bad-step answer to the human annotation. Even a small sample gives an external accuracy number no competitor publishes.
