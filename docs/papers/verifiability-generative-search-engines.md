# Evaluating Verifiability in Generative Search Engines (Liu, Zhang, Liang)

Paper: [arXiv:2304.09848](https://arxiv.org/abs/2304.09848) (Findings of EMNLP 2023)

## Core Idea

Measures whether generated, citation-bearing text is actually verifiable, decomposing verifiability into citation recall (are statements cited comprehensively?) and citation precision (do the citations actually support the statements?), with attribution judged independent of the truth of the statements — against only the retrieved sources. Across major generative search engines, on average 51.5% of generated sentences are fully supported by their citations and only 74.5% of citations support their sentences. The paper recommends making the retrieval corpus explicit to users.

## Why It Matters Here

This is the measurement model for the claim-verification surface — not the taxonomy, which is this repo's own. The per-claim outcomes (verified / partially verified / contradicted / unsupported / unverified) can be reported the way citation precision and recall are: per-run verified / partially-verified / unsupported fractions as headline metrics, instead of a wall of individual claim results.

Corpus-explicitness is the second import. Every verdict should name exactly what the claim was checked against — "checked against these 3 retrieved chunks" — because a verdict without a named corpus cannot be audited, only believed.

The paper's independence-of-truth rule is the repo's determinism rule in evaluation form: check the claim against the recorded evidence, not against the world. That is what keeps the LLM judge out of the attribution path.

## Key Takeaways For The Repo

### 1. Report verification outcomes as per-run fractions

Verified / partially-verified / unsupported fractions on the verdict card give the explainable trust score an auditable basis — each fraction recomputes from the per-claim results beneath it.

### 2. Surface the corpus per claim

Each claim's verdict names the evidence items it was checked against. Corpus-explicitness is what makes a verdict checkable by hand.

### 3. Judge against recorded evidence only, independent of world truth

Attribution independent of truth is what makes the check mechanical and replayable. Claims reaching beyond the recorded evidence stay unverified.

## Concrete Opportunities

- add a per-run verified / partially-verified / unsupported fraction row to the verdict card as a headline metric
- render the checked-against evidence set on each claim in the claim-verification view
- track the fractions per baseline bundle in the regression lab as an engine-change gate
- state corpus-explicitness in docs: every verdict names exactly what it was checked against

## Caution

Their "supported" is human judgment on natural-language entailment; the repo's check is mechanical consistency against recorded evidence. The deterministic version is stricter and noisier on paraphrase — expect partially verified to carry the load, and do not reuse the paper's numbers as a quality bar for agent runs; they measure generative search engines with human raters.

## Best Next Experiment

Compute the per-run verification fractions from existing claim-verification output and render them as one headline row on the verdict card. Then check whether the fractions already explain the trust score's movement across a handful of sessions — if they do, the score gains an auditable basis for free.
