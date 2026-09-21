# Why Programs Fail: A Guide to Systematic Debugging

Book: [Why Programs Fail, 2nd ed.](https://shop.elsevier.com/books/why-programs-fail/zeller/978-0-12-374515-6) (Morgan Kaufmann, 2009)

## Core Idea

The book that turned debugging from art into experimental discipline. Zeller frames every debugging act as the scientific method applied to a failing run: track the problem, reproduce it, then run controlled experiments that narrow the causes, automating the hypothesis tests to determine which inputs and changes are relevant. Its best-known instrument is delta debugging, which minimizes failure-inducing inputs and program changes by systematic removal, isolating cause-effect chains automatically.

## Why It Matters Here

This is the scientific lineage of first-bad-decision localization. A recorded agent session is a very long failing input, and the causal chain is the candidate set for automated minimization: what is the shortest subset of decisions and evidence that still produces the same failed verdict?

The framing transfers as much as the algorithm. An operator reading a verdict card is running Zeller's loop by hand — hypothesis, experiment, narrowed cause — and the repo can automate the experiment half because the black-box recorder already holds the state.

Reproduction is the precondition. Zeller's method needs a failing run that can be re-run; committed baseline bundles in the regression lab are exactly that, which is what makes them a gate on engine changes rather than a demo.

## Key Takeaways For The Repo

### 1. Debugging is hypothesis testing, not narrative

The failure narrative should read as hypotheses with evidence attached: each localized failure states what was suspected, what check ran, and what the check returned — the same shape as the five operator questions.

### 2. Delta debugging on traces gives minimal reproductions

A ddmin-style loop over a failing run's decision/evidence chain can yield the minimal subset that still produces the same failed verdict — the "minimal reproduction" to show next to the full session, and a small fixture to commit to the regression lab.

### 3. Controlled experiments require recorded state

The scientific method applies to agent runs only because the recorder captured them. Every feature that re-runs a check over recorded evidence — claim verification, replay — is a Zeller-style experiment the operator does not have to trust, only inspect.

## Concrete Opportunities

- implement a ddmin-style trace minimizer in the regression lab: minimize a failing bundle run to the decision/evidence subset that still produces the same failed verdict, shown as "minimal reproduction" beside the full session
- use minimal reproductions as committed regression fixtures — a minimized trace is a small, sharp bundle for gating engine changes
- pre-narrow first-bad-decision candidates by which decisions survive inside the minimal subset
- frame the session analysis report as an explicit hypothesis list (suspect, check run, result) in Zeller's vocabulary

## Caution

Delta debugging assumes near-monotone failure behavior: removing input either keeps or kills the failure. Agent traces carry no such guarantee — dropping a decision can change downstream behavior in unpredictable ways, so a minimized trace is a candidate explanation, never the run itself. Always display it alongside the unmodified session, and do not let "minimal" quietly become "what actually happened."

## Best Next Experiment

Take one recorded failing session, treat the ordered decision/evidence chain as the ddmin input, and re-run the deterministic claim verifier over candidate subsets until the same failed verdict persists — a script over an existing session bundle, no ML and no new infrastructure. Report how small the minimal chain gets and whether its first surviving bad decision matches the engine's first-bad-decision answer.
