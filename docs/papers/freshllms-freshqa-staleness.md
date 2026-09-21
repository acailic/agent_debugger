# FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation (FreshQA)

Paper: [arXiv:2310.03214](https://arxiv.org/abs/2310.03214) (2023)

## Core Idea

FreshQA is a QA benchmark that mixes fast-changing world-knowledge questions with evergreen ones, plus false-premise questions that need to be debunked rather than answered. All models, regardless of size, struggle on fast-changing knowledge and false premises; prompting and search-augmentation choices move the numbers substantially. The premise underneath the benchmark: knowledge has different volatility classes, and neither model scale nor search alone fixes acting on outdated facts.

## Why It Matters Here

The stale verdict in the claim-verification taxonomy (acted on evidence a newer fact superseded) only makes sense because evidence has volatility classes. FreshQA supplies the split that makes a staleness check tractable: evergreen vs fast-changing vs user-provided, recorded at capture time. Staleness cross-checks then run only on the volatile class — the evergreen majority never pays the cost.

The false-premise category maps directly onto the "unsupported" bucket. An agent can act on a premise the cited evidence never contained: that is unsupported — the premise is absent from or contradicted by the cited evidence — not merely unverified. FreshQA's results say agents walk into this bucket often enough to matter.

## Key Takeaways For The Repo

### 1. Record the volatility class at capture time

Every evidence item gets a class (evergreen / fast-changing / user-provided) when recorded, not at audit time. The class is a property of the evidence, not of the check.

### 2. Run staleness cross-checks only on the volatile class

Scoping the check to fast-changing evidence bounds its cost and keeps it deterministic: compare capture time against superseding-fact time within a known-volatile set, never everywhere.

### 3. False premises are unsupported, not unverified

Unverified means the check could not run. Unsupported means the check ran and the premise is absent from or contradicted by the cited evidence. The distinction is load-bearing for the trust score.

## Concrete Opportunities

- add a volatility_class field to the evidence record schema, set at capture
- scope the staleness cross-check to the fast-changing class only
- add a premise-presence check to claim verification: absent or contradicted premise → unsupported
- surface the volatility mix of a session's evidence on the verdict card

## Caution

FreshQA is about QA answers, not agent actions, and volatility heuristics will misfire — some "evergreen" facts change. A stale flag lowers the trust score and triggers verify-first; it never auto-fails the run. The class is a routing hint for the check, not a claim about the world.

## Best Next Experiment

Add the three-value volatility_class to the evidence schema and hand-tag a few recorded sessions. Report what fraction of evidence items land in the fast-changing class — that fraction bounds the cost of the staleness cross-check before any checker is written.
