# Research Inspiration

These papers are here because they push on the same problems this project is trying to solve: debugging, replay, evidence, safety, and control in agent systems.

## Papers

- [Towards a Neural Debugger for Python](https://arxiv.org/abs/2603.09951v1)
  Why it matters here: debugger-native interactions, breakpoint-style inspection, and execution-conditioned reasoning.

- [MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning](https://arxiv.org/abs/2603.09892v1)
  Why it matters here: adaptive replay, retention-aware sampling, and trace prioritization.

- [CXReasonAgent: Evidence-Grounded Diagnostic Reasoning Agent for Chest X-rays](https://arxiv.org/abs/2602.23276v1)
  Why it matters here: evidence-grounded decision making, auditability, and tool-backed verification.

- [NeuroSkill(tm): Proactive Real-Time Agentic System Capable of Modeling Human State of Mind](https://arxiv.org/abs/2603.03212v1)
  Why it matters here: real-time agent loops and state-aware monitoring patterns.

- [Learning When to Act or Refuse: Guarding Agentic Reasoning Models for Safe Multi-Step Tool Use](https://arxiv.org/abs/2603.03205v1)
  Why it matters here: explicit safety checks, refusal states, and traceability for multi-step tool use.

- [Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts](https://arxiv.org/abs/2603.09890v1)
  Why it matters here: observability and control for multi-agent dialogue behavior.

- [AgentTrace: Causal Graph Tracing for Root Cause Analysis](https://arxiv.org/abs/2603.14688)
  Why it matters here: reconstructing causal chains from execution logs, tracing failures backward, and ranking likely upstream causes.

- [XAI for Coding Agent Failures: Transforming Raw Execution Traces into Actionable Insights](https://arxiv.org/abs/2603.05941)
  Why it matters here: turning raw failure traces into structured explanations that operators can act on quickly.

- [REST: Receding Horizon Explorative Steiner Tree for Zero-Shot Object-Goal Navigation](https://arxiv.org/abs/2603.18624)
  Why it matters here: frontier-based exploration and tree-guided search over large unknown state spaces.

- [FailureMem: A Failure-Aware Multimodal Framework for Autonomous Software Repair](https://arxiv.org/abs/2603.17826)
  Why it matters here: learning from failed repair attempts instead of treating them as disposable noise.

For repo-oriented notes on each paper, see [Paper Notes](./papers/README.md).

## How To Use These Papers In This Repo

Use these papers as design pressure, not as decoration.

Practical examples:

- use replay research to improve checkpointing and event prioritization
- use evidence-grounded reasoning research to improve decision event structure
- use safety research to add refusal and guardrail events
- use multi-agent control research to design better policy and prompt observability
- use causal tracing research to rank likely root causes after an error or refusal
- use XAI research to turn raw traces into concise failure narratives with evidence links
- use repair-memory research to preserve failed attempts and guide later debugging
- use exploration research to navigate large trace graphs without inspecting every branch

## Reading Strategy

Read the papers at two levels:

1. what capability or discipline the paper demonstrates
2. what minimum version of that capability belongs in this repo

That keeps the docs grounded. The goal is not to import paper vocabulary into the product. The goal is to turn research into better event design, better replay, and better debugging workflows.
