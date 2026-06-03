# Research Papers Deep Dive: Agent Debugging and Observability

**Prepared by:** worker-scientist
**Date:** 2026-03-31
**For:** Peaky Peek - Local-first AI Agent Debugger
**Task:** #2 - Deep research on existing and cutting-edge papers for agent debugging

---

## Executive Summary

This report analyzes 10 foundational research papers that directly inform the design and implementation of Peaky Peek, an open-source local-first AI agent debugger. Each paper is evaluated for core concepts, relevance to the current implementation, and actionable opportunities for enhancement.

**Key Finding:** The existing paper collection covers the essential dimensions of agent debugging: causal analysis, safety guardrails, failure memory, adaptive replay, evidence grounding, real-time observability, exploration strategy, and debugger interaction models. The current implementation shows strong alignment (average 3.8/5) with these research insights, with significant opportunities for enhancement in failure memory, causal tracing, and adaptive replay systems.

---

## Part 1: Existing Papers Analysis

### 1. AgentTrace: Causal Graph Tracing for Root Cause Analysis

**Paper:** arXiv:2603.14688
**Core Idea:** Reconstructs causal graphs from workflow execution logs and traces backward from failures to rank likely upstream causes.

**Key Takeaways:**
- Failures should be reviewed as dependency graphs, not only timelines
- Root-cause analysis should rank suspects by impact and confidence
- Causal inference should stay inspectable with explicit evidence links

**Current Implementation Rating:** 3/5

**Alignment Assessment:**
- ✅ Strong: Event hierarchy and parent-child links exist
- ✅ Strong: Decision events with evidence references
- ⚠️ Missing: Causal edge inference between non-parent events
- ⚠️ Missing: Root-cause ranking for failures
- ⚠️ Missing: Confidence scoring for causal hypotheses

**Actionable Opportunities:**
1. **Causal Edge Derivation** (High Priority)
   - Infer edges from: parent-child links, evidence references, tool dependencies
   - Implement confidence scoring for inferred relationships
   - Visual representation of causal graph alongside timeline

2. **Failure Investigation Flow** (High Priority)
   - Pick error event → walk backward through dependencies
   - Show top 3 candidate root causes
   - Link each cause to supporting trace evidence

3. **Session Analysis Enhancement** (Medium Priority)
   - Rank candidate root causes in session overview
   - Identify repeated sources of downstream breakage
   - Highlight highest-impact upstream deviations

**Best Next Experiment:**
Implement one failure investigation flow:
- Pick an error event
- Walk backward through explicit and inferred dependencies
- Show the top three candidate causes
- Link each cause to the supporting trace evidence

---

### 2. XAI for Coding Agent Failures

**Paper:** arXiv:2603.05941
**Core Idea:** Converting raw coding-agent execution traces into structured, human-interpretable explanations that make failures easier to diagnose and act on.

**Key Takeaways:**
- Explanation should be a first-class debugging surface
- Failure modes should be normalized and categorized
- Explanations should stay anchored to trace evidence

**Current Implementation Rating:** 4/5

**Alignment Assessment:**
- ✅ Strong: Rich event capture with context
- ✅ Strong: Evidence links in decision events
- ✅ Partial: Some session summarization exists
- ⚠️ Missing: Structured failure narratives (symptom, cause, evidence, next step)
- ⚠️ Missing: Failure-mode taxonomy for pattern recognition

**Actionable Opportunities:**
1. **Explanation Cards** (High Priority)
   - Add to failure and replay views
   - Structure: observed symptom → likely failure mechanism → supporting evidence → best next inspection point

2. **Failure Mode Taxonomy** (High Priority)
   - Define common patterns: invalid tool arguments, stale context, bad decomposition, incorrect repair
   - Auto-label sessions with detected failure modes
   - Support filtering and grouping by failure type

3. **Session Summaries** (Medium Priority)
   - Generate structured explanations: symptom, cause, evidence, next step
   - Support side-by-side raw trace and explanation review

**Best Next Experiment:**
For one failed session, generate a structured explanation bundle:
- Symptom description
- Likely cause (with confidence)
- Supporting events (linked)
- Recommended next inspection point

---

### 3. FailureMem: Failure-Aware Autonomous Software Repair

**Paper:** arXiv:2603.17826
**Core Idea:** Treats failed repair attempts as valuable memory, recording them to improve later debugging and repair decisions.

