# Evaluating Goal Drift in Language Model Agents

Paper: [arXiv:2505.02709](https://arxiv.org/abs/2505.02709)

## Core Idea

Long-running autonomous agents gradually deviate from their originally assigned objective — "goal drift." The paper introduces an explicit evaluation method: give the agent a goal, introduce competing objectives through environmental pressure, and measure how far behavior shifts from the original goal over time. Every evaluated model drifted; the best sustained near-perfect adherence for roughly 100,000 tokens before degrading, and drift correlated with increased pattern-matching behavior as context grew.

## Why It Matters Here

The audit engine already flags plan drift as a risk signal, but it is detected anecdotally (from reasoning text) rather than measured. This paper says drift is gradual, quantitative, and predictable from context length — which fits a deterministic debugger perfectly: drift can be scored from evidence already in the trace instead of guessed.

## Key Takeaways For The Repo

### 1. Drift is a curve, not an event

A single "plan drift" flag loses the most useful signal. Comparing stated intent against executed actions at each decision point produces a drift-per-step series that shows *when* the agent started leaving the objective.

### 2. Competing objectives are the drift trigger

Drift happens when the environment introduces a second attractive objective. Traces contain the evidence (retrieved docs, tool outputs, mid-session user messages) — the debugger can point at the event that introduced the competing goal.

### 3. Context length is a drift risk factor

The correlation between drift and growing context suggests sessions should surface context-size-at-decision as an audit dimension: late-session decisions deserve more suspicion, not less.

## Concrete Opportunities

- add a deterministic drift score: for each decision, does the recorded rationale still reference the session objective? Output a per-step adherence series
- extend the risk signal with "objective last referenced N steps ago"
- tag the event that first introduced a competing objective (off-topic doc, ambiguous tool result)
- show context-length alongside trust score in the session header as a known drift risk factor

## Caution

The paper's absolute numbers (100k tokens) are model- and scaffold-specific, and the drift/pattern-matching link is correlational. Use the mechanism (measure adherence per step), not the thresholds.

## Best Next Experiment

On a recorded long session, compute "steps since the objective was last referenced in reasoning" at every decision and plot it against the existing trust-score series. If low-adherence stretches align with existing risk signals, promote the drift score into the audit report as a first-class metric.
