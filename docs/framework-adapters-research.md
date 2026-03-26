# AI Agent Framework Adapters Research

**Date:** 2026-03-26
**Purpose:** Identify the top 10 most-downloaded AI agent frameworks and map Peaky Peek adapter coverage.

---

## Top 10 AI Agent Frameworks by PyPI Downloads

| Rank | Framework | PyPI Package | Monthly Downloads | GitHub Stars | PP Adapter | Notes |
|------|-----------|-------------|-------------------|-------------|------------|-------|
| 1 | LangChain | `langchain` | 224.9M | 131K | Native + Auto-patch | Market leader. LangGraph is its multi-agent extension. |
| 2 | OpenAI Agents | `openai-agents` | 19.8M | 20K | None | Official OpenAI SDK. Fast-growing since late 2025. |
| 3 | PydanticAI | `pydantic-ai` | 16.5M | 16K | Native + Auto-patch | Peaky Peek's primary beachhead. Backed by Pydantic team. |
| 4 | LangGraph | `langgraph` | 41.9M | 28K | None | Graph-based orchestration layer for LangChain. |
| 5 | LlamaIndex | `llama-index-core` | 6.7M | 48K | Auto-patch | RAG-focused framework. High star count, moderate downloads. |
| 6 | CrewAI | `crewai` | 6.2M | 47K | Auto-patch | Multi-agent orchestration. Strong community. |
| 7 | Semantic Kernel | `semantic-kernel` | 2.7M | 28K | None | Microsoft's framework. Python + .NET. Enterprise focus. |
| 8 | Haystack | `haystack-ai` | 662K | 25K | None | deepset's NLP pipeline framework. European AI co. |
| 9 | AG2 (AutoGen) | `ag2` | 595K | 4K | Auto-patch | Multi-agent conversation framework (Microsoft origins). |
| 10 | Smolagents | `smolagents` | 496K | 26K | None | HuggingFace's lightweight agent framework. |

---

## Methodology

- **PyPI downloads:** Sourced from pypistats.org `/api/packages/{pkg}/recent` (`last_month` field), fetched 2026-03-26
- **GitHub stars:** GitHub REST API, fetched 2026-03-26
- **Package names:** Verified against actual PyPI distribution names
- **Ranking:** Sorted by PyPI monthly downloads descending

---

## Adapter Coverage Summary

| Status | Count | Frameworks |
|--------|-------|-----------|
| Native + Auto-patch | 2 | LangChain, PydanticAI |
| Auto-patch only | 3 | CrewAI, LlamaIndex, AG2 |
| No adapter | 5 | OpenAI Agents, LangGraph, Semantic Kernel, Haystack, Smolagents |

**Coverage:** 5 of 10 top frameworks have some form of adapter (50%). However, by download volume, covered frameworks account for ~86% of total top-10 downloads (dominated by LangChain).

---

## Priority Recommendations

### High Priority (large gap, high impact)

| Framework | Why | Approach |
|-----------|-----|---------|
| **OpenAI Agents** | #2 by downloads, #4 by growth, zero competition for debugging | Build native adapter. Captures agent runs, handoffs, tool calls, guardrails. |
| **LangGraph** | 41.9M downloads, shares LangChain user base | Extend existing LangChain adapter or build dedicated. Captures graph nodes, edges, state transitions. |

### Medium Priority (moderate gap, strategic value)

| Framework | Why | Approach |
|-----------|-----|---------|
| **Smolagents** | HuggingFace backing, growing fast, lightweight (easy to instrument) | Build auto-patch adapter. Captures tool calls, agent steps, CodeAgent execution. |

### Low Priority (small gap or low leverage)

| Framework | Why | Approach |
|-----------|-----|---------|
| **Semantic Kernel** | Enterprise/microsoft ecosystem, Python is secondary to .NET | Monitor. Build only if enterprise demand materializes. |
| **Haystack** | 662K downloads, NLP-pipeline focus (not agent-first) | Monitor. Lower priority than pure agent frameworks. |

---

## Key Insight

LangChain + LangGraph together represent ~250M+ monthly downloads — over 70% of the total top-10 volume. The existing LangChain adapter already covers the largest chunk. The biggest **coverage gap by volume** is **OpenAI Agents** (19.8M, no adapter) and **LangGraph** (41.9M, no dedicated adapter despite sharing the LangChain ecosystem).
