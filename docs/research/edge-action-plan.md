# Edge Action Plan: Peaky Peek Research-Backed Roadmap

**Prepared by:** worker-planner (research-edge-plan team)
**Date:** 2026-03-31
**Based on:** Research papers deep-dive (worker-scientist) + Code audit (worker-architect)

---

## Executive Summary

This action plan synthesizes findings from 10 research papers and a comprehensive codebase audit. The key finding: **Peaky Peek already implements core concepts from 9/11 papers** with strong coverage (70-100%) in most areas.

**Strategic Insight:** The product is closer to research-edge than initially apparent. The highest-value work is **completing partial implementations** rather than building from scratch.

**Overall Implementation Score:** 3.8/5

The plan prioritizes:
1. **Completing 5 high-impact partial implementations** (quick wins)
2. **Adding 3 differentiating features** for competitive positioning
3. **Monitoring 6 emerging research areas** for future inspiration

---

## 1. VISION STATEMENT

**Peaky Peek should become the definitive research-grounded debugger for AI agents.**

Based on the research landscape, this means:

- **From traces to explanations:** Transform raw execution traces into structured, human-interpretable failure narratives
- **From errors to distinctions:** Explicitly distinguish between failed, blocked, and refused actions
- **From static to adaptive:** Importance scoring that evolves based on failure patterns and replay value
- **From passive to interactive:** Debugger-like controls (breakpoints, stepping, selective replay)
- **From single-session to cross-session learning:** Failure memory that surfaces prior repair attempts

**Why this matters:** The research shows that effective agent debugging requires (1) causal understanding, not just chronological views; (2) safety-aware observability; (3) evidence-grounded decisions; and (4) adaptive memory management. Peaky Peek is positioned to deliver all four.

---

## Execution Model

This roadmap should be executed as four parallel workstreams, not as a flat feature queue.

### Workstream A: Event Model And Persistence
- Scope: SDK events, schema serialization, storage, migrations, API contracts
- Typical features: repair attempts, replay value persistence, feedback-loop memory artifacts
- Done means: event survives capture, persistence, query, and seeded-session replay

### Workstream B: Intelligence And Query Layer
- Scope: causal analysis, clustering, drift detection, ranking, health computation
- Typical features: causal overlays, guided exploration, health score, failure-informed retrieval
- Done means: scoring logic is benchmarked against seeded traces and exposed through stable APIs

### Workstream C: Frontend Debugger Workflows
- Scope: decision tree, event detail, replay, live monitoring, analytics panels
- Typical features: provenance workflows, breakpoint UX, blocked-action distinction, multi-agent views
- Done means: the feature is discoverable in the main debugger flow and not hidden behind manual inspection

### Workstream D: Evaluation, Fixtures, And Demo Proof
- Scope: seeded sessions, regression tests, screenshots, GIFs, competitive demos
- Typical features: failure chains, repair sequences, drift incidents, multi-agent scenarios
- Done means: every roadmap item has one fixture, one regression assertion, and one demoable path

### Release Rules
1. No feature counts as shipped until SDK, API, persistence, UI, tests, and docs all cover it.
2. Every feature needs one seeded session that demonstrates the intended debugging workflow.
3. High-risk intelligence features ship in observe-only or explain-only mode before any automated action.
4. Local-first remains the default. Cloud, export, and production integrations are additive, not required.

---

## 2. QUICK WINS (1-2 weeks each)

These complete partial implementations with high research backing and low implementation cost.

### Quick Win #1: Visual Causal Edges in Decision Tree
**Paper:** AgentTrace (arXiv:2603.14688)
**Current Status:** 95% - Backend causal analysis exists, visualization missing
**Implementation:** Annotate DecisionTree links with causal relation types

**What to change:**
- In `frontend/src/components/DecisionTree.tsx`, add visual distinction between:
  - Parent-child links (solid lines)
  - Evidence links (dotted blue lines)
  - Inferred causal edges (dotted orange lines)
