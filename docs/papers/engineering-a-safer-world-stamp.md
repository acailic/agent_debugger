# Engineering a Safer World: Systems Thinking Applied to Safety (STAMP)

Book: [Engineering a Safer World](https://doi.org/10.7551/mitpress/8179.001.0001) (MIT Press, 2012, open access)

## Core Idea

The book that introduces STAMP: safety as a control problem, not a component-reliability problem. Accidents arise when safety constraints are inadequately enforced in a hierarchical control structure — including component-interaction accidents in which no component individually fails. The operational method, STPA, identifies unsafe control actions of four types — a required action not taken (omitted), a wrong action taken, an action at the wrong time or in the wrong order (mistimed), and an action applied too long or stopped too soon (overlong) — then traces each to flaws in the control loop. Chain-of-events causality under-models these systemic accidents.

## Why It Matters Here

The four unsafe-control-action types are a ready-made classification for first-bad-decision + downstream-damage localization: every localized bad decision gets a type — omitted, wrong, mistimed, overlong. "Mistimed" is the formal home of the stale verdict. Acting on evidence a newer fact superseded is an action taken at the wrong time relative to the state of the world — a cleaner description than "wrong," because the evidence was once adequate and the content was never false at capture.

Safety as a control problem is the argument for auditing the whole control loop — model, tools, evidence flow, harness — rather than grading the model. The repo's stance that the model is not always the culprit is STAMP's basic position, 14 years earlier.

Component-interaction accidents give the failure narrative a vocabulary for runs where every component behaved to spec and the outcome is still wrong: nothing individually failed; the interaction did.

## Key Takeaways For The Repo

### 1. Type every localized bad decision with the four UCA categories

Omitted / wrong / mistimed / overlong gives the first-bad-decision record a deterministic classification axis — no LLM judge, filterable, countable across sessions.

### 2. "Mistimed" is the formal home of the stale verdict

Contradicted means the claim disagrees with its cited evidence; stale means the evidence was adequate when captured and a newer fact superseded it before the action. Wrong content versus wrong timing.

### 3. Audit the loop, not the model

The run's control loop includes tools, evidence flow, and harness. Localization that can only blame the model is measuring the wrong system.

## Concrete Opportunities

- add a uca_type field (omitted / wrong / mistimed / overlong) to the first-bad-decision record in the failure narrative
- define the stale verdict in docs as the mistimed subtype: acted on evidence a newer fact superseded
- add a component-interaction case to the failure narrative for runs where no component individually failed
- state the control-loop audit scope (model, tools, evidence flow, harness) explicitly in the audit report

## Caution

STAMP assumes designed control structures with specifiable safety constraints; agent behavior is emergent, so STPA-style analysis here will be partial. Use the four types as a reporting taxonomy for the failure narrative, not as a promise that every failure reduces to a controllable constraint violation. The stakes line and posture bands on the verdict card are argued from operator studies, not from this book — do not cite Leveson for them.

## Best Next Experiment

Add the four-value uca_type to the failure narrative schema and hand-classify a dozen recorded failed runs. Check two things: whether the four types cover the observed failures, and whether every stale case lands in mistimed without argument. The classification is worth shipping only if both hold.