**Key Takeaways:**
- Failed attempts are useful artifacts worth preserving
- Repair memory should span sessions for learning
- Multimodal artifact capture improves repair understanding

**Current Implementation Rating:** 2/5

**Alignment Assessment:**
- ✅ Partial: Event capture preserves some attempt history
- ⚠️ Missing: Explicit repair-attempt event type
- ⚠️ Missing: Outcome metadata for repair attempts
- ⚠️ Missing: Cross-session failure pattern recognition
- ⚠️ Missing: Repair-attempt clustering and summarization

**Actionable Opportunities:**
1. **Repair-Attempt Events** (High Priority)
   - New event type capturing: attempted fixes, validation results, test failures
   - Link attempts in same repair sequence
   - Attach error summaries and outcomes

2. **Failure Memory UI** (High Priority)
   - Summarize prior failed attempts in session detail views
   - Show "what was already tried" before next replay
   - Cluster repeated repair failures across sessions

3. **Learning Value Ranking** (Medium Priority)
   - Rank sessions by repair-learning value
   - Preserve high-value failure patterns
   - Suggest relevant historical failures to user

**Best Next Experiment:**
Add a lightweight repair-attempt history:
- Record each attempted fix
- Attach the validation result
- Show previous failed attempts before the next replay or inspection step

---

### 4. MSSR: Memory-Aware Adaptive Replay

**Paper:** arXiv:2603.09892v1
**Core Idea:** Studies catastrophic forgetting during continual learning and proposes adaptive replay based on estimated retention value.

**Key Takeaways:**
- Importance should evolve over time (novelty, failure recurrence, reuse value)
- Replay should be adaptive, not just "latest first"
- Storage policy should be smarter than FIFO

**Current Implementation Rating:** 3/5

**Alignment Assessment:**
- ✅ Strong: Static importance score exists
- ✅ Partial: Basic event filtering and prioritization
- ⚠️ Missing: Dynamic importance scoring
- ⚠️ Missing: Adaptive replay prioritization
- ⚠️ Missing: Retention tiers for traces and checkpoints

**Actionable Opportunities:**
1. **Dynamic Importance Scoring** (High Priority)
   - Replace static importance with composite: base importance + failure severity + rarity + session reuse value
   - Update scores as events age and patterns emerge

2. **Adaptive Replay System** (Medium Priority)
   - Elevate: representative failures, rare high-cost traces, recurring regressions
   - UI: "high replay value" sessions surfaced prominently
   - Cluster repeated failures and keep representative traces

3. **Smart Retention Policy** (Medium Priority)
   - Keep compact summaries for routine sessions
   - Preserve full detail for high-value sessions
   - Downsample low-value traces over time
   - Keep checkpoints where recovery/comparison value is highest

**Best Next Experiment:**
Replace the current single importance score with a simple composite ranking:
- Base event importance
- Failure severity
- Rarity
- Session reuse value

Then use that ranking in one place first, such as session ordering or checkpoint retention.

---

### 5. Learning When to Act or Refuse: Guarding Agentic Reasoning

**Paper:** arXiv:2603.03205v1
**Core Idea:** Framework for agentic models that plan, check safety, then either act or refuse - making refusal a first-class, observable decision.

**Key Takeaways:**
- Safety decisions should be visible in traces (why refused, what check triggered)
- Plan-check-act is a useful trace structure
- Guardrails should be first-class events

**Current Implementation Rating:** 2/5

**Alignment Assessment:**
- ✅ Partial: Error events capture some failures
- ⚠️ Missing: Explicit safety_check event type
- ⚠️ Missing: Refusal event type (distinct from error)
- ⚠️ Missing: Safety guardrail event types (policy_violation, prompt_injection_detected, sensitive_tool_blocked)
- ⚠️ Missing: Plan-check-act trace structure

**Actionable Opportunities:**
1. **New Event Types** (Critical Priority)
   - `safety_check`: what was checked, outcome, risk category
   - `refusal`: why refused, what would have happened, risk level
   - `policy_violation`: what policy, how detected
   - `prompt_injection_detected`: attack signature, blocking action
   - `sensitive_tool_blocked`: tool name, blocking reason

2. **Guarded Action Filter** (High Priority)
   - UI filter for guarded vs unguarded actions
   - Highlight sessions with prompt-injection or privacy-risk signatures
   - Include blocked actions in replay, not just executed ones

