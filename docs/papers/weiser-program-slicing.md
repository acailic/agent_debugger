# Program Slicing

Paper: [doi:10.1109/TSE.1984.5010248](https://doi.org/10.1109/TSE.1984.5010248) (IEEE TSE, 1984)

## Core Idea

The paper that defined the slice: for a variable at a program point, the subset of program statements that can influence that variable's value there, computable from the program text alone (static slicing). Weiser motivated slicing by debugging — programmers localizing a fault naturally reason about a reduced projection of the program, and slices make that projection precise and automatic. Slices are typically far smaller than the original program.

## Why It Matters Here

The causal chain is a dependence graph in Weiser's sense. Every claim cites the evidence it was checked against, and every action depends on the decision and evidence that triggered it. Those are data dependences, and 1984 already tells the repo what to do with them.

The two operator questions map onto the two slice directions. "Why did the agent believe X" is a backward slice from a claim — what fed this. Downstream-damage localization is a forward slice from the first bad decision — the damage radius.

The decisive property is exactness. Slicing one recorded execution is dynamic slicing: it answers what did influence a node in this run, not what could have in general. Static slices over-approximate; a recorded trace does not. That is the same promise the deterministic claim-verification taxonomy makes, and Weiser gives it a 40-year, entirely non-LLM pedigree.

## Key Takeaways For The Repo

### 1. Dependence edges belong at capture time

The recorder should emit claim-to-evidence and action-to-decision edges as first-class recorded events, so slicing is traversal over captured facts rather than reconstruction after the fact. The SDK and the auto-patch adapters should write the same edges.

### 2. Every node deserves two one-click views

Backward slice ("what fed this") and forward slice ("what it fed — the damage radius") on any decision, claim, or action. Downstream damage then has a precise definition: the forward slice from the first bad decision.

### 3. Promise what did influence, not what could have

Because the slice runs over one recorded execution, the honest wording is "influenced, in this run." That exactness is the product's differentiator, and Weiser is the citation behind deterministic attribution in the docs.

## Concrete Opportunities

- add dependence-edge types to the recorder event schema (claim-checked-against-evidence, action-triggered-by-decision), written by both the SDK and the auto-patch adapters
- ship one-click backward ("what fed this") and forward ("damage radius") slice views on any node in session analysis
- define downstream damage as the forward slice from the first bad decision and report its size in the failure narrative
- cite Weiser (1984) wherever the deterministic-attribution stance is argued in docs — the 40-year non-LLM pedigree

## Caution

Weiser's static slices can be wildly over-approximate in real programs, which is exactly why this repo slices a single recorded execution instead of an agent in general. But a slice is only as complete as the capture: where session completeness diagnostics flag missing events, the slice is silently partial too. And not every operator question is a slice — timelines and summaries still earn their place beside it.

## Best Next Experiment

Take one recorded session, hand-write its dependence edges into a table (each claim to its evidence, each action to its decision), and implement backward and forward traversal as a small script over that table. If the two traversals correctly answer "why did the agent believe X" and "what did the first bad decision touch" on that session, the edges belong in the recorder schema.
