# Competitive Roadmap: Peaky Peek vs Hindsight & Market

> Research conducted 2026-04-03. Based on analysis of [Hindsight](https://github.com/vectorize-io/hindsight), Peaky Peek capabilities, and the competitive landscape.

## Strategic Positioning

**Peaky Peek and Hindsight are complementary, not competing.**

| Dimension | Peaky Peek | Hindsight |
|-----------|------------|-----------|
| Core function | Agent decision archaeology | Agent memory/learning |
| Data model | Event tree (decisions, traces, checkpoints) | Memory units (facts, entities, mental models) |
| Retrieval | Semantic search, failure clustering | TEMPR (4-strategy parallel) |
| Replay | Time-travel via checkpoints | No session replay |
| Deployment | Local-first, SQLite | Docker, K8s, cloud |
| Analysis | Causal failure analysis, drift detection | Disposition-aware reasoning, consolidation |

**Hindsight is forward-looking** (improve future behavior through memory).
**Peaky Peek is backward-looking** (understand past behavior through traces).

---

## Quick Wins (Completed)

### 1. Entity Extraction from Traces

Extract entities (tool names, error types, API endpoints, agent names) from trace events. Build an entity index and query API.

**Deliverables:**
- `storage/entities.py` — Entity extraction module
- `storage/repositories/entity_repo.py` — Entity repository
- `api/entity_routes.py` — API endpoints for entity queries
- `tests/test_entity_extraction.py` — Unit tests
- `tests/test_entity_repo.py` — Repository tests

**Value:** Turns raw traces into an agent knowledge graph. Enables "Top 10 failure-prone tools" dashboards.

### 2. Cross-Session Natural Language Search

Extend `storage/search.py` with natural language query support across sessions.

**Deliverables:**
- Enhanced `storage/search.py` — NL query support with filtering
- `api/search_routes.py` — Search API endpoint
- `tests/storage/test_nl_search.py` — Search tests
- `tests/test_nl_search_api.py` — API tests

**Value:** "Find sessions where the agent got stuck in a loop" — semantic search over all past debugging sessions.

### 3. Similar Failures UI Panel

When viewing a failure, show 3-5 historically similar failures with root causes.

**Deliverables:**
- `frontend/src/components/SimilarFailuresPanel.tsx` — React component
- Updates to `App.tsx`, `App.css`, `api/client.ts`, `types/index.ts`
- API endpoint for similar failures

**Value:** Learn from past failures without manual searching. One-click navigation to related sessions.

---

## Medium-Term Goals (Completed)

### 4. Trace-to-Memory Bridge Abstraction

Export trace insights to external memory systems via a pluggable interface.

**Deliverables:**
- `agent_debugger_sdk/core/exporters/` — MemoryExporter protocol + TraceInsight models
- `tests/test_memory_exporters.py` — Tests

**Value:** Foundation for feeding debugging insights into any memory system (Hindsight, Zep, LangGraph Store).

### 5. Automated Pattern Detection

Cross-session pattern detection extending existing drift detection.

**Deliverables:**
- `collector/patterns/` — PatternDetector module
- `storage/repositories/pattern_repo.py` — Pattern repository
- `storage/migrations/versions/005_add_patterns.py` — Migration
- `api/analytics_routes.py` — Extended with pattern endpoints
- `tests/patterns/` — Tests

**Value:** Proactive alerts like "this agent's error rate increased 40% this week." Agent health reports.

### 6. Hindsight Memory Integration Adapter

Concrete Hindsight integration building on the trace-to-memory bridge.

**Deliverables:**
- `agent_debugger_sdk/adapters/hindsight.py` — HindsightMemoryAdapter
- `agent_debugger_sdk/config.py` — Hindsight configuration
- `docs/HINDSIGHT_INTEGRATION.md` — Setup documentation
- `tests/adapters/` — Tests with mock Hindsight server

**Value:** Automatically feed debugging insights to Hindsight memory banks. First-mover advantage as "the debugger that makes agents smarter."

---

## Competitive Advantages to Defend

1. **Time-Travel Debugging** — Checkpoint restoration with framework-specific state schemas. No memory system offers this.
2. **Causal Failure Analysis** — BFS upstream cause ranking. Most tools show *what* happened; Peaky Peek shows *why*.
3. **Zero-Code Auto-Instrumentation** — 7+ frameworks with monkey-patching. Massive DX advantage.
4. **Local-First / Privacy-First** — SQLite with optional API server. No cloud dependency.
5. **Live Monitoring with Derived Alerts** — Oscillation detection, guardrail pressure, policy shift alerts.

---

## Future Strategic Direction

### Phase 1 (Now): Best-in-class agent debugger
Time-travel, causal analysis, auto-instrumentation, similar failures, pattern detection.

### Phase 2 (Next): Cross-session learning
Feed debugging insights back into the agent. "Last time you tried approach X, it failed because Y."

### Phase 3 (Vision): Agent Improvement Platform
The convergence of tracing and memory. LangGraph is starting here but is framework-locked. Peaky Peek can be framework-agnostic.

**The pitch:** "Peaky Peek doesn't just show you what your agent did — it learns from it."

---

## Lessons from Hindsight Research

1. **TEMPR multi-strategy retrieval** — Consider adding temporal and entity-based retrieval to session search
2. **Disposition traits** — Could adapt confidence scoring to be agent-personality-aware
3. **Consolidation** — Auto-derive patterns from raw traces, not just detect them
4. **Read-optimized architecture** — Our search is already read-optimized; keep that focus
5. **Tag-based security** — Our tenant_id model maps well to Hindsight's tag boundaries