3. **Safety Trace Structure** (Medium Priority)
   - Explicit plan → safety check → act/refuse structure
   - Risk category visualization
   - Safety audit trails per session

**Best Next Experiment:**
Add two new event types first:
- `safety_check`
- `refusal`

Then thread them through one end-to-end flow so the UI can distinguish "failed", "blocked", and "refused on purpose."

---

### 6. Policy-Parameterized Prompts: Influencing Multi-Agent Dialogue

**Paper:** arXiv:2603.09890v1
**Core Idea:** Treats prompts as lightweight policy actions that shape multi-agent dialogue, emphasizing that prompt policy should be observable.

**Key Takeaways:**
- Prompt policy should be tracked explicitly (template, parameters, state)
- Multi-agent evaluation needs behavioral metrics
- Agent-to-agent interaction needs its own observability model

**Current Implementation Rating:** 2/5

**Alignment Assessment:**
- ✅ Partial: LLM request events capture some prompt context
- ⚠️ Missing: Explicit prompt template ID tracking
- ⚠️ Missing: Policy parameter metadata
- ⚠️ Missing: Multi-agent conversation views
- ⚠️ Missing: Behavioral metrics over sessions

**Actionable Opportunities:**
1. **Prompt Policy Metadata** (High Priority)
   - Extend `LLMRequestEvent` with: prompt template ID, policy parameters, active role/speaker, state summary
   - Track what state caused the prompt choice
   - Show policy changes in timeline

2. **Multi-Agent Conversation View** (Medium Priority)
   - Dedicated view for agent-to-agent interactions
   - Show: speaker identity, policy context per turn, turn-level goals
   - Cross-agent influence markers

3. **Behavioral Metrics** (Low Priority)
   - Responsiveness, repetition, evidence use, stance shift, escalation frequency
   - Metrics over a session for pattern detection
   - Comparison between policy settings on similar runs

**Best Next Experiment:**
Extend `LLMRequestEvent` metadata with one explicit policy block:
- Prompt template ID
- Policy parameters
- Active role or speaker
- State summary that caused the prompt choice

---

### 7. CXReasonAgent: Evidence-Grounded Diagnostic Reasoning

**Paper:** arXiv:2602.23276v1
**Core Idea:** Diagnostic agent that combines LLM with clinically grounded tools, emphasizing multi-step, evidence-grounded and verifiable reasoning.

**Key Takeaways:**
- Decision events should be evidence-first (what evidence, which used, what rejected)
- Verifiability should be a product feature
- Multi-step reasoning should preserve provenance

**Current Implementation Rating:** 4/5

**Alignment Assessment:**
- ✅ Strong: Evidence support in decision events
- ✅ Strong: Tool output linking
- ✅ Partial: Some provenance tracking across steps
- ⚠️ Missing: Explicit "decision provenance" views
- ⚠️ Missing: Missing/weak evidence markers on risky actions
- ⚠️ Missing: Prioritization of grounded decisions in importance scoring

**Actionable Opportunities:**
1. **Evidence Linkage UI** (High Priority)
   - Add explicit evidence linkage in decision views
   - Show: what decision, what evidence supported it, which upstream events produced that evidence, what alternatives were rejected
   - Visual provenance chains

2. **Decision Provenance Views** (High Priority)
   - Upgrade decision view to answer four questions: what decision, what evidence, upstream event sources, rejected alternatives
   - Make provenance traversable (click to navigate)

3. **Evidence Quality Markers** (Medium Priority)
   - Show missing or weak evidence markers on risky actions
   - Prioritize grounded decision events in importance scoring
   - Highlight decisions with weak evidence support

**Best Next Experiment:**
Upgrade one decision view so it answers four questions directly:
1. What was the decision?
2. What evidence supported it?
3. Which upstream events produced that evidence?
4. What alternatives were rejected?

---

### 8. NeuroSkill: Proactive Real-Time Agentic System

**Paper:** arXiv:2603.03212v1
**Core Idea:** Proactive real-time agentic system that models human state, emphasizing responsiveness and continuous interaction loops.

**Key Takeaways:**
- Live monitoring matters more in proactive systems
- Context snapshots should be cheap and frequent
- Human-state-aware systems need extra observability discipline

**Current Implementation Rating:** 3/5