- Add legend explaining edge types
- Show confidence scores on inferred edges

**Expected impact:** Users can immediately see causal dependencies without manual trace reconstruction. Reduces debugging time for complex failures.

**Files:** `frontend/src/components/DecisionTree.tsx` (lines 1-344)

---

### Quick Win #2: Repair Attempt Event Type
**Paper:** FailureMem (arXiv:2603.17826)
**Current Status:** 85% - `RepairAttemptEvent` exists in the SDK, but the end-to-end product flow is incomplete
**Implementation:** Finish repair-attempt tracking from event capture through failure analysis and UI surfacing

**What to change:**
- Ensure repair-attempt fields survive persistence and API query paths
- Group attempts by `repair_sequence_id` and show prior failed fixes before a new repair
- Surface "Previously Tried Repairs" in the failure explanation flow and similar-failure workflows
- Add one seeded session that demonstrates failed -> failed -> success repair progression

**Expected impact:** Users see what was already tried before attempting new repairs. Prevents repeated failed strategies.

**Files:**
- `agent_debugger_sdk/core/events/repair.py`
- `api/schemas.py`
- `frontend/src/components/WhyButton.tsx`
- `frontend/src/components/SimilarFailuresPanel.tsx`

---

### Quick Win #3: Decision Provenance Panel
**Paper:** CXReasonAgent (arXiv:2602.23276v1)
**Current Status:** 85% - panel exists, but it still behaves like a structured field dump rather than a first-class investigation workflow
**Implementation:** Upgrade the existing provenance panel into a source-linked debugger surface

**What to change:**
- Replace raw JSON evidence blocks with typed evidence cards and weak-evidence markers
- Rank supporting and contradictory upstream events instead of listing IDs only
- Keep the four debugger questions, but make each answer navigable from the panel
- Normalize alternatives and evidence metadata in API payloads so the panel stays stable across frameworks

**Expected impact:** Users can trace decision reasoning backward to source evidence. Improves trust in agent decisions.

**Files:**
- `frontend/src/components/DecisionProvenancePanel.tsx`
- `frontend/src/components/EventDetail.tsx`
- `api/schemas.py`

---

### Quick Win #4: "Show Blocked Actions" Toggle
**Paper:** Learning When to Act or Refuse (arXiv:2603.03205v1)
**Current Status:** 90% - blocked-action filtering exists in the timeline, but it is not yet a coherent cross-view workflow
**Implementation:** Make blocked, refused, and failed states consistent across timeline, replay, and detail views

**What to change:**
- Share blocked-action filter state between timeline, replay, and stored session preferences
- Mirror blocked-action markers inside replay, not only the trace timeline
- Keep blocked action context visible in event detail and session summaries
- Add one regression fixture that contains both refused and failed actions in the same run

**Expected impact:** Users can distinguish "failed" from "refused on purpose." Critical for safety debugging.

**Files:**
- `frontend/src/components/TraceTimeline.tsx`
- `frontend/src/components/SessionReplay.tsx`
- `frontend/src/stores/sessionStore.ts`
- `frontend/src/components/EventDetail.tsx`

---

### Quick Win #5: Breakpoint UI Controls
**Paper:** Towards a Neural Debugger for Python (arXiv:2603.09951v1)
**Current Status:** 85% - event-level breakpoints exist in replay, but they are still local and not fully aligned with server-side replay controls
**Implementation:** Productize breakpoints with saved presets and API-backed replay stop behavior

**What to change:**
- Persist breakpoint presets in store/localStorage
- Align UI selections with replay route query params and server-side stopping behavior
- Add quick presets for error, low-confidence, safety, and tool breakpoints
- Surface "stopped at breakpoint" state in replay UI using server response fields

**Expected impact:** Users can halt replay at specific event types. Enables iterative debugging.

