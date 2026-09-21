# Trust in Automation: Designing for Appropriate Reliance (Lee & See)

Paper: [doi:10.1518/hfes.46.1.50_30392](https://doi.org/10.1518/hfes.46.1.50_30392) (Human Factors 46(1), 2004)

## Core Idea

The canonical human-factors paper on calibrated trust in automation. Trust is only useful when it matches ability: overtrust causes misuse (relying on automation beyond its capability), undertrust causes disuse (ignoring capable automation), and the design goal is appropriate reliance between the two. Trust develops along three information bases — performance (what the automation did), process (how it works), and purpose (why it was designed and for what) — and the paper's guidance is to make those bases observable, so people calibrate trust to actual ability rather than to appearance.

## Why It Matters Here

This is the 20-year-old science behind the repo's whole trust surface. The explainable trust score is a calibration target's instrument, not a grade: its job is to place the operator at the right point on the misuse–disuse line for this run. The verdict card's named postures (act / verify-first / do-not-act) are reliance guidance in exactly Lee & See's sense — verify-first is a misuse guard on under-verified runs, a reachable act verdict is the disuse guard.

The five operator questions map onto the three trust bases. What happened and with what result are the performance basis. Why and with what evidence are the process basis. The task framing is the purpose basis. The question surface this repo already answers is a trust-bases instrument; it needs labeling, not redesign.

The three bases double as an audit checklist for the trust-score explanation. A score that exposes verification outcomes but not which checks ran, or not what class of task the run claimed to do, is hiding a basis the operator calibrates on. (The calibrated-trust note covers context-sensitivity; this paper covers why calibrated reliance is the design goal at all.)

## Key Takeaways For The Repo

### 1. The postures are misuse/disuse guards

Act / verify-first / do-not-act are reliance guidance, not grades. Verify-first exists to prevent misuse on under-verified runs; a clean act verdict presented as decisively as a do-not-act prevents disuse of good runs.

### 2. The three bases are the audit checklist for the score explanation

Every explainable trust score should expose a performance basis (verification outcomes), a process basis (which checks ran, what the recorder saw), and a purpose basis (what class of task this run claimed to do).

### 3. The five questions are already the trust-bases instrument

The mapping is exact: what happened / with what result = performance, why / with what evidence = process, task framing = purpose. Documenting the mapping makes the question surface defensible as calibration support rather than a report format.

## Concrete Opportunities

- audit the current trust-score explanation against the three bases and document any basis with no exposed element
- write the misuse/disuse rationale into the posture microcopy (verify-first = misuse guard, reachable act = disuse guard)
- label each of the five operator questions with its trust basis in the docs
- add a basis-completeness warning to the session view when a verdict's explanation draws on only one or two bases

## Caution

Lee & See write about human trustors and continuous automation; an agent run is episodic and the operator is expert. The score is evidence for the operator's calibration, not the operator's trust itself — keep the human in the loop. The stakes line and the band names are argued from elsewhere; this paper argues only the goal, and it should not be stretched into claims about how any particular operator will read a number.

## Best Next Experiment

Take the current trust-score explanation and tag every element as performance, process, or purpose. Any basis with nothing under it is a concrete gap; fill the emptiest one first (likely purpose — task framing) using a field the recorder already captures, before adding anything new.