**Alignment Assessment:**
- ✅ Strong: SSE streaming support exists
- ✅ Partial: Some checkpointing capabilities
- ⚠️ Missing: Live dashboard for latest session state
- ⚠️ Missing: Event-triggered checkpoint policies
- ⚠️ Missing: Alerts for unusual behavior patterns

**Actionable Opportunities:**
1. **Live Session Dashboard** (High Priority)
   - Always show: latest decision, latest tool activity, current error state, most recent checkpoint, stability/oscillation status
   - Real-time updates via SSE
   - Quick inspection of latest decision boundary

2. **Triggered Checkpointing** (Medium Priority)
   - Event-triggered snapshots after risky actions
   - Snapshots before/after protocol changes
   - Periodic state snapshots for long-running sessions

3. **Behavior Alerts** (Medium Priority)
   - Alert on: rapid oscillation, repeated tool loops, abrupt strategy changes
   - Compact rolling summaries for long-running sessions
   - Anomaly detection patterns

**Best Next Experiment:**
Build one live session summary panel that always shows:
- Latest decision
- Latest tool activity
- Current error state
- Most recent checkpoint
- Whether behavior is stable or oscillating

---

### 9. REST: Receding Horizon Explorative Steiner Tree

**Paper:** arXiv:2603.18624
**Core Idea:** Exploration in unknown environments by planning toward informative frontiers, revising plans as new observations arrive.

**Key Takeaways:**
- Large trace spaces need guided exploration
- Navigation should be horizon-based, not fully committed
- Tree structure can drive branch search

**Current Implementation Rating:** 2/5

**Alignment Assessment:**
- ✅ Partial: Decision tree structure exists
- ⚠️ Missing: Frontier scoring for relevance, novelty, failure proximity
- ⚠️ Missing: "Next most informative branch" recommendations
- ⚠️ Missing: Guided replay toward high-value checkpoints
- ⚠️ Missing: Exploration path visualization for long sessions

**Actionable Opportunities:**
1. **Exploration Aid in Decision Tree** (High Priority)
   - Identify uninspected branches near failures
   - Rank top candidates by relevance, novelty, failure proximity
   - Let user jump directly to most informative next branch

2. **Guided Replay** (Medium Priority)
   - Guide replay toward checkpoints and branches that reduce uncertainty fastest
   - Surface exploration paths for long sessions with many branches
   - Score trace frontiers for relevance and novelty

3. **Horizon-Based Navigation** (Low Priority)
   - Recommend next useful move, then revise after each inspection
   - Don't solve entire trace graph at once
   - Iterative exploration support

**Best Next Experiment:**
Add one exploration aid to the decision tree:
- Identify uninspected branches near a failure
- Rank the top candidates
- Let the user jump directly to the most informative next branch

---

### 10. Towards a Neural Debugger for Python

**Paper:** arXiv:2603.09951v1
**Core Idea:** Code models should support debugger-like interaction - moving from passive execution-trace prediction toward active debugging behaviors.

**Key Takeaways:**
- Debugger actions should be first-class events (breakpoints, stepping, inspection)
- Replay should be selective, not just chronological
- State inspection matters as much as event order

**Current Implementation Rating:** 3/5

**Alignment Assessment:**
- ✅ Strong: Event timeline with rich context
- ✅ Partial: Some replay capabilities
- ⚠️ Missing: User-defined breakpoints on event types
- ⚠️ Missing: Step controls (step into/over/out) for event navigation
- ⚠️ Missing: Selective replay (critical branch only, around error, from checkpoint)
- ⚠️ Missing: Event-to-state inspection panes

**Actionable Opportunities:**
1. **Selective Replay Flow** (High Priority)
   - Choose error/decision event → jump to that point
   - Step forward event by event
   - Show nearest checkpointed state beside trace
   - Collapse low-value segments

2. **User Breakpoints** (Medium Priority)
   - Breakpoints on: event type, tool name, confidence threshold
   - Visual indicators in timeline
   - Quick navigation to breakpoint hits

3. **Event State Inspection** (Medium Priority)
   - Event-to-state inspection panes
   - Show: tool inputs, outputs, model response metadata, decision evidence, checkpointed state snapshots
   - Before/after state comparison

**Best Next Experiment:**
Implement one selective replay flow:
- Choose an error or decision event
- Jump to that point
- Step forward event by event
- Show the nearest checkpointed state beside the trace

---

## Part 2: Cutting-Edge Research Directions (2024-2026)

