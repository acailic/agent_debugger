# Intelligence-First Competitive Strategy

**Date:** 2026-03-26
**Status:** Approved
**Supporting research:** `docs/competitive-strategy-research.md`, `docs/competitive-analysis.md`

---

## The Bet

Peaky Peek wins by being the only AI agent debugger that explains WHY agents fail — in 30 seconds. Not another observability platform, but the debugger developers reach for when tracing is not enough.

The entire LLM observability market (Phoenix, Langfuse, LangSmith, AgentOps, LiteLLM) competes on feature breadth (tracing + evaluation + prompts + datasets). Nobody competes on debugging depth. The moat is in capabilities zero competitors have: decision provenance, causal explanation, AI-curated replay, semantic failure memory, and behavioral drift detection.

## Hero Features

1. **"See WHY your agent did that"** — one-click root cause explanation with confidence scores
2. **"Replay from any checkpoint"** — AI-curated replay that shows only the important parts

## Supporting Features

3. Failure Memory — semantic search across past sessions
4. Cost Dashboard — make existing pricing.py visible in UI
5. Behavior Alerts — detect drift between sessions

## Deliberately Not Building (This Cycle)

| Deferred | Why | Revisit When |
|----------|-----|-------------|
| Natural language debugging | Uncertain UX — wait for user feedback on structured explanations | After Phase 3 launch |
| Counterfactual analysis | Very high complexity (6-12mo R&D) | After Phase 4 |
| Evaluation (LLM-as-judge) | Phoenix does this well — emit OTel spans instead | If users explicitly ask |
| Prompt management | Not a debugger concern — Langfuse owns this | Never |
| Clerk auth + Stripe billing | Premature before proving product value | After 50+ active users |
| Multi-agent visualization | Niche — CrewAI/AutoGen are secondary frameworks | After PydanticAI beachhead succeeds |
| Dataset/experiments | Not core to debugging | Never |

---

## Phase 1: "Why Did It Fail?" + Smart Replay (4 weeks)

**Goal:** Build the 30-second demo. A developer runs their PydanticAI agent, and when it fails, clicks one button to see a plain-English explanation.

### "Why Did It Fail?" button

- **Backend:** Causal chain analysis service — walks the event timeline backward from the failure event, scores each decision's contribution to the failure. Based on AgentTrace paper (arXiv:2603.14688) causal graph reconstruction.
- **Confidence scoring:** Per-decision confidence (e.g., "Decision #34 used stale credentials — 87% confidence this caused the failure").
- **Output:** Plain-English explanation with linked evidence (event IDs, timestamps).
- **API:** `POST /api/sessions/{id}/explain` returns structured explanation + confidence scores.
- **Error pattern heuristics:** Framework-specific failure patterns (PydanticAI's three retry layers, LangChain's OutputParserException, etc.).

### Smart Replay Highlights

- **Backend:** Event importance scoring — rank events by failure contribution, retry churn, latency spikes, decision reversals. Based on MSSR paper (arXiv:2603.09892v1) importance scoring.
- **Output:** Top 10-15% of events as the "highlight reel" — remaining events collapsed as context summaries.
- **API:** `GET /api/sessions/{id}/highlights` returns ordered list of key events with explanations.

### Frontend

- "Explain This Session" button on failed sessions — prominent, top-level CTA.
- Highlight panel alongside the timeline — collapsed events shown as summary ("45 similar decisions").
- Explanation card with confidence scores and linked evidence.

### Validation

The 30-second demo works end-to-end with a real PydanticAI agent.

---

## Phase 2: Failure Memory + Cost Dashboard (4 weeks)

**Goal:** Developers never debug the same failure twice. Cost visibility without leaving the debugger.

### Failure Memory Search

- **Backend:** Embed event sequences as vectors (decision type + tool name + error type + context). Store in local SQLite with vector extension or simple cosine similarity.
- **Search API:** `GET /api/search?q=...` — natural language query over past sessions. Returns similar sessions ranked by similarity, with fix descriptions if available.
- **Similar sessions API:** `POST /api/sessions/{id}/similar` — find semantically similar past sessions.
- **Fix notes:** Optional manual annotation ("Fixed by adding retry timeout") — stored and surfaced in future searches. Based on FailureMem paper (arXiv:2603.17826) repair memory.

### Cost Dashboard

- **Frontend:** Cost panel in session detail view — per-event cost breakdown using existing `pricing.py`.
- **Aggregate cost view:** "This week: $12.40 across 847 traces" with cost by model/provider breakdown.
- **API:** `GET /api/sessions/{id}/cost`, `GET /api/cost/summary`.

### Frontend

- Search bar in the UI — "Search past failures..."
- Cost summary widget on dashboard.
- Fix annotation UI — "How did you fix this?" on any session.

### Validation

A developer can search for a failure they debugged last week and see the fix notes.

