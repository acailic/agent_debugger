# Why Do Multi-Agent LLM Systems Fail? (MAST)

Paper: [arXiv:2503.13657](https://arxiv.org/abs/2503.13657) (2025)

## Core Idea

The first comprehensive failure taxonomy for LLM multi-agent systems. Expert annotation of MAS execution traces yields MAST: 14 failure modes in three categories — system design issues, inter-agent misalignment, and task verification — with inter-annotator agreement of κ = 0.88. The paper releases MAST-Data, 1600+ annotated traces across 7 MAS frameworks, plus an LLM-as-a-judge pipeline for scalable annotation. The empirical motivation: multi-agent gains on benchmarks are often minimal, and the taxonomy shows where the value leaks out — at agent hand-offs and at missing or faulty verification, more than in the base model.

## Why It Matters Here

MAST is the reference vocabulary for the failure narrative. The narrative's mechanism slot needs a name for what went wrong; the 14 modes are a field-tested set of names, sorted by three categories. "Verification absent" and "instruction conflict" are better mechanism labels than anything this repo would invent from scratch.

The taxonomy also types the first bad decision. A localized bad step that is a hand-off break calls for a different operator reaction than one that is a verification miss. Carrying the MAST category and mode on the first-bad-decision record turns the localization from a correct answer into an actionable one.

The inter-agent modes double as a completeness checklist. Information loss between agents and failed hand-offs are only detectable if the recorder captured the inter-agent messages at all. Each inter-agent mode is therefore a concrete test for "did the recorder miss events" in the session completeness diagnostics.

## Key Takeaways For The Repo

### 1. Adopt the mode vocabulary for the failure narrative

The 14 modes and 3 categories label the mechanism slot with vocabulary that already has κ = 0.88 agreement among expert annotators. This repo gets the rigor without inventing its own taxonomy.

### 2. Type the first bad decision with a MAST mode

First-bad-decision + downstream-damage localization currently returns a node. Attaching mode + category classifies that node so the operator knows which kind of failure to react to.

### 3. Inter-agent modes are recorder-completeness tests

If a session involves agent-to-agent interaction but no captured hand-off messages, the completeness diagnostics should name that gap. The MAST inter-agent modes enumerate exactly which messages matter.

## Concrete Opportunities

- add MAST-aligned mode + category fields to the failure narrative and the first-bad-decision record
- build a fixture suite with one synthetic trace per MAST mode that the engine must classify deterministically from trace facts, gated in the regression lab's CI run
- extend session completeness diagnostics with an inter-agent capture check derived from the inter-agent misalignment modes
- use MAST-Data's 1600+ labeled traces as an external corpus for checking narrative-mode classification coverage

## Caution

MAST's scalable annotator is an LLM-as-a-judge pipeline. That is the part to refuse: adopt the taxonomy, not the judge — every mode label this repo emits must be derived from recorded trace facts, or the deterministic-attribution stance is gone. The corpus is also multi-agent traces, so several modes will rarely fire in single-agent sessions; a mode that never fires is a finding about the session, not a bug in the classifier.

## Best Next Experiment

Pick the modes that map onto single-agent traces (roughly the system-design and task-verification categories), write one synthetic trace per mode, and assert the engine labels each with the right mode from trace facts alone. Around ten fixtures, committed as a baseline bundle — the start of a MAST-mode gate in the regression lab.