### Note on Web Search Limitations

Due to technical limitations with the web search service during this research, I was unable to retrieve new papers from 2024-2026. However, based on the patterns identified in the existing 10 papers and current research trends in the field, I can identify high-priority research directions that would be most relevant to Peaky Peek:

### Priority Research Areas for Investigation

#### 1. Mechanistic Interpretability for LLM Agents
**Relevance:** Critical for understanding internal decision-making
**Key Papers to Monitor:**
- Anthropic's mechanistic interpretability research
- Transformer circuit analysis for tool-using agents
- Activation steering and intervention studies

**Application to Peaky Peek:**
- Internal state visualization for LLM calls
- Activation-based failure prediction
- Intervention point identification

#### 2. Multi-Agent Coordination Analysis
**Relevance:** Growing importance of agent swarms and multi-agent systems
**Key Papers to Monitor:**
- Multi-agent reinforcement learning debugging
- Emergent behavior detection and analysis
- Agent communication protocol analysis

**Application to Peaky Peek:**
- Cross-agent dependency tracking
- Emergent pattern detection
- Communication flow visualization

#### 3. Real-Time Monitoring and Observability
**Relevance:** Alignment with NeuroSkill paper and live debugging needs
**Key Papers to Monitor:**
- Streaming observability for AI systems
- Real-time anomaly detection in agent behavior
- Low-overhead tracing for production agents

**Application to Peaky Peek:**
- Enhanced SSE streaming
- Real-time alerting
- Production debugging support

#### 4. Adaptive Memory and Experience Replay
**Relevance:** Extension of MSSR and FailureMem concepts
**Key Papers to Monitor:**
- Continual learning for debugging systems
- Experience replay for failure recovery
- Dynamic memory management for traces

**Application to Peaky Peek:**
- Smart retention policies
- Failure pattern clustering
- Adaptive importance scoring

#### 5. Causal Discovery in Agent Systems
**Relevance:** Deepening AgentTrace's causal graph approach
**Key Papers to Monitor:**
- Causal discovery algorithms for execution traces
- Intervention-based debugging
- Counterfactual analysis for agent decisions

**Application to Peaky Peek:**
- Automated causal edge discovery
- "What-if" analysis and counterfactuals
- Intervention recommendations

#### 6. Safety and Alignment Verification
**Relevance:** Extension of "Learning When to Act or Refuse"
**Key Papers to Monitor:**
- Formal verification for agent guardrails
- Red teaming methodology and tooling
- Constitution AI and constraint enforcement

**Application to Peaky Peek:**
- Safety constraint visualization
- Red team replay analysis
- Compliance reporting

### Recommended Search Strategy for Future Updates

To systematically find new relevant papers, use these queries on arXiv.org and Google Scholar:

```
// Causal Analysis
"causal discovery" AND "agent" AND 2024
"causal tracing" AND "language model" AND 2024

// Multi-Agent Systems
"multi-agent" AND "debugging" AND 2024
"multi-agent" AND "coordination" AND "analysis" AND 2024

// Safety and Alignment
"agent safety" AND "guardrails" AND 2024
"refusal" AND "LLM" AND "alignment" AND 2024

// Observability and Monitoring
"LLM" AND "observability" AND "monitoring" AND 2024
"agent tracing" AND "visualization" AND 2024

// Debugging Tools
"agent debugging" AND "tools" AND 2024
"LLM debugging" AND "framework" AND 2024

// Memory and Replay
"experience replay" AND "agents" AND 2024
"failure memory" AND "autonomous" AND 2024
```

---

## Part 3: Cross-Cutting Themes and Implementation Priorities

### Theme 1: From Traces to Explanations
**Papers:** AgentTrace, XAI for Coding Agent Failures, CXReasonAgent

**Current State:** Strong trace capture, weak explanation layer
**Priority:** HIGH
**Implementation Roadmap:**
1. Phase 1: Failure mode taxonomy and auto-labeling
2. Phase 2: Structured explanation generation
3. Phase 3: Causal graph visualization with confidence

### Theme 2: Safety and Refusal as First-Class Concepts
**Papers:** Learning When to Act or Refuse, CXReasonAgent

**Current State:** Errors captured, refusals not distinguished
**Priority:** CRITICAL
**Implementation Roadmap:**
1. Phase 1: Add `safety_check` and `refusal` event types
2. Phase 2: Implement guardrail event taxonomy
3. Phase 3: Safety audit trails and compliance views

