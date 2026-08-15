# Tracing Agentic Failure from the Flow of Success (OAT)

Paper: [arXiv:2607.12747](https://arxiv.org/abs/2607.12747)

## Core Idea

Unsupervised failure attribution without failure labels: train only on *successful* trajectories. OAT (one-class learning with neural controlled differential equations) learns the dynamics of success in latent space; at inference, each step in a failed trajectory gets an anomaly score for how far it deviates from those success dynamics. Trained on 100 successful trajectories, it is 200–5000× faster than prompting-based attribution with +20% F1 in-domain and +7% F1 out-of-distribution.

## Why It Matters Here

The repo already records many sessions of the same agents doing similar tasks, and already has a divergence detector and comparison routes for contrasting runs. This paper is the blueprint for turning that fleet of past *successful* runs into a reference model: a failing session can be localized by where it departs from how success usually flows — no failure annotations needed.

## Key Takeaways For The Repo

### 1. Success trajectories are the cheap training set

Failures are rare and expensive to label; successes are abundant and free. Any session corpus accumulates successes by default, so a success-dynamics reference costs nothing to collect.

### 2. Anomaly-as-attribution gives per-step scores

A continuous "deviation from normal flow" score per step composes well with the existing deterministic signals: determinism answers *is this claim supported*, success-dynamics answers *is this step weird for this kind of task*.

### 3. Speed enables fleet-scale auditing

Two-to-three orders of magnitude faster than LLM-judge attribution means attribution can run across the whole portfolio routinely — matching the fleet-level portfolio audit view.

## Concrete Opportunities

- extend the existing comparison/divergence tooling with a "typical success flow" per (agent, task-type) built from historical sessions
- score each step of a failing session against that reference and surface the top deviation points as supplemental (non-deterministic) audit signals — clearly labeled as statistical, unlike the verified/contradicted claims
- feed portfolio aggregates: sessions whose steps deviate most from their task-type's success flow rank as highest audit priority

## Caution

This is a learned, statistical layer — the opposite of the repo's deterministic verification guarantee. It must never silently influence the trust score; keep it advisory and visually distinct, or the "explainable, deterministic" promise is diluted.

## Best Next Experiment

Without any ML: for one task type with several recorded sessions, align a failing run's step sequence against a successful run using the existing divergence detector and report the first divergence point as a candidate failure localization. If that heuristic agrees with the audit engine's "first bad decision" on real sessions, the learned version is worth building.
