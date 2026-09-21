# Science Foundations — Candidate Works for Review (2026-09-21)

**Method.** Compiled on 2026-09-21 by scouting the four README pillars (agent debugging, causal tracing, failure analysis, adaptive replay) plus the trust/verdict surface. Two passes: (1) the gap-hypothesis list (classic debugging/localization/record-replay/tracing/trust/safety-science lineage, agent rollback, agent eval reliability), then (2) open searches for 2024–2026 LLM-agent works on failure attribution, trace error localization, staleness, verifiability, and rewind. Every candidate below was checked against a **primary source**: arXiv abstract pages fetched directly, the Crossref DOI registration record for paywalled ACM/IEEE/Cambridge/MIT Press items (publisher-deposited metadata), the Elsevier book page for Zeller, and the actual Google Dapper technical-report PDF. The 15 works already listed in the README/`docs/papers/` and their near-duplicates were excluded. Numbers below appear only if they appeared in the fetched primary source. Candidates are split TOP TIER (8) / SECOND TIER (9). This file proposes only — no README or `docs/papers/` edits were made.

## Summary table

| # | Work | Venue/Year | Pillar | Maps to Peaky Peek feature | Tier |
|---|------|-----------|--------|---------------------------|------|
| 1 | Why Do Multi-Agent LLM Systems Fail? (MAST) | arXiv:2503.13657, 2025 | failure analysis | Failure-mode labels for the audit narrative; first-bad-decision + completeness diagnostics | Top |
| 2 | Why Programs Fail (A. Zeller) | Morgan Kaufmann/Elsevier, 2nd ed. 2009 | agent debugging | Trace minimization (delta debugging) for first-bad-decision isolation and regression lab | Top |
| 3 | Program Slicing (M. Weiser) | IEEE TSE SE-10(4), 1984 | causal tracing | Causal chain + downstream-damage as backward/forward slices | Top |
| 4 | Visualization of Test Information to Assist Fault Localization (Tarantula) | ICSE 2002 (ACM) | agent debugging | Suspiciousness ranking of decisions across passed/failed runs in the regression lab | Top |
| 5 | Dapper, a Large-Scale Distributed Systems Tracing Infrastructure | Google Tech Report dapper-2010-1, 2010 | causal tracing | Black-box recorder: span-tree trace model, instrumented vs inferred causality, safe no-payload recording | Top |
| 6 | Trust in Automation: Designing for Appropriate Reliance (Lee & See) | Human Factors 46(1), 2004 | trust | Explainable trust score; act / verify-first / do-not-act postures | Top |
| 7 | Engineering a Safer World (N. Leveson, STAMP) | MIT Press, 2012 (open access) | failure analysis | Verdict card: control-theoretic framing, unsafe-control-action typing, stakes line | Top |
| 8 | TRAIL: Trace Reasoning and Agentic Issue Localization | arXiv:2505.08638, 2025 | agent debugging | External ground truth for first-bad-decision localization; completeness diagnostics taxonomy | Top |
| 9 | Engineering Record and Replay for Deployability (rr, extended TR) | arXiv:1705.05937 (ASPLOS'17 lineage), 2017 | adaptive replay | Deterministic record/replay: capture only nondeterministic events; reverse-execution over recorded runs | Second |
| 10 | τ-bench: Tool-Agent-User Interaction | arXiv:2406.12045, 2024 | trust / regression | pass^k reliability gating in the regression lab; deterministic final-state checking | Second |
| 11 | AgentRewind: Recoverable Execution for Long-Horizon LLM Agents | arXiv:2608.14380, 2026 | adaptive replay | Adaptive replay checkpoints aligned across agent context AND environment state | Second |
| 12 | FreshLLMs / FreshQA | arXiv:2310.03214, 2023 | trust | Stale-evidence detection: evidence volatility classes + false-premise handling | Second |
| 13 | Evaluating Verifiability in Generative Search Engines | arXiv:2304.09848, Findings of EMNLP 2023 | trust | Claim-verification taxonomy: per-claim citation precision/recall as verified/unsupported scoring | Second |
| 14 | Locating and Editing Factual Associations in GPT (ROME) | NeurIPS 2022 (arXiv:2202.05262) | causal tracing | Causal-intervention methodology → counterfactual evidence ablation on recorded traces | Second |
| 15 | Human Error (J. Reason) | Cambridge University Press, 1990 | failure analysis | Verdict narrative: active error vs latent conditions split; defense-in-depth framing | Second |
| 16 | Characterizing Faults in Agentic AI | arXiv:2603.06847, 2026 | failure analysis | Completeness diagnostics: harness-fault checklist (schema mismatch, dependency drift, state loss) | Second |
| 17 | Model or Harness? An Interaction-Centric Taxonomy for Localizing Agent Failures | arXiv:2607.28802, 2026 | failure analysis | First-bad-decision localization output: component-interaction edge + fault-side attribution | Second |

---

## Top tier

### 1. Why Do Multi-Agent LLM Systems Fail? (MAST)

- **Verified title:** Why Do Multi-Agent LLM Systems Fail?
- **Authors:** Mert Cemri, Melissa Z. Pan, Shuyi Yang, et al. (12 authors; UC Berkeley et al.)
- **Venue/Year:** arXiv:2503.13657, 2025 (v1 Mar 2025, v3 Oct 2025)
- **Primary link:** https://arxiv.org/abs/2503.13657
- **Core idea.** The first comprehensive failure taxonomy for LLM multi-agent systems. From expert annotation of MAS execution traces the authors derive MAST: 14 unique failure modes clustered into three categories — (i) system design issues, (ii) inter-agent misalignment, and (iii) task verification — with inter-annotator agreement of κ = 0.88. The paper also releases MAST-Data, a dataset of 1600+ annotated traces across 7 MAS frameworks, and an LLM-as-a-judge pipeline for scalable annotation. The motivation is empirical: multi-agent gains on benchmarks are often minimal, and the taxonomy explains where the value leaks out — notably at agent hand-offs and at missing/faulty verification rather than in the base model.
- **Why it matters for Peaky Peek.** MAST is the reference vocabulary for the audit report's failure narrative and the "where did it fail?" answer. Its three categories map cleanly onto Peaky Peek surfaces: system-design issues and inter-agent misalignment → first-bad-decision localization on the causal chain; task-verification issues → the deterministic claim-verification taxonomy (contradicted/unsupported/unverified). It also feeds completeness diagnostics: several MAST modes (information loss between agents, failed hand-offs) are only detectable if the recorder captured inter-agent messages — a concrete checklist for "did we miss events."
- **Design takeaway.** Add a MAST-aligned mode picker to the failure narrative ("hand-off break", "verification absent", "instruction conflict", …) and write a fixture suite where each MAST mode has a synthetic trace that Peaky Peek must classify deterministically — that suite becomes a regression-lab gate.
- **Caution.** MAST's scalable annotator is an LLM judge; Peaky Peek's attribution path stays deterministic — adopt the taxonomy, not the judging mechanism.
- **Suggested note slug:** `why-do-multi-agent-llm-systems-fail-mast`

### 2. Why Programs Fail: A Guide to Systematic Debugging

- **Verified title:** Why Programs Fail: A Guide to Systematic Debugging (2nd edition)
- **Authors:** Andreas Zeller
- **Venue/Year:** Morgan Kaufmann / Elsevier, 2009 (ISBN 978-0-12-374515-6)
- **Primary link:** https://shop.elsevier.com/books/why-programs-fail/zeller/978-0-12-374515-6
- **Core idea.** The canonical book that turned debugging from art into an experimental discipline. Zeller frames every debugging act as the scientific method applied to a failing run: track the problem, reproduce the failure, then run controlled experiments to narrow causes — automating hypothesis tests to determine which changes are relevant. Its best-known instrument is delta debugging, which automatically minimizes failure-inducing inputs and program changes (isolating failure-inducing cause-effect chains) by systematic removal. The publisher's TOC confirms the arc: from tracking and reproducing problems through simplifying, observing state, and cause-effect chains.
- **Why it matters for Peaky Peek.** This is the scientific lineage of "first bad decision" isolation: a recorded agent run is just a (very long) failing input, and the causal chain is a candidate set for automated minimization. Delta debugging applied to traces — "what is the shortest prefix/subset of decisions and evidence that still produces the contradiction?" — directly strengthens first-bad-decision localization, and the scientific-method framing (explicit hypotheses, controlled experiments, observed state) matches Peaky Peek's audit-record UX.
- **Design takeaway.** Implement a `ddmin`-style trace minimizer in the regression lab: given a failing bundle run, produce the minimal decision/evidence subset that still yields the same failed verdict, and show it as "minimal reproduction" next to the full session.
- **Caution.** Delta debugging assumes near-monotone failure behavior (removing input either keeps or kills the bug); agent traces have no such guarantee — treat the minimal trace as a candidate explanation, and always display it alongside the unmodified session.
- **Suggested note slug:** `why-programs-fail-systematic-debugging`

### 3. Program Slicing

- **Verified title:** Program Slicing
- **Authors:** Mark D. Weiser
- **Venue/Year:** IEEE Transactions on Software Engineering, SE-10(4):352–357, 1984 (originally ICSE 1981)
- **Primary link:** https://doi.org/10.1109/TSE.1984.5010248
- **Core idea.** The paper that defined the slice: for a variable at a program point, the slice is the subset of program statements that can influence that variable's value there — computable from the program text alone (static slicing). Weiser motivated slicing by debugging: when localizing a fault, programmers naturally reason about a reduced projection of the program rather than the whole thing, and slices make that projection precise and automatic. Slices are typically far smaller than the original program.
- **Why it matters for Peaky Peek.** Peaky Peek's causal chain is exactly a data/control-dependence graph in Weiser's sense — every claim cites evidence, every action depends on decisions. "Downstream damage" localization is a forward slice from the first bad decision; "why did the agent believe X" is a backward slice from a claim. Citing Weiser gives the deterministic-attribution stance a 40-year-old, fully non-LLM pedigree.
- **Design takeaway.** Store dependence edges at record time (claim → evidence it was checked against; action → decision + evidence that triggered it) and expose two one-click views on any node: backward slice ("what fed this") and forward slice ("what it fed — the damage radius").
- **Caution.** Static slices can be wildly over-approximate in real programs; in traces they are exact because we slice a single recorded execution (dynamic slicing). Don't promise "what could have influenced" — promise "what did influence, in this run."
- **Suggested note slug:** `weiser-program-slicing`

### 4. Visualization of Test Information to Assist Fault Localization (Tarantula)

- **Verified title:** Visualization of Test Information to Assist Fault Localization
- **Authors:** James A. Jones, Mary Jean Harrold, John Stasko
- **Venue/Year:** ICSE '02 (24th International Conference on Software Engineering), ACM, 2002
- **Primary link:** https://doi.org/10.1145/581396.581397
- **Core idea.** The founding paper of spectrum-based fault localization. Run the test suite, record which lines execute in passing vs failing tests (the program spectrum), then rank every line by suspiciousness — how much more strongly it associates with failures than with passes — and visualize the whole program as a color-coded heat map from red (mostly executed by failing tests) to green (mostly passing). The developer's attention is ordered by evidence from many runs rather than by one stack trace.
- **Why it matters for Peaky Peek.** This is the missing inference step for first-bad-decision localization when you have more than one run. A single session gives a chain; a regression-lab bundle gives a spectrum — run the same scenario many times (or many scenarios through the same engine change) and score each decision node by its failed/passed association. Decisions that only occur in failed runs jump out deterministically, with zero LLM judgment — the same math Tarantula used on lines, applied to agent decision nodes.
- **Design takeaway.** Add a "spectrum" view to the regression lab: aggregate a bundle's runs, compute a Tarantula/Ochiai-style suspiciousness score per decision node and per evidence source, and pre-rank the first-bad-decision candidates by it.
- **Caution.** SBFL ranks, it does not convict: a decision that correlates with failure may be a symptom (chosen only when things are already off the rails), not the cause. Keep the score as an ordering heuristic on top of the causal chain, not a verdict.
- **Suggested note slug:** `tarantula-test-information-fault-localization`

### 5. Dapper, a Large-Scale Distributed Systems Tracing Infrastructure

- **Verified title:** Dapper, a Large-Scale Distributed Systems Tracing Infrastructure (Google Technical Report dapper-2010-1, April 2010)
- **Authors:** Benjamin H. Sigelman, Luiz André Barroso, Mike Burrows, Pat Stephenson, Manoj Plakal, Donald Beaver, Saul Jaspan, Chandan Shanbhag
- **Venue/Year:** Google Technical Report, 2010
- **Primary link:** https://research.google.com/archive/papers/dapper-2010-1.pdf (primary PDF, fetched and read)
- **Core idea.** The design that became the model for every distributed tracing system (Zipkin, Jaeger, OpenTelemetry). Traces are trees of spans; instrumented services propagate trace context and emit span annotations. The paper derives three application-level requirements — ubiquitous deployment, continuous monitoring, application-level transparency — and shows annotated (instrumented) monitoring beats black-box/inference-based monitoring: one compared system using inference-based monitoring "mistakenly attribut[es] causality to unrelated events," which annotated instrumentation avoids by making causality explicit. It also treats recording cost seriously (even least-aggressive sampling at 1 sample per 1024 requests kept sampled requests below 0.01%) and safety: annotated instrumentation records limited metadata and no payload data, protecting sensitive information by design.
- **Why it matters for Peaky Peek.** The black-box recorder is a Dapper for agents, and the paper is its design brief: propagate explicit causal identifiers across model calls, tool calls, and decisions instead of inferring causality afterwards; keep per-event metadata cheap; deliberately record structure, not payloads (which also matches Peaky Peek's redaction stance). Its inference-vs-annotation finding is the scientific argument for Peaky Peek's deterministic trace-derived attribution over after-the-fact LLM inference of causes.
- **Design takeaway.** Formalize the recorder's event schema as span trees with propagated context (trace/span ids on every SDK event, auto-patch adapters included), and add a documented "no payload by default" policy statement per event type, Dapper-style.
- **Caution.** Dapper samples and drops; Peaky Peek audits. Sampling is exactly what an audit console cannot do — adopt the span model and safety practice, not the sampling philosophy.
- **Suggested note slug:** `dapper-distributed-tracing`

### 6. Trust in Automation: Designing for Appropriate Reliance

- **Verified title:** Trust in Automation: Designing for Appropriate Reliance
- **Authors:** John D. Lee, Katrina A. See
- **Venue/Year:** Human Factors, 46(1):50–80, 2004
- **Primary link:** https://doi.org/10.1518/hfes.46.1.50_30392
- **Core idea.** The canonical human-factors paper on calibrated trust. Trust is only useful if calibrated: overtrust causes misuse (relying on automation beyond its capability), undertrust causes disuse (ignoring capable automation). The goal is therefore appropriate reliance, and trust develops along three information dimensions — performance (what it did), process (how it works), and purpose (why it exists / for what it is designed). The paper's design guidance is to make these bases observable so people can calibrate trust to actual ability rather than to appearance.
- **Why it matters for Peaky Peek.** This is the scientific justification for the whole trust surface: the explainable trust score is a calibration instrument, not a grade, and the verdict card's three postures (act / verify-first / do-not-act) are literally reliance guidance — the product deciding, per run, where on the misuse–disuse line the operator should sit. Peaky Peek's five questions map onto Lee & See's trust bases: what happened/with what result = performance; why/with what evidence = process; the task framing = purpose.
- **Design takeaway.** Audit the trust-score explanation against the three bases: each score should expose a performance basis (verification outcomes), a process basis (which checks ran, what the recorder saw), and a purpose basis (what class of task this run claimed to do) — and the posture bands should be documented as misuse/disuse guards (verify-first exists to prevent misuse on under-verified runs).
- **Caution.** Lee & See's literature is about human trustors and continuous automation; an agent run is episodic. Don't present the score as the operator's trust — it is evidence for the operator's calibration; keep the human in the loop.
- **Suggested note slug:** `trust-in-automation-lee-see`

### 7. Engineering a Safer World: Systems Thinking Applied to Safety

- **Verified title:** Engineering a Safer World: Systems Thinking Applied to Safety
- **Authors:** Nancy G. Leveson
- **Venue/Year:** The MIT Press, 2012 (open access; DOI 10.7551/mitpress/8179.001.0001)
- **Primary link:** https://doi.org/10.7551/mitpress/8179.001.0001
- **Core idea.** The book introducing STAMP (System-Theoretic Accident Model and Processes): safety as a control problem, not a component-reliability problem. Accidents — including component-interaction accidents where nothing individually "fails" — arise from inadequate enforcement of safety constraints in hierarchical control structures. The operational method is STPA: identify unsafe control actions (a required action not taken, a wrong action taken, an action at the wrong time/order, or an action applied too long/short) and trace them to flaws in the control loop. The book explicitly argues that chain-of-events causality under-models systemic accidents.
- **Why it matters for Peaky Peek.** The verdict card is an STPA-style report for an agent run. The stakes line ("did this run mutate state?") names the hazard; the named posture is the safety constraint to enforce; and Leveson's unsafe-control-action taxonomy is a ready-made classification for first-bad-decision localization: omitted action, wrong action, mistimed action (stale evidence is exactly "action at a wrong time relative to newer facts"), overlong/over-applied action. It also justifies why Peaky Peek audits the whole control loop — model, tools, evidence flow, harness — rather than grading the model alone.
- **Design takeaway.** Type each localized bad decision with Leveson's four unsafe-control-action categories (omitted / wrong / mistimed / overlong) in the failure narrative, and make "mistimed" the formal home of the stale-evidence verdict (acted on evidence a newer fact superseded).
- **Caution.** STAMP assumes designed control structures with specifiable safety constraints; agent behavior is emergent, so STPA-style constraints will be partial. Use it as a reporting taxonomy, not as a promise that every failure is a controllable constraint violation.
- **Suggested note slug:** `engineering-a-safer-world-stamp`

### 8. TRAIL: Trace Reasoning and Agentic Issue Localization

- **Verified title:** TRAIL: Trace Reasoning and Agentic Issue Localization
- **Authors:** Darshan Deshpande, Varun Gangal, Hersh Mehta, et al. (6 authors; Patronus AI)
- **Venue/Year:** arXiv:2505.08638, 2025 (v3 Jun 2025; dataset public on Hugging Face)
- **Primary link:** https://arxiv.org/abs/2505.08638
- **Core idea.** A benchmark for the exact problem Peaky Peek solves: finding what went wrong inside a recorded agent execution. TRAIL contributes a formal error taxonomy and 148 large human-annotated traces from single- and multi-agent workflows (software engineering and information-retrieval settings). Its headline result: modern long-context LLMs are poor at trace debugging — the best model evaluated, Gemini-2.5-pro, scored 11% — i.e., "read the trace and spot the issue" is not solved by bigger models.
- **Why it matters for Peaky Peek.** TRAIL supplies (a) an external, human-labeled ground truth to score Peaky Peek's deterministic first-bad-decision localization against, and (b) the strongest published argument for the product's core stance: if frontier LLMs get 11% at localizing trace errors, an LLM judge in the attribution path is the wrong tool, and deterministic trace-derived attribution is the differentiator. Its error taxonomy is also a completeness-diagnostics checklist for what a recorder must capture.
- **Design takeaway.** Stand up an eval harness that runs Peaky Peek's localizer on the public TRAIL dataset and reports agreement with the human-annotated error locations — publishable evidence for "deterministic beats 11%," and a regression-lab gate for engine changes.
- **Caution.** TRAIL annotates error spans in traces of third-party agent frameworks; its notion of "the error" doesn't always match Peaky Peek's decision-graph nodes, so agreement metrics need a defensible mapping step (not silently gamed).
- **Suggested note slug:** `trail-trace-issue-localization`

---

## Second tier

### 9. Engineering Record and Replay For Deployability: Extended Technical Report (rr)

- **Verified title:** Engineering Record And Replay For Deployability: Extended Technical Report
- **Authors:** Robert O'Callahan, Chris Jones, Nathan Froyd, Kyle Huey, Albert Noll, Nimrod Partush
- **Venue/Year:** arXiv:1705.05937, 2017 (extended TR of the ASPLOS 2017 rr paper; the rr project links this TR as its canonical technical overview)
- **Primary link:** https://arxiv.org/abs/1705.05937
- **Core idea.** The paper behind rr, the record-and-replay debugger. rr captures an execution's nondeterministic events (notably system-call results) so the entire run can be replayed bit-for-bit later, entirely in user space with stock hardware, compilers, runtimes, and OS — no VM recording, no kernel mods, no pervasive instrumentation. Deterministic replay then enables reverse-execution debugging, reproduction of intermittent failures, and forensic "black box" analysis of recorded executions.
- **Why it matters for Peaky Peek.** The founding recipe for the recorder's economics and the adaptive-replay engine: you do not need to record everything, only the nondeterministic inputs — for an agent, the model outputs and tool results; everything else (prompt, code, config) is deterministic context. Recorded runs become reproducible artifacts, which is what makes the regression lab's baseline bundles and the replay UI scientifically sound rather than theatrical.
- **Design takeaway.** Specify the session bundle format as "deterministic core + nondeterministic log" (recorded model responses, tool results, and timestamps), with a replay checker that verifies a re-run reproduces the recorded causal chain — completeness diagnostics can then flag sessions whose replay diverges (missing events).
- **Caution.** rr replays machine execution; agent "replay" re-runs nondeterministic LLM inference only if the recorded outputs are reused. Be precise in UI language: Peaky Peek replays recorded evidence deterministically; it does not make live model calls reproducible.
- **Suggested note slug:** `rr-engineering-record-and-replay`

### 10. τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains

- **Verified title:** τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains
- **Authors:** Shunyu Yao, Noah Shinn, Pedram Razavi, Karthik Narasimhan
- **Venue/Year:** arXiv:2406.12045, 2024
- **Primary link:** https://arxiv.org/abs/2406.12045
- **Core idea.** A benchmark emulating dynamic user–agent conversations with domain-specific API tools (retail, airline), proposing pass^k — the requirement that the agent succeed on all k repeated trials of the same task — as a reliability metric. The abstract's findings: even state-of-the-art function-calling agents like gpt-4o succeed on under 50% of tasks and are "quite inconsistent (pass^8 <25% in retail)". Success is judged by comparing the end-of-conversation database state against the goal state — a check on outcomes, not prose.
- **Why it matters for Peaky Peek.** Two direct imports. (1) pass^k is the honest way for the regression lab to gate engine changes: an engine tweak isn't "fixed" if the same bundle still fails 1 run in 8; worst-of-k over baseline bundles is a stronger gate than mean pass rate. (2) τ-bench's grading — final state vs goal state, deterministic, no judge model — is precisely Peaky Peek's no-LLM-judge verification philosophy and a template for outcome checks in verdict cards (with-what-result).
- **Design takeaway.** Add pass^k as a first-class regression-lab metric: replay each bundle scenario k times (or across k recorded variants) and gate on all-k success; display "reliability: pass^8" style numbers on bundle reports.
- **Caution.** τ-bench measures task success against an oracle goal state; Peaky Peek audits real runs that have no oracle. Adopt the repeated-trial reliability math, not the benchmark tasks, as the claim of coverage.
- **Suggested note slug:** `tau-bench-pass-k-reliability`

### 11. AgentRewind: Recoverable Execution for Long-Horizon LLM Agents

- **Verified title:** AgentRewind: Recoverable Execution for Long-Horizon LLM Agents
- **Authors:** Yu Zhuang, Kefei Chen, Yitong Duan, et al. (6 authors)
- **Venue/Year:** arXiv:2608.14380, 2026 (v1 Aug 2026)
- **Primary link:** https://arxiv.org/abs/2608.14380
- **Core idea.** Argues that prevention (plan refinement, safety checks) is not enough for long-horizon agents because errors made early spread through both context and external environment state in hard-to-reverse ways. AgentRewind is a runtime recovery framework that records aligned checkpoints of the agent's internal context and the controlled environment, so a rewind executor can restore both and let the agent roll back and retry using information from prior attempts. It introduces MettleBench, a benchmark measuring task completion and partial progress on long-horizon engineering assignments, and reports gains in success rate and checklist progress versus baselines across tasks, models, strategies, and harnesses.
- **Why it matters for Peaky Peek.** The "aligned checkpoints" insight is the key correctness constraint for adaptive replay: rewinding an agent's conversation is useless if the filesystem/database the agent mutated is not rewound in lockstep. Peaky Peek's first-bad-decision localization should therefore emit, alongside the decision, the environment checkpoint boundary it belongs to — so replay-from-here is well defined. MettleBench's partial-progress (checklist) scoring also fits evaluating whether a rewind recovered most of the run.
- **Design takeaway.** Extend session bundles with environment fingerprints (hashes of external state at each decision point) so adaptive replay can verify "context and environment are still aligned at this rewind point" and refuse unsafe rewinds where state cannot be restored.
- **Caution.** AgentRewind rewinds to retry with the live agent; Peaky Peek replays to explain. Don't overload replay UX with retry orchestration — expose the checkpoint alignment as evidence, and leave execution policy to the operator.
- **Suggested note slug:** `agentrewind-recoverable-execution`

### 12. FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation (FreshQA)

- **Verified title:** FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation
- **Authors:** Tu Vu, Mohit Iyyer, Xuezhi Wang, et al. (11 authors; Google)
- **Venue/Year:** arXiv:2310.03214, 2023
- **Primary link:** https://arxiv.org/abs/2310.03214
- **Core idea.** FreshQA is a dynamic-QA benchmark mixing fast-changing world-knowledge questions with evergreen ones, plus false-premise questions "that need to be debunked." Findings: models are trained once and never updated, and "all models (regardless of model size) struggle on questions that involve fast-changing knowledge and false premises"; evaluation runs in two modes measuring both correctness and hallucination. The paper also shows prompting and search-augmentation choices (FreshPrompt) substantially move the numbers.
- **Why it matters for Peaky Peek.** The scientific grounding for the stale-evidence check. Staleness only exists because knowledge has different volatility classes — evergreen vs fast-changing — and FreshQA demonstrates that neither model size nor search alone fixes acting on outdated facts. The false-premise category is directly relevant to claim verification: an agent can act on a premise the evidence never supported (Peaky Peek's "unsupported" bucket).
- **Design takeaway.** Tag every evidence item with a volatility class (static reference, fast-changing fact, user-provided) at record time; run staleness cross-checks only on the volatile class, and add a false-premise detector: if a claim's premise contradicts or is absent from cited evidence, that's "unsupported," not just "unverified."
- **Caution.** FreshQA is about QA answers, not agent actions; volatility tagging heuristics will misfire (some "evergreen" facts change). Stale flags should lower trust and trigger verify-first, not auto-fail the run.
- **Suggested note slug:** `freshllms-freshqa-staleness`

### 13. Evaluating Verifiability in Generative Search Engines

- **Verified title:** Evaluating Verifiability in Generative Search Engines
- **Authors:** Nelson F. Liu, Tianyi Zhang, Percy Liang
- **Venue/Year:** Findings of EMNLP 2023 (arXiv:2304.09848)
- **Primary link:** https://arxiv.org/abs/2304.09848
- **Core idea.** Measures whether generated, citation-bearing text is actually verifiable, decomposing verifiability into citing comprehensively (citation recall) and accurately (citation precision) — with attribution "independent of the truth" of statements, judged by humans against only the retrieved sources. Results across major generative search engines: "on average, a mere 51.5% of generated sentences are fully supported by citations and only 74.5% of citations support" their sentences. The paper recommends systems attribute to trustworthy sources and make the retrieval corpus explicit to users.
- **Why it matters for Peaky Peek.** This is the measurement model behind the claim-verification taxonomy: each claim is checked against the evidence actually cited, independent of real-world truth — exactly Peaky Peek's deterministic, trace-derived check (verified / partially verified / contradicted / unsupported / unverified). Per-run citation-precision-style ratios give the trust score an explainable, per-claim auditable basis rather than a vibes number.
- **Design takeaway.** Report per-run verified/partially-verified/unsupported fractions as headline metrics (the analog of citation precision), and surface the evidence corpus per claim ("checked against these 3 retrieved chunks"), mirroring the paper's corpus-explicitness recommendation.
- **Caution.** Their "supported" is human judgment; Peaky Peek's must be mechanical entailment/consistency checks against recorded evidence. Expect the deterministic version to be stricter and noisier on paraphrase — tune toward "partially verified" rather than binary fail.
- **Suggested note slug:** `verifiability-generative-search-engines`

### 14. Locating and Editing Factual Associations in GPT (ROME)

- **Verified title:** Locating and Editing Factual Associations in GPT
- **Authors:** Kevin S. Meng, David Bau, Alex Andonian, Yonatan Belinkov
- **Venue/Year:** NeurIPS 2022 (arXiv:2202.05262)
- **Primary link:** https://arxiv.org/abs/2202.05262
- **Core idea.** The paper that gave "causal tracing" its modern meaning: a causal intervention on model internals that identifies which neuron activations are decisive for a factual prediction — running the model clean, corrupting the run, then restoring activations piecewise and measuring which restores restore the correct output. It localizes factual recall to mid-layer feed-forward modules processing the subject tokens, and ROME edits a specific factual association via a rank-one weight update while preserving behavior elsewhere.
- **Why it matters for Peaky Peek.** Lineage for the causal-tracing pillar's methodology: attribution via controlled intervention — clean run, corrupted run, measure what restores — is exactly the evidence-ablation experiment Peaky Peek can run deterministically on recorded traces (no model internals needed). It grounds the phrase "causal tracing" in the literature the README name-checks, while Peaky Peek applies the same experimental logic at the evidence layer instead of the activation layer.
- **Design takeaway.** Implement "evidence ablation" in the audit panel: for a chosen decision, replay the recorded decision logic with one evidence item removed or replaced (e.g., the superseding fact swapped in) and report whether the decision/claim changes — an ablation-style causal-importance score per evidence item.
- **Caution.** ROME operates on weights and activations inside one model; Peaky Peek must never over-claim neural-level explanation. Trace-level ablation shows which recorded inputs the outcome was sensitive to — not what the network "believed."
- **Suggested note slug:** `rome-locating-factual-associations`

### 15. Human Error

- **Verified title:** Human Error
- **Authors:** James Reason
- **Venue/Year:** Cambridge University Press, 1990 (DOI 10.1017/cbo9781139062367)
- **Primary link:** https://doi.org/10.1017/cbo9781139062367
- **Core idea.** The founding text of modern error analysis. Reason distinguishes active failures — the errors committed at the human–system interface, whose effects are felt near in time and place — from latent conditions: dormant weaknesses (design flaws, poor procedures, stale data) laid down earlier in a system, which line up with local triggers to let an accident through (the "Swiss cheese" image of layered defenses with holes). The book's core teaching: blame the active error, but hunt the latent conditions, because they are where prevention lives.
- **Why it matters for Peaky Peek.** A precise framing for the failure narrative: the first bad decision is the active failure, but Peaky Peek's completeness diagnostics, stale-evidence detection, and weak-tool-data findings are the latent conditions — stale retrieved facts, missing instrumentation, ambiguous instructions — that made the bad decision likely. This justifies the verdict card reporting both the localized decision and its enabling conditions, instead of a single "the model was wrong."
- **Design takeaway.** Split the failure narrative into "active error" (the first bad decision) and "latent conditions" (all upstream findings that plausibly enabled it), and require at least one latent-condition candidate before a do-not-act verdict can be marked resolved.
- **Caution.** Reason's model is about human cognition and organizational defenses; agent "latent conditions" are an analogy. Don't stretch it into claims about model intention — keep the language mechanistic (superseded fact, dropped event).
- **Suggested note slug:** `human-error-reason-latent-failures`

### 16. Characterizing Faults in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes

- **Verified title:** Characterizing Faults in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes
- **Authors:** Mehil B. Shah, Mohammad Mehdi Morovati, Mohammad Masudur Rahman, Foutse Khomh (et al.)
- **Venue/Year:** arXiv:2603.06847, 2026 (v1 Mar 2026, v2 May 2026)
- **Primary link:** https://arxiv.org/abs/2603.06847
- **Core idea.** An empirical study of faults in real agentic-AI deployments: mining 13,602 issues and pull requests across 40 agentic-system repositories, then analyzing 385 faults via stratified sampling. It produces a taxonomy of 34 fault types organized into four architectural dimensions, links fault types to symptoms and root causes with Apriori association-rule mining, and validates with a developer study of 145 practitioners. Symptom areas include structured-output interpretation, tool calls, runtime execution, and exception handling; root causes include data schema mismatches, dependency drift, state-management complexity, and model interface instability.
- **Why it matters for Peaky Peek.** The empirical base for completeness diagnostics and recorder robustness: these are the faults production agent stacks actually exhibit, at the model–harness boundary. Peaky Peek's instrumentation must not silently die on exactly these (schema mismatch at a tool boundary = dropped events = incomplete session), and the root-cause list doubles as a checklist the completeness diagnostics should actively test for (e.g., detect tool-output schema drift between recorded calls).
- **Design takeaway.** Turn the four dimensions into a self-test suite for the recorder: inject each symptom class (malformed tool output, state loss, exception mid-chain) into a demo agent and assert the session is flagged "incomplete" with the specific gap named — making completeness diagnostics provably non-silent.
- **Caution.** This is GitHub-mined harness/framework fault research, not model-behavior research; it says little about reasoning failures. Use it for instrumentation and diagnostics coverage, not for claim-verification design.
- **Suggested note slug:** `agentic-ai-fault-taxonomy`

### 17. Model or Harness? An Interaction-Centric Taxonomy for Localizing Agent Failures

- **Verified title:** Model or Harness? An Interaction-Centric Taxonomy for Localizing Agent Failures
- **Authors:** Harsh Raj, Vipul Gupta, Anas Mahmoud, et al. (7 authors; Scale AI)
- **Venue/Year:** arXiv:2607.28802, 2026 (v1 Jul 2026)
- **Primary link:** https://arxiv.org/abs/2607.28802
- **Core idea.** Observes that existing evaluations "reduce agent failures to system-level outcomes, obscuring where the fault originated and which intervention would improve" performance. Proposes localizing failures to interactions rather than components: 41 failure modes, each assigned to an edge between two components (model, harness, user, tools, memory, environment) plus a fault side indicating where the repair belongs. Reproducibility was tested with independent reasoning agents as judges across four frontier models, with the strongest judge reaching Cohen's κ = 0.76 against human category labels.
- **Why it matters for Peaky Peek.** The edge-plus-fault-side structure is a clean output format for first-bad-decision localization: Peaky Peek already finds the node in the causal chain; this work argues the node alone is not actionable — you need the interaction it occurred on (decision→tool, tool→model, memory→decision) and the side at fault (model output vs harness bug vs tool data). That directly guides the operator's next move and matches Peaky Peek's stance that the model is not always the culprit.
- **Design takeaway.** Extend the first-bad-decision record with two deterministic fields derived from the trace: `interaction_edge` (the two components the bad step connects) and `fault_side` (model-produced / harness-recorded / tool-returned), inferred from where in the chain the bad data originated.
- **Caution.** Their reproducibility check uses LLM judges (κ = 0.76). Peaky Peek's fault_side must come from trace facts (which component emitted the bad artifact), and where the trace can't decide, say "undetermined" — don't borrow the judge.
- **Suggested note slug:** `model-or-harness-fault-side-taxonomy`

---

## Checked and rejected

- **Quinn & Alvaro, "Deterministic Record-and-Replay" (CACM 68(5), 2025; Queue 22(4), 2024 — Crossref-verified).** Excellent modern statement of "record only the nondeterministic actions," but it duplicates the rr entry's design takeaway for Peaky Peek with no additional action; fold a mention into the rr note instead.
- **W3C PROV-DM (PROV Data Model, W3C Recommendation 2013).** A specification, not research; the provenance/data-lineage angle is already carried by the covered survey "From Agent Traces to Trust," and no new design takeaway emerged beyond "model derivations as edges," which Weiser slicing + Dapper covers more usefully.
- **DoublePlay (Cui et al., parallel record-replay) and omniscient debugging (B. Lewis).** Considered for the record-replay lineage, not pursued: DoublePlay's core problem (deterministic replay of multi-core thread interleavings) has no analog in single-threaded agent traces, and omniscient debugging lacks a stable canonical citable primary (workshop/website forms only) — rr (with its extended TR) carries the whole lineage.
- **Google SRE book, postmortem-culture chapter (sre.google, O'Reilly 2016).** Canonical practice literature and a nice framing for blameless audit reports, but it adds no design takeaway beyond what Leveson (control/constraint framing) and Reason (active vs latent) already provide for the verdict-card UX.
- **"An Empirical Study on Failures in Automated Issue Solving" (arXiv, Sep 2025).** Verified to exist via search, but its scope (SWE-agent issue-resolution failures) and failure-analysis angle are already better covered for Peaky Peek's purposes by MAST (#1), TRAIL (#8), and the agentic fault taxonomy (#16); no distinct design takeaway.