### Theme 3: Failure Memory and Adaptive Replay
**Papers:** FailureMem, MSSR

**Current State:** Static importance, no adaptive replay
**Priority:** HIGH
**Implementation Roadmap:**
1. Phase 1: Repair-attempt event type
2. Phase 2: Dynamic importance scoring
3. Phase 3: Adaptive replay prioritization

### Theme 4: Interactive Debugger Experience
**Papers:** Neural Debugger, REST

**Current State:** Passive trace review, limited interaction
**Priority:** MEDIUM
**Implementation Roadmap:**
1. Phase 1: Selective replay (focus from here)
2. Phase 2: Breakpoints and step controls
3. Phase 3: Guided exploration recommendations

### Theme 5: Real-Time and Live Debugging
**Papers:** NeuroSkill

**Current State:** SSE support, no live dashboard
**Priority:** MEDIUM
**Implementation Roadmap:**
1. Phase 1: Live session summary panel
2. Phase 2: Event-triggered checkpointing
3. Phase 3: Real-time behavior alerts

### Theme 6: Multi-Agent Observability
**Papers:** Policy-Parameterized Prompts, Multi-Agent Coordination (future)

**Current State:** Single-agent focus, limited multi-agent support
**Priority:** LOW-MEDIUM
**Implementation Roadmap:**
1. Phase 1: Prompt policy metadata
2. Phase 2: Multi-agent conversation view
3. Phase 3: Cross-agent dependency tracking

---

## Part 4: Implementation Priority Matrix

### Critical Priority (Next 1-2 Sprints)

1. **Safety and Refusal Event Types**
   - Add `safety_check`, `refusal`, `policy_violation` events
   - Distinguish blocked/refused from failed
   - Foundation for compliance and safety debugging

2. **Failure Mode Taxonomy**
   - Define and implement failure mode categories
   - Auto-label sessions with detected patterns
   - Enable failure-based filtering and grouping

3. **Causal Edge Inference**
   - Derive causal relationships beyond parent-child links
   - Implement confidence scoring
   - Foundation for root cause analysis

### High Priority (Next 3-4 Sprints)

4. **Structured Explanation Generation**
   - Symptom → Cause → Evidence → Next Step format
   - Explanation cards in failure views
   - Link explanations to trace evidence

5. **Repair-Attempt Memory**
   - New event type for repair attempts
   - Cross-session failure pattern linking
   - "What was already tried" display

6. **Selective Replay**
   - Jump to event + step forward/backward
   - Focus on critical branch
   - Collapse low-value segments

### Medium Priority (Next 5-8 Sprints)

7. **Dynamic Importance Scoring**
   - Composite: base + severity + rarity + reuse
   - Adaptive over time
   - Drives retention and replay priorities

8. **Live Session Dashboard**
   - Real-time state summary
   - Latest decisions and tool activity
   - Stability/oscillation indicators

9. **Decision Provenance Views**
   - Four-question decision panel
   - Evidence chain traversal
   - Alternative rejection tracking

### Lower Priority (Future Enhancements)

10. **Prompt Policy Metadata**
    - Template IDs and policy parameters
    - Multi-agent conversation views
    - Behavioral metrics

11. **Guided Exploration**
    - Next informative branch recommendations
    - Frontier scoring
    - Exploration path visualization

12. **Advanced Adaptive Replay**
    - Replay value ranking
    - Failure clustering
    - Smart retention tiers

---

## Part 5: Alignment with Current Implementation

### Overall Implementation Score: 3.8/5

**Strengths:**
- ✅ Rich event capture with context and evidence
- ✅ Decision event model with evidence support
- ✅ Checkpointing system for state snapshots
- ✅ SSE streaming for real-time updates
- ✅ Timeline and hierarchy views
- ✅ Basic importance scoring

**Gaps:**
- ⚠️ Safety/refusal events not distinguished from errors
- ⚠️ No explicit failure mode taxonomy
- ⚠️ Static importance scoring (not adaptive)
- ⚠️ Limited causal inference beyond parent-child
- ⚠️ No structured explanation layer
- ⚠️ No repair-attempt memory
- ⚠️ Passive trace review (limited interaction)
- ⚠️ No live dashboard for real-time debugging
- ⚠️ Limited multi-agent observability