**Files:**
- `frontend/src/components/SessionReplay.tsx`
- `frontend/src/stores/sessionStore.ts`
- `frontend/src/api/client.ts`
- `api/replay_routes.py`

---

## 3. MEDIUM-TERM (1-2 months)

These features would differentiate Peaky Peek from competitors like LangSmith and OpenTelemetry.

### Medium-Term #1: Adaptive Replay with Time-Decay
**Paper:** MSSR (arXiv:2603.09892v1)
**Current Status:** 65% - importance and replay value exist, but recency and retention behavior are still mostly static
**Implementation:** Dynamic importance scoring with time-decay

**What to change:**
- Modify `collector/intelligence/compute.py` to add:
  - Time decay factor: increase replay_value for recent failures
  - Recency boost: sessions with activity in last 7 days get +0.2
  - Stale penalty: sessions inactive for 30 days get -0.3
- Thread replay value into session summaries and retention decisions
- Add "Replay Value" sort option to the session rail and analytics views

**Expected impact:** Smart memory management. High-value failure patterns preserved, low-value routine traces downsampled.

**Competitive advantage:** LangSmith has flat retention; Peaky Peek adapts based on actual debugging value.

**Files:**
- `collector/intelligence/compute.py`
- `collector/replay.py`
- `frontend/src/components/SessionRail.tsx`
- `frontend/src/utils/healthScore.ts`

**Effort estimate:** 2-3 weeks

---

### Medium-Term #2: Multi-Agent Conversation View
**Paper:** Policy-Parameterized Prompts (arXiv:2603.09890v1)
**Current Status:** 75% - conversation and coordination panels exist, but the workflow is still split and not yet a unified multi-agent debugger surface
**Implementation:** Consolidate existing conversation and coordination views into one first-class multi-agent workflow

**What to change:**
- Unify `ConversationPanel` and `MultiAgentCoordinationPanel` around one event model
- Show speaker turns with active policy template badges and turn-level goals
- Keep cross-agent influence markers visible and clickable
- Support compare-by-speaker and compare-by-policy workflows

**Expected impact:** Debug multi-agent systems by understanding dialogue flow and policy shifts.

**Competitive advantage:** LangSmith treats multi-agent as multiple sessions; Peaky Peek shows conversation context.

**Files:**
- `frontend/src/components/ConversationPanel.tsx`
- `frontend/src/components/MultiAgentCoordinationPanel.tsx`
- `frontend/src/hooks/useConversationFilters.ts`
- `api/schemas.py`

**Effort estimate:** 3-4 weeks

---

### Medium-Term #3: Guided Exploration with Frontier Scoring
**Paper:** REST (arXiv:2603.18624)
**Current Status:** 30% - Decision tree exists, no guidance
**Implementation:** Rank and recommend "next most informative branch"

**What to change:**
- Add frontier scoring to `DecisionTree.tsx`:
  - Failure proximity: closer to error = higher priority
  - Novelty: branches not yet inspected
  - Evidence weakness: decisions with missing/weak evidence
- Highlight top-ranked branch with "Recommended Next" badge
- Add "Explore Most Informative" button to jump directly
- Track exploration progress per branch

**Expected impact:** Users spend less time searching for relevant branches. System guides them to high-value investigation points.

**Competitive advantage:** No competitor offers exploration guidance for large trace spaces.

**Files:**
- `frontend/src/components/DecisionTree.tsx` (lines 1-344)
- `collector/intelligence/compute.py` (add frontier scoring)

**Effort estimate:** 2-3 weeks

---

### Medium-Term #4: Live Session Dashboard with Alerts
**Paper:** NeuroSkill (arXiv:2603.03212v1)
**Current Status:** 85% - live dashboard shell exists, but the operational loop around alerts, checkpoints, and degradation is not finished
**Implementation:** Graduate the dashboard from a readout panel into an operator workflow