---

## Phase 3: PydanticAI Beachhead Launch (4 weeks)

**Goal:** 50 PydanticAI developers using Peaky Peek within 30 days of launch. Minimal auth, maximum simplicity.

### Launch Infrastructure

- **Minimal auth:** API key generation + verification only (no Clerk, no OAuth). `pip install && peaky-peek login`.
- **Landing page:** Single page — hero = 30-second demo GIF, sub-hero = "pip install peaky-peek" quickstart, comparison vs Phoenix/Langfuse.
- **Docs site:** Quickstart (PydanticAI first, LangChain second), adapter reference, API reference.
- **OpenInference OTel export:** `pip install peaky-peek[phoenix]` — emit compatible spans so users can send sessions to Phoenix for evaluation.

### Go-to-Market

- PydanticAI community first: GitHub Discussions, Pydantic Discord, issue #2472 responders.
- Blog post: "Why your PydanticAI agent debugger should explain WHY, not just WHAT."
- "Peaky Peek vs Langfuse vs Phoenix for PydanticAI" comparison page.
- Demo video: the 30-second flow, screen-recorded.

### Framework Polish

- Harden PydanticAI adapter (elevate from ADR-004 rank #4 to #1).
- Promote existing auto-patch adapters more visibly.
- PydanticAI-specific error pattern detection (three retry layers, structured output validation failures).

### Validation

50 active users, 10+ sessions/week from external users, 5+ community mentions.

---

## Phase 4: Behavior Alerts + Intelligence Polish (4-6 weeks)

**Goal:** Developers catch issues before they break production.

### Behavior Alerts

- **Backend:** Compare new sessions against recent history — detect parameter drift (temperature changed), latency changes, error rate shifts, decision pattern changes. Based on XAI paper (arXiv:2603.05941) behavioral drift and NeuroSkill (arXiv:2603.03212v1) real-time monitoring.
- **Alert surface:** In-UI notifications on session load ("This session's behavior diverges from the last 5 runs").
- **API:** `GET /api/sessions/{id}/anomalies` returns detected drift points.

### Intelligence Polish

- Improve explanation quality based on real user sessions.
- Add framework-specific heuristics (LangChain retry patterns, PydanticAI validation failures).
- Performance: Why button + Smart Replay complete in <5 seconds for sessions up to 10K events.

### Validation

Anomaly detection catches a real behavior change that the developer did not notice.

---

## Success Metrics

| Metric | Current | Phase 1 Target | Phase 3 Target |
|--------|---------|---------------|---------------|
| 30-second demo works | No | Yes (PydanticAI) | Yes (PydanticAI + LangChain) |
| Time to root cause | Unknown | < 30 seconds | < 30 seconds |
| Active users | 0 | Internal testing | 50+ |
| GitHub stars | ~50 | — | 500+ |
| PydanticAI adapter depth | Basic | Improved | Best-in-class |
| Cost dashboard | pricing.py exists | — | Visible in UI |
| Failure memory | None | — | Semantic search works |
| Anomaly detection | Basic (loop alerts) | — | Behavior drift detection |

---

## Research Foundation

All intelligence features are grounded in published research:

| Feature | Paper | Key Concept |
|---------|-------|-------------|
| Why button | AgentTrace (arXiv:2603.14688) | Causal graph reconstruction, backward tracing from failures |
| Smart replay | MSSR (arXiv:2603.09892v1) | Retention-aware sampling, trace prioritization |
| Failure memory | FailureMem (arXiv:2603.17826) | Repair memory, learning from failed attempts |
| Behavior alerts | XAI (arXiv:2603.05941) + NeuroSkill (arXiv:2603.03212v1) | Behavioral drift detection, real-time monitoring |

Full paper references in `docs/research-inspiration.md`.

---

## Competitive Positioning

### Where we play

- **Local-first debugging** — `pip install` and go, no Docker, no cloud dependency
- **PydanticAI beachhead** — 28.7M monthly downloads, no strong debugger exists
- **Causal explanation** — the only tool that explains WHY, not just WHAT
- **Complementary to observability** — emit OTel spans to Phoenix/Langfuse for evaluation

### Where we don't play

- Prompt management (Langfuse owns this)
- LLM-as-judge evaluation (Phoenix owns this)
- Gateway/routing (LiteLLM owns this)
- Full platform/auth/billing (premature)
- LangChain-first (Phoenix/Langfuse/LangSmith are stronger here — we lead with PydanticAI)

### The 30-Second Demo

1. "Agent failed, 500 events" (2s)
2. Click "Why Did It Fail?" (1s)
3. "Decision #34 used stale credentials (87% confidence)" (5s)
4. Click "See Similar Failures" (2s)
5. "This failed 3 times before. Fixes here." (5s)
6. "Done. 15 seconds total." (2s)
