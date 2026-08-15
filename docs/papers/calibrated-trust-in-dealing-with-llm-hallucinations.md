# Calibrated Trust in Dealing with LLM Hallucinations

Paper: [arXiv:2512.09088](https://arxiv.org/abs/2512.09088) (FLLM 2025)

## Core Idea

A 192-participant qualitative study of how hallucinations change trust in everyday LLM use. Hallucinations do not cause blanket mistrust — users engage in *context-sensitive trust calibration*, weighting expectancy, prior experience, domain expertise, and (newly identified) intuition, modulated by perceived risk and decision stakes. The authors extend Blöbaum's recursive trust-calibration model with intuition.

## Why It Matters Here

The repo renders an explainable trust score, but a score alone does not calibrate anyone — operators calibrate from context, stakes, and history. This study says the tool around the number matters as much as the number: the same trust score must read differently for a low-stakes scratch task and a production run.

## Key Takeaways For The Repo

### 1. Trust is calibrated per-context, not globally

Users already adjust trust by decision stakes. Surfacing stakes (what the session touched: files, external calls, payments) next to the trust score matches how operators actually decide to rely on a run.

### 2. Prior experience is a trust input

Operators trust agents they've seen behave. Session history for the same agent (the portfolio view already aggregates this) should be one click from any single session's verdict.

### 3. Overtrust and undertrust are both failures

The framing cuts both ways: uncritical acceptance of a hallucinated run wastes the audit, reflexive distrust wastes the tool. The UI should make "this run is trustworthy — you can act on it" as easy to conclude as "this run is suspect."

## Concrete Opportunities

- add a compact "stakes" line to the session verdict card: resources touched, actions taken, reversibility
- link each session's verdict to that agent's recent portfolio trend (trust improving/degrading)
- name the trust bands in the UI (e.g. act / verify-first / do-not-act) instead of showing only a raw number
- A/B the verdict card wording: recommendation-oriented vs number-oriented

## Caution

It is a small qualitative study of chat users, not agent operators — transfer the mechanism (context-sensitive calibration), not the specific factor weights. The repo's users are more expert than the study population.

## Best Next Experiment

Add stakes metadata (tool categories used, writes vs reads, external effects) to the session summary schema and render it in the verdict card. Then check with a real operator whether the verdict card changes their decision, not just their knowledge.
