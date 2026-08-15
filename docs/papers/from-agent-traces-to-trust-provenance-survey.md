# From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents

Paper: [arXiv:2606.04990](https://arxiv.org/abs/2606.04990)

## Core Idea

Final-answer accuracy cannot explain how an agent produced an output or where it went wrong. The survey argues that **evidence tracing** and **execution provenance** are the foundation of process-level accountability: execution provenance is the typed graph of everything an agent did, and evidence tracing is its projection onto which evidence supported which claim.

## Why It Matters Here

This is the closest thing to a literature backing for what this repo already is. The taxonomy (trace sources, evidence units, provenance relations, granularity, trust functions) reads like a checklist for an audit console, and it explicitly connects retrieval grounding, tool-use logging, claim support, and trust scoring into one framework instead of separate features.

## Key Takeaways For The Repo

### 1. Provenance is a typed graph, not a log

Flat event lists force the auditor to reconstruct causality by hand. Typed edges (used-evidence, produced-claim, triggered-retry, caused-failure) are what make "why did this happen" answerable by traversal rather than re-reading.

### 2. Claim support is a first-class relation

The survey treats "which evidence supports which claim" as a queryable relation, not a UI afterthought. Verification status (verified / contradicted / unsupported) should be derivable from that relation alone.

### 3. Trust functions belong at the end of the pipeline

Trust scores are most defensible when computed as a function of the provenance graph — coverage, support ratios, contradiction counts — rather than as an independent model or heuristic bolted on.

### 4. Provenance should serve recovery, not just review

The survey links auditing to recovery (what to re-run, what to exclude). A provenance graph that can point at the minimal sub-graph to re-execute is more valuable than one that only renders.

## Concrete Opportunities

- audit the existing evidence-provenance endpoint against the survey's relation taxonomy and name any missing edge types
- document the trust score explicitly as a function of graph properties (supported claim ratio, contradicted count, uncited evidence)
- add a "minimal re-execution set" view: the smallest sub-graph that would need to re-run to invalidate or confirm a suspect claim
- treat the staleness check as a provenance relation (evidence-was-current-at) rather than a separate flag

## Caution

It is a survey: it unifies vocabulary more than it validates methods. Adopting its taxonomy wholesale risks over-engineering relations this repo's users will never query.

## Best Next Experiment

Map one recorded session onto the survey's provenance relation set and count which relations the current engine can and cannot express. Any relation that exists in the taxonomy but not in the data model is a candidate feature, prioritized by how often auditors ask for it.
