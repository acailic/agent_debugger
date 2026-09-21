# Human Error (Reason)

Book: [Human Error](https://doi.org/10.1017/cbo9781139062367) (Cambridge University Press, 1990)

## Core Idea

The founding text of modern error analysis. Reason splits active failures — errors committed at the human–system interface, whose effects appear near in time and place — from latent conditions: dormant weaknesses (design flaws, poor procedures, stale data) laid down earlier in the system, which line up with local triggers to let an accident through. The core teaching: blame the active error, but hunt the latent conditions, because they are where prevention lives.

## Why It Matters Here

The failure narrative (symptom, mechanism, cause chain, evidence, next inspection point) currently centers the first bad decision. Reason's split gives it a second, mandatory layer: the first bad decision is the active failure; stale evidence, missing instrumentation, and ambiguous instructions are the latent conditions that made it likely. A narrative reporting only the decision reduces to "the model was wrong."

The repo already has latent-condition detectors — session completeness diagnostics, stale-evidence detection — but their output is not wired into the failure narrative as enabling conditions of the localized decision.

The split also disciplines resolution. A do-not-act verdict should not be marked resolved on the active failure alone, because the latent conditions remain in place for the next run.

## Key Takeaways For The Repo

### 1. Split the failure narrative into active error and latent conditions

First bad decision = active failure; everything upstream that plausibly enabled it = latent-condition candidates. Report both, labeled as such.

### 2. Require a latent-condition candidate before a do-not-act verdict is marked resolved

Gating resolution on at least one named enabling condition forces the audit past symptom level and gives the next run something to check.

### 3. The next inspection point should usually point upstream

Prevention lives in the latent conditions, so the narrative's next inspection point should name an enabling condition — a superseded fact source, a silent recorder gap — not only the decision.

## Concrete Opportunities

- add a latent_conditions array to the failure narrative schema, populated from completeness diagnostics and stale-evidence findings
- gate the do-not-act resolved state on a non-empty latent-condition candidate
- seed a mechanistic latent-condition vocabulary: superseded fact, dropped event, ambiguous instruction, missing check
- surface latent conditions that recur across sessions in the regression lab's baseline bundles

## Caution

Reason's model is about human cognition and organizational defenses; agent latent conditions are an analogy. Keep the language mechanistic — superseded fact, dropped event — and make no claims about model intention. Not every active failure has an identifiable latent condition; an empty list should read "none found," never "none existed."

## Best Next Experiment

Add latent_conditions to the failure narrative schema and populate it from existing session completeness diagnostics for a handful of failed sessions. Then check whether an operator can name an enabling condition for each do-not-act verdict — if they cannot, the detectors are finding the wrong things.
