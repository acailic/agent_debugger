# ADR-004: Target Users & Framework Priority

**Status:** Accepted
**Date:** 2026-03-23

## Context

The AI agent ecosystem has multiple frameworks, each with different architectures and callback systems. We cannot support all frameworks equally from day one. We need to prioritize based on ecosystem size, debugging need, and integration complexity.

## Decision

### Primary Persona

**Developer building AI agents who needs to understand agent behavior.**

Typical profile:
- Python developer (95% of agent development is Python)
- Using one or more agent frameworks
- Building agents that make decisions, use tools, and interact with external systems
- Debugging issues like: agent loops, wrong tool selection, poor reasoning, safety violations, unexpected behavior

### Framework Priority

| Priority | Framework | Ecosystem Size | Debugging Need | Integration Complexity | Status |
|----------|-----------|---------------|----------------|----------------------|--------|
| 1 | **LangChain / LangGraph** | Largest (90k+ GitHub stars) | Very high (complex agents) | Medium (callback system) | Adapter exists, needs hardening |
| 2 | **CrewAI** | Fast-growing (25k+ stars) | High (multi-agent) | Medium | Not started |
| 3 | **AutoGen** | Large (40k+ stars, Microsoft) | High (multi-agent) | Medium-High | Not started |
| 4 | **PydanticAI** | Growing | Medium | Low (clean API) | Adapter complete |
| 5 | **OpenAI Agents SDK** | New but strategic | Medium | Low | Not started |
| 6 | **Custom / Direct SDK** | Universal | Varies | None (raw API) | Complete |

### Rationale for LangChain First

- Largest active user base with the most complex agent architectures
- LangSmith is their own tool, but it is broad, not deep on debugging
- LangChain users are most likely to feel the pain of inadequate debugging
- LangChain's callback system is well-documented and stable
- Success with LangChain users validates the core product thesis

### CrewAI Second

- Multi-agent framework = perfect fit for our multi-agent debugging features
- Growing fast, no strong debugging tool yet
- Users are building production agents that need debugging

## Consequences

- LangChain adapter must be production-quality before public launch
- CrewAI adapter should be ready within first month post-launch
- SDK must be framework-agnostic at core, with adapters as thin wrappers
- Documentation and examples must lead with LangChain
- Marketing content should target LangChain community first (blog posts, Discord, Twitter)
