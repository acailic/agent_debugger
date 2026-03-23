# FailureMem: A Failure-Aware Multimodal Framework for Autonomous Software Repair

Paper: [arXiv:2603.17826](https://arxiv.org/abs/2603.17826)

## Core Idea

This paper treats failed repair attempts as valuable memory. Instead of discarding them, the system records failed attempts and uses that history to improve later debugging and repair decisions.

## Why It Matters Here

Debugging systems usually preserve the final outcome and lose the failed path that led there.

That matters for this repo because failed attempts often contain the strongest signal about:

- what was already tried
- which strategies repeatedly do not work
- where an agent keeps looping or regressing

## Key Takeaways For The Repo

### 1. Failed attempts are useful artifacts

The debugger should be able to retain:

- attempted fixes
- resulting errors or regressions
- tests or checks that invalidated the attempt
- links between attempts in the same repair sequence

### 2. Repair memory should span sessions

The product becomes stronger when it can recognize repeated failed strategies across runs and surface them before the next attempt starts.

### 3. Multimodal does not need to mean complicated on day one

This repo can start with text-first artifacts:

- code diffs
- tool outputs
- test failures
- error summaries

That is enough to capture useful repair memory before adding richer artifact types.

## Concrete Opportunities

- add repair-attempt events with outcome metadata
- summarize prior failed attempts in session detail views
- cluster repeated repair failures across sessions
- rank sessions by repair-learning value

## Caution

The repo should avoid preserving sensitive or low-value artifacts forever. Failure memory needs the same retention and redaction discipline as normal traces.

## Best Next Experiment

Add a lightweight repair-attempt history:

- record each attempted fix
- attach the validation result
- show previous failed attempts before the next replay or inspection step
