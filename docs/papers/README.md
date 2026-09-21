# Paper Notes

This section turns each inspiration paper into a short working note for the repo.

Each note uses the same structure:

- `Core idea`: the shortest accurate summary of the paper
- `Why it matters here`: the transfer to `agent_debugger`
- `Key takeaways for the repo`: the most relevant lessons
- `Concrete opportunities`: changes the repo could actually make
- `Caution`: what not to over-apply
- `Best next experiment`: the highest-value thing to try first

## Papers

- [Towards a Neural Debugger for Python](./towards-a-neural-debugger-for-python.md)
- [MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning](./mssr-memory-aware-adaptive-replay.md)
- [CXReasonAgent: Evidence-Grounded Diagnostic Reasoning Agent for Chest X-rays](./cxreasonagent-evidence-grounded-diagnostic-reasoning.md)
- [NeuroSkill(tm): Proactive Real-Time Agentic System Capable of Modeling Human State of Mind](./neuroskill-proactive-real-time-agentic-system.md)
- [Learning When to Act or Refuse: Guarding Agentic Reasoning Models for Safe Multi-Step Tool Use](./learning-when-to-act-or-refuse.md)
- [Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts](./policy-parameterized-prompts.md)
- [AgentTrace: Causal Graph Tracing for Root Cause Analysis](./agenttrace-causal-graph-tracing-for-root-cause-analysis.md)
- [XAI for Coding Agent Failures: Transforming Raw Execution Traces into Actionable Insights](./xai-for-coding-agent-failures.md)
- [REST: Receding Horizon Explorative Steiner Tree for Zero-Shot Object-Goal Navigation](./rest-receding-horizon-explorative-steiner-tree.md)
- [FailureMem: A Failure-Aware Multimodal Framework for Autonomous Software Repair](./failuremem-failure-aware-autonomous-software-repair.md)
- [From Agent Traces to Trust: Evidence Tracing and Execution Provenance in LLM Agents](./from-agent-traces-to-trust-provenance-survey.md)
- [Evaluating Goal Drift in Language Model Agents](./evaluating-goal-drift-in-language-model-agents.md)
- [Which Agent Causes Task Failures and When? (Who&When)](./who-and-when-automated-failure-attribution.md)
- [Tracing Agentic Failure from the Flow of Success (OAT)](./tracing-agentic-failure-from-the-flow-of-success.md)
- [Calibrated Trust in Dealing with LLM Hallucinations](./calibrated-trust-in-dealing-with-llm-hallucinations.md)
- [Why Do Multi-Agent LLM Systems Fail? (MAST)](./why-do-multi-agent-llm-systems-fail-mast.md)
- [Why Programs Fail: A Guide to Systematic Debugging](./why-programs-fail-systematic-debugging.md)
- [Program Slicing](./weiser-program-slicing.md)
- [Visualization of Test Information to Assist Fault Localization (Tarantula)](./tarantula-test-information-fault-localization.md)
- [Dapper, a Large-Scale Distributed Systems Tracing Infrastructure](./dapper-distributed-tracing.md)
- [Trust in Automation: Designing for Appropriate Reliance](./trust-in-automation-lee-see.md)
- [Engineering a Safer World (STAMP)](./engineering-a-safer-world-stamp.md)
- [TRAIL: Trace Reasoning and Agentic Issue Localization](./trail-trace-issue-localization.md)
- [Engineering Record and Replay for Deployability (rr)](./rr-engineering-record-and-replay.md)
- [τ-bench: Tool-Agent-User Interaction](./tau-bench-pass-k-reliability.md)
- [AgentRewind: Recoverable Execution for Long-Horizon LLM Agents](./agentrewind-recoverable-execution.md)
- [FreshLLMs / FreshQA](./freshllms-freshqa-staleness.md)
- [Evaluating Verifiability in Generative Search Engines](./verifiability-generative-search-engines.md)
- [Locating and Editing Factual Associations in GPT (ROME)](./rome-locating-factual-associations.md)
- [Human Error](./human-error-reason-latent-failures.md)
- [Characterizing Faults in Agentic AI](./agentic-ai-fault-taxonomy.md)
- [Model or Harness? Localizing Agent Failures](./model-or-harness-fault-side-taxonomy.md)

Sources for the 2026-09-21 additions, with per-work verification against
primary sources: [science-foundations candidates digest](../research/2026-09-21-science-foundations-candidates.md).

## How To Read These Notes

These are not literature reviews. They are design notes.

The goal is to answer one question per paper:

- what should this repo do differently because this paper exists
