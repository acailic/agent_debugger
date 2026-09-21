# TRAIL: Trace Reasoning and Agentic Issue Localization

Paper: [arXiv:2505.08638](https://arxiv.org/abs/2505.08638) (2025)

## Core Idea

A benchmark for the exact problem this repo solves: finding what went wrong inside a recorded agent execution. TRAIL contributes a formal error taxonomy and 148 large human-annotated traces from single- and multi-agent workflows in software-engineering and information-retrieval settings. The headline result: modern long-context LLMs are poor at trace debugging — the best model evaluated, Gemini-2.5-pro, scored 11%. Reading a trace and spotting the issue is not solved by bigger models. The dataset is public on Hugging Face.

## Why It Matters Here

The 11% number is the strongest single published figure behind this repo's core stance. When the best evaluated frontier model localizes trace errors at 11%, putting an LLM judge in the attribution path means paying for the weak tool on every run. Deterministic trace-derived attribution is the differentiator, and it now has a citable number attached.

The public TRAIL traces are external ground truth for the deterministic localizer. This repo can score its first-bad-decision localization against human-annotated error locations it did not create. The mapping from TRAIL's error spans to decision-graph nodes is part of the experiment and must be written down explicitly — not silently gamed — but the value is real: an accuracy number computed on someone else's labels.

The error taxonomy doubles as a recorder coverage checklist. Every category TRAIL annotates is a class of issue the black-box recorder must capture for the localizer to see it. Walking the taxonomy against the event schema is a completeness audit of what the SDK and auto-patch adapters emit.

## Key Takeaways For The Repo

### 1. The 11% result is the number to cite

Gemini-2.5-pro, the best model evaluated, localized trace errors at 11%. This is the strongest single published number for keeping LLMs out of the attribution path — recent, concrete, and from the exact task this repo performs.

### 2. External ground truth needs an explicit mapping step

The 148 public, human-annotated traces let the localizer be scored against labels this repo did not produce. The mapping from TRAIL error spans to decision-graph nodes must be documented, or the benchmark measures the mapping instead of the localizer.

### 3. The error taxonomy is a capture-completeness checklist

Each TRAIL error category is an issue class the localizer can only find if the recorder captured it. Any category with no home in the event schema is a gap in what the recorder emits.

## Concrete Opportunities

- run the deterministic localizer on the public TRAIL traces and publish agreement with the human-annotated error locations, with the mapping rules documented alongside
- cite the 11% Gemini-2.5-pro result in docs as the published case against an LLM judge in the attribution path
- audit the recorder event schema against the TRAIL error taxonomy: every category must be representable in captured events, and gaps named
- make TRAIL agreement a regression-lab metric so engine changes that regress localization get caught in CI

## Caution

TRAIL annotates error spans in traces of third-party agent frameworks. Its notion of "the error" does not always match this repo's decision-graph nodes, and several traces come from workflows richer than what the recorder captures today. Score on the representable subset, say which subset that was, and treat the agreement number as directional evidence rather than a leaderboard entry.

## Best Next Experiment

Download 10 TRAIL traces, hand-map the annotated error locations onto decision-graph nodes, and write the mapping rules down as they are derived. Then run the localizer and report agreement. Ten traces is enough to learn whether the mapping is defensible before committing to the full 148.