**What to change:**
- Persist alert context so live issues remain inspectable after disconnect or session end
- Add alert acknowledgement, jump-to-event, and replay-from-alert shortcuts
- Implement event-triggered checkpoint recommendations and, later, automatic checkpointing
- Feed alert history into the later health-score and production-tracing tracks

**Expected impact:** Debug long-running sessions in real-time. Catch issues before session completes.

**Competitive advantage:** LangSmith is post-hoc only; Peaky Peek supports live debugging.

**Files:**
- `frontend/src/components/LiveDashboard.tsx`
- `api/services.py`
- `collector/live_monitor.py`
- `collector/patterns/health_report.py`

**Effort estimate:** 3-4 weeks

---

## 4. LONG-TERM / CUTTING EDGE (3-6 months)

Ambitious features based on newest research and emerging trends.

### Long-Term #1: Counterfactual Analysis
**Paper:** AgentTrace + Causal Discovery research
**Basis:** Extension of causal graph tracing
**Why it matters:** Answer "what if" questions about agent decisions

**Implementation approach:**
- Extend causal analyzer to identify intervention points
- Add "What if this decision were different?" analysis
- Simulate alternative downstream outcomes
- Present counterfactual scenarios with confidence intervals

**Dependencies:** Causal edge inference (Quick Win #1), Decision provenance (Quick Win #3)

**Effort estimate:** 2-3 months

---

### Long-Term #2: Cross-Agent Dependency Tracking
**Paper:** Multi-Agent Coordination Analysis (emerging research)
**Basis:** Extension of multi-agent conversation view
**Why it matters:** Debug emergent behaviors in agent swarms

**Implementation approach:**
- Track cross-agent references and dependencies
- Visualize communication flow between agents
- Detect emergent patterns (e.g., leader-follower, consensus formation)
- Alert on circular dependencies or deadlocks

**Dependencies:** Multi-agent conversation view (Medium-Term #2)

**Effort estimate:** 3-4 months

---

### Long-Term #3: Low-Overhead Production Tracing
**Paper:** Real-Time Monitoring and Observability (emerging research)
**Basis:** Extension of SSE streaming
**Why it matters:** Debug agents in production without performance impact

**Implementation approach:**
- Implement sampling-based tracing for production
- Add configurable observability levels (minimal, standard, verbose)
- Create production-specific dashboards with alerting
- Support export to external monitoring systems (Prometheus, Grafana)

**Dependencies:** Live dashboard (Medium-Term #4)

**Effort estimate:** 3-4 months

---

### Long-Term #4: Mechanistic Interpretability Integration
**Paper:** Mechanistic Interpretability for LLM Agents (emerging)
**Basis:** Internal state visualization for LLM calls
**Why it matters:** Understand why LLM made specific decisions

**Implementation approach:**
- Capture activation patterns from LLM calls (where available)
- Visualize attention heads relevant to decisions
- Identify intervention points for steering agent behavior
- Integrate with Anthropic's mechanistic interpretability tools

**Dependencies:** Decision provenance (Quick Win #3)

**Effort estimate:** 4-6 months (highly experimental)

---

### Long-Term #5: Failure-Informed Feedback Loop
**Paper:** FailureMem + Continual Learning for Debugging Systems (emerging)
**Basis:** Extension of failure memory, explanation layers, and prompt-policy metadata
**Why it matters:** Turn debugging data into agent improvement without requiring model retraining

**Implementation approach:**
- Persist compact failure lessons: attempted strategy, failure mechanism, evidence, and fix outcome
- Retrieve similar prior failures before or during a new run and surface context like: "last time approach X failed because Y"
- Support developer-controlled injection modes: observe-only, suggest-to-human, or auto-attach as agent context
- Track whether the injected lesson improved outcomes, then down-rank stale or misleading memories

**Dependencies:** Failure memory, root-cause explanations, prompt-policy metadata, repair-attempt tracking

**Effort estimate:** 3-4 months

---

### Long-Term #6: Unified Agent Health Score
**Paper:** Behavioral Drift + Real-Time Monitoring + Failure Clustering (combined research direction)
**Basis:** Extension of `collector/patterns/health_report.py`, drift alerts, and frontend health scoring
**Why it matters:** Create one operator-friendly signal for regression detection and position Peaky Peek as "Datadog for AI agents"

**Implementation approach:**
- Combine drift detection, failure-cluster recurrence, confidence trends, tool instability, and loop alerts into one composite score
- Expose health at multiple levels: session, agent, environment, and release
- Show score contributors so users can see whether the regression came from drift, repeated failures, or declining confidence
- Alert on sudden health drops after prompt, model, tool, or policy changes and validate the score against real incidents

**Dependencies:** Behavior alerts, cross-session clustering, health report generation, analytics history

**Effort estimate:** 2-3 months

---

## 5. PAPERS TO WATCH

Monitor these research areas for future inspiration. Check arXiv and Google Scholar quarterly.

### High Priority (Next 3 months)
1. **Mechanistic Interpretability for Tool-Using Agents**
   - Anthropic's circuit analysis research
   - Activation steering for agentic systems
   - Why: Internal state visualization is the next frontier

2. **Multi-Agent Reinforcement Learning Debugging**
   - Emergent behavior detection
   - Coordination failure analysis
   - Why: Multi-agent systems are growing rapidly

3. **Causal Discovery Algorithms for Execution Traces**
   - Automated causal edge discovery
   - Intervention-based debugging
   - Why: Extends AgentTrace concepts

### Medium Priority (Next 6 months)
4. **Real-Time Anomaly Detection in Agent Behavior**
   - Streaming observability patterns
   - Low-overhead production tracing
   - Why: Production debugging is a gap

5. **Continual Learning for Debugging Systems**
   - Experience replay optimization
   - Dynamic memory management
   - Why: Extends MSSR and FailureMem

6. **Formal Verification for Agent Guardrails**
   - Safety constraint proving
   - Red teaming methodology
   - Why: Compliance and safety markets

### Search Queries for Updates
```
"causal discovery" AND "agent" AND 2024
"multi-agent" AND "debugging" AND 2024
"mechanistic interpretability" AND "agent" AND 2024
"agent safety" AND "guardrails" AND 2024
"LLM" AND "observability" AND "production" AND 2024
```

---

## 6. COMPETITIVE POSITIONING

Based on research-backed features, here's how Peaky Peek positions against competitors:

### vs LangSmith
| Feature | Peaky Peek | LangSmith | Research Basis |
|---------|-----------|-----------|----------------|
| Causal root-cause analysis | ✅ Yes (AgentTrace) | ❌ No | Differentiating |
| Safety/refusal distinction | ✅ Yes (Act or Refuse) | ❌ No | Differentiating |
| Failure memory across sessions | ✅ Yes (FailureMem) | ❌ No | Differentiating |
| Adaptive replay prioritization | ✅ Yes (MSSR) | ❌ No | Differentiating |
| Evidence-grounded decisions | ✅ Yes (CXReasonAgent) | ⚠️ Partial | Parity+ |
| Multi-agent conversation view | 🔄 Planned | ⚠️ Partial | Planned |
| Live debugging | 🔄 Planned | ❌ No | Differentiating |

**Competitive moat:** 5 research-backed features that LangSmith lacks.

### vs OpenTelemetry
| Feature | Peaky Peek | OpenTelemetry | Research Basis |
|---------|-----------|---------------|----------------|
| Agent-specific events | ✅ Yes | ⚠️ Generic | Domain-specific |
| Causal inference | ✅ Yes | ❌ No | Differentiating |
| Failure explanation layer | ✅ Yes | ❌ No | Differentiating |
| Agent-specific | ✅ Yes | ⚠️ Manual | Parity |
| Low-overhead production | 🔄 Planned | ✅ Yes | Gap |

**Competitive moat:** Agent-first design vs generic observability.

### vs Arize Phoenix
| Feature | Peaky Peek | Arize Phoenix | Research Basis |
|---------|-----------|---------------|----------------|
| Local-first | ✅ Yes | ❌ No (SaaS) | Differentiating |
| Repair attempt tracking | ✅ Yes | ❌ No | Differentiating |
| Selective replay | ✅ Yes | ⚠️ Partial | Parity+ |
| LLM-specific tracing | ⚠️ Partial | ✅ Yes | Gap |

**Competitive moat:** Local-first + repair memory.

### Positioning Statement
**"Peaky Peek: The research-grounded local debugger for AI agents."**

Key differentiators:
1. **Causal understanding** beyond timelines (AgentTrace)
2. **Safety-aware observability** distinguishing blocked/refused/failed (Act or Refuse)
3. **Cross-session failure learning** (FailureMem, MSSR)
4. **Evidence-grounded decisions** with provenance tracking (CXReasonAgent)
5. **Local-first architecture** for data-sensitive applications

---

## 7. RISK ASSESSMENT

Which research-backed features might be premature or over-engineered?

### High Risk (Do Not Implement Yet)
1. **Counterfactual Analysis (Long-Term #1)**
   - Risk: May produce misleading "what if" scenarios
   - When to reconsider: After causal inference validates against real failures

2. **Mechanistic Interpretability (Long-Term #4)**
   - Risk: Highly experimental, may not generalize across LLMs
   - When to reconsider: When standardized APIs for activation access emerge

### Medium Risk (Implement with Care)
3. **Adaptive Replay Scoring (Medium-Term #1)**
   - Risk: Time-decay may hide old-but-valuable failures
   - Mitigation: Always allow manual override of retention decisions

4. **Cross-Agent Dependency Tracking (Long-Term #2)**
   - Risk: May become complex visualization noise
   - Mitigation: Start with simple dependency graphs, add complexity based on user feedback

5. **Failure-Informed Feedback Loop (Long-Term #5)**
   - Risk: Stale or incorrect memories can bias future runs in the wrong direction
   - Mitigation: Default to observe-only retrieval, show provenance for every injected lesson, require opt-in for auto-attach

6. **Unified Agent Health Score (Long-Term #6)**
   - Risk: A single number can hide important failure modes or create false confidence
   - Mitigation: Always show component signals beside the composite score and validate against real incident history

### Low Risk (Safe to Implement)
All Quick Wins (#1-5) are low-risk:
- Complete existing partial implementations
- Clear user value
- Minimal architectural changes

---

## 8. IMPLEMENTATION PRIORITY MATRIX

### Phase 1: Foundation (Next 6 weeks)
| Feature | Paper | Effort | Impact | Priority |
|---------|-------|--------|--------|----------|
| Visual causal edges | AgentTrace | 1 week | High | 1 |
| Repair attempt events | FailureMem | 1 week | High | 2 |
| Decision provenance | CXReasonAgent | 1 week | High | 3 |
| Show blocked actions | Act or Refuse | 3 days | Medium | 4 |
| Breakpoint UI | Neural Debugger | 1 week | Medium | 5 |

### Phase 2: Differentiation (Months 2-3)
| Feature | Paper | Effort | Impact | Priority |
|---------|-------|--------|--------|----------|
| Adaptive replay | MSSR | 2-3 weeks | High | 6 |
| Live dashboard | NeuroSkill | 3-4 weeks | High | 7 |
| Guided exploration | REST | 2-3 weeks | Medium | 8 |
| Multi-agent view | Policy-Param | 3-4 weeks | Medium | 9 |

### Phase 3: Innovation (Months 4-6)
| Feature | Paper | Effort | Impact | Priority | Risk |
|---------|-------|--------|--------|----------|------|
| Unified health score | Combined | 2-3 months | High | 10 | Medium |
| Failure-informed feedback loop | FailureMem+ | 3-4 months | High | 11 | Medium |
| Counterfactual analysis | AgentTrace+ | 2-3 months | High | 12 | High |
| Cross-agent tracking | Emerging | 3-4 months | Medium | 13 | Medium |
| Production tracing | Emerging | 3-4 months | High | 14 | Low |
| Mechanistic int. | Emerging | 4-6 months | Unknown | 15 | High |

---

## Delivery Cadence

### Sprint 1 (Weeks 1-2): Causal Clarity
- Finish visual causal edges and provenance-panel hardening
- Normalize evidence and alternative fields in API payloads
- Lock one seeded failure session for causal-debugging demos

### Sprint 2 (Weeks 3-4): Repair Memory And Breakpoints
- Finish repair-attempt persistence and surface prior repairs in the failure workflow
- Persist breakpoint presets and align replay UI with server stop behavior
- Add one replay fixture with low-confidence and safety breakpoints

### Sprint 3 (Weeks 5-6): Adaptive Replay Foundation
- Add recency-aware replay value scoring
- Surface replay value in session rail sorting and analytics
- Validate retention behavior against seeded recent vs stale failures

### Sprint 4 (Weeks 7-8): Live Monitoring Operations
- Promote live dashboard alerts into durable investigation entrypoints
- Add replay-from-alert and checkpoint recommendation flows
- Capture baseline metrics for future health scoring

### Sprint 5 (Weeks 9-10): Multi-Agent And Guided Exploration
- Consolidate conversation and coordination into one multi-agent workflow
- Add branch frontier scoring and recommended-next investigation flows
- Demo one multi-agent failure with policy shift and cross-agent influence

### Sprint 6 (Weeks 11-12): Pick The First Strategic Bet
- Choose between `Unified Agent Health Score` and `Failure-Informed Feedback Loop`
- Decision rule: pick the one with clearer operator value based on real debugger usage and seeded benchmarks
- Keep the other as the next-quarter lead item, not a parallel distraction

### Phase Gate For Long-Term Work
Do not start counterfactual analysis or mechanistic interpretability until:
- quick wins are fully shipped end to end
- adaptive replay and live monitoring are both stable
- at least one composite metric or memory feedback loop has real usage proof

---

## 9. SUMMARY AND NEXT STEPS

### Key Findings
1. **Peaky Peek is closer to research-edge than apparent** - 5 papers have 95-100% implementation
2. **5 high-impact quick wins available** - complete partial implementations in 1-2 weeks each
3. **Competitive differentiation opportunity** - 5 features not available in LangSmith or OpenTelemetry
4. **Emerging research areas to monitor** - mechanistic interpretability, multi-agent RL debugging

### Recommended Immediate Actions
1. **Week 1-2:** Finish the causal-debugging path already present in the repo: causal edges, stronger provenance, and one seeded session
2. **Week 3-4:** Close the repair-memory and breakpoint product gaps instead of rebuilding those features from scratch
3. **Week 5-8:** Push adaptive replay and live monitoring into stable operator workflows
4. **End of Month 3:** Choose one strategic lead bet: `Unified Agent Health Score` or `Failure-Informed Feedback Loop`

### Success Metrics
- **Short-term (6 weeks):** Quick wins are shipped end to end, not just visible in UI. Seeded sessions cover causal explanation, blocked actions, repair history, and breakpoints.
- **Medium-term (3 months):** Adaptive replay and live monitoring are both used in debugger workflows. At least one multi-agent or guided-exploration scenario is demo-ready.
- **Long-term (6 months):** One strategic bet is operational with usage proof, and one higher-risk experimental track remains in spike mode only.

### Research Monitoring
Assign quarterly "research scan" to check:
- arXiv for new agent debugging papers
- Anthropic/OpenAI research blogs for mechanistic interpretability
- Multi-agent systems conferences for coordination debugging

---

**Plan Status:** ✅ COMPLETE
**Next Task:** Report completion to team-lead