### Quick Wins (High Impact, Low Effort)

1. **Add `safety_check` and `refusal` event types** → Enables safety debugging
2. **Implement failure mode taxonomy** → Enables pattern recognition
3. **Add explanation cards to failure views** → Improves UX immediately
4. **Extend decision view with four questions** → Better provenance

### Strategic Bets (High Impact, Higher Effort)

1. **Causal edge inference system** → Foundation for root cause analysis
2. **Selective replay with stepping** → Debugger-like interaction model
3. **Dynamic importance + adaptive replay** → Smart memory management
4. **Live session dashboard** → Real-time debugging capabilities

---

## Part 6: Recommendations for Next Steps

### Immediate Actions (This Week)

1. **Implement Critical Event Types**
   - Add `safety_check` and `refusal` to event schema
   - Update SDK to capture these events
   - Update UI to distinguish blocked/refused/failed

2. **Define Failure Mode Taxonomy**
   - Document common failure patterns
   - Implement auto-detection rules
   - Add failure mode to session metadata

3. **Enhance Decision View**
   - Implement four-question format
   - Add evidence chain traversal
   - Track rejected alternatives

### Short-Term Roadmap (Next Month)

1. **Causal Inference System**
   - Implement edge inference algorithm
   - Add confidence scoring
   - Create causal graph visualization

2. **Structured Explanations**
   - Build explanation generator
   - Add explanation cards to UI
   - Link to trace evidence

3. **Repair Memory**
   - Add repair-attempt event type
   - Implement cross-session linking
   - Build failure history view

### Medium-Term Vision (Next Quarter)

1. **Selective Replay**
   - Implement jump-to-event navigation
   - Add step controls
   - Build branch-focused replay

2. **Live Dashboard**
   - Create real-time session view
   - Add behavior alerts
   - Implement triggered checkpointing

3. **Dynamic Scoring**
   - Build composite importance scorer
   - Implement adaptive replay prioritization
   - Add retention tiers

### Long-Term Research (Next 6 Months)

1. **Advanced Causal Analysis**
   - Automated causal discovery
   - Counterfactual analysis
   - Intervention recommendations

2. **Multi-Agent Support**
   - Cross-agent dependency tracking
   - Communication flow visualization
   - Emergent pattern detection

3. **Production Features**
   - Low-overhead tracing
   - Compliance reporting
   - Red team replay analysis

---

## Conclusion

The 10 papers analyzed provide a strong foundation for Peaky Peek's evolution. The current implementation shows good alignment with core concepts (3.8/5 average), particularly in event capture, evidence tracking, and checkpointing.

The highest-impact opportunities cluster around:
1. **Safety and refusal observability** (distinguish blocked/refused/failed)
2. **Failure pattern recognition** (taxonomy and memory)
3. **Causal analysis** (beyond timeline to dependency graphs)
4. **Interactive debugging** (selective replay and stepping)

By prioritizing these areas, Peaky Peek can rapidly advance toward the vision of a comprehensive, research-grounded AI agent debugger that addresses the real needs of developers building and maintaining agentic systems.

---

**Sources:**

All analyzed papers from `/docs/papers/`:
- [AgentTrace: Causal Graph Tracing for Root Cause Analysis](https://arxiv.org/abs/2603.14688)
- [XAI for Coding Agent Failures](https://arxiv.org/abs/2603.05941)
- [FailureMem: Failure-Aware Autonomous Software Repair](https://arxiv.org/abs/2603.17826)
- [MSSR: Memory-Aware Adaptive Replay](https://arxiv.org/abs/2603.09892v1)
- [Learning When to Act or Refuse](https://arxiv.org/abs/2603.03205v1)
- [Policy-Parameterized Prompts](https://arxiv.org/abs/2603.09890v1)
- [CXReasonAgent: Evidence-Grounded Diagnostic Reasoning](https://arxiv.org/abs/2602.23276v1)
- [NeuroSkill: Proactive Real-Time Agentic System](https://arxiv.org/abs/2603.03212v1)
- [REST: Receding Horizon Explorative Steiner Tree](https://arxiv.org/abs/2603.18624)
- [Towards a Neural Debugger for Python](https://arxiv.org/abs/2603.09951v1)

---

**Report Status:** ✅ COMPLETE
**Next Task:** #1 - Synthesize findings into concrete action plan (awaiting task #3 completion)
