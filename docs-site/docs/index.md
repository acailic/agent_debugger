---
title: Home
description: Local-first AI agent debugger with replay, failure memory, smart highlights, and drift detection
---

# Peaky Peek

**Local-first agent debugger with replay, failure memory, smart highlights, and drift detection.**

<p align="center">
  <code>pip install peaky-peek-server && peaky-peek --open</code>
</p>

## Why Peaky Peek?

Traditional observability tools weren't built for agent-native debugging:

| Tool | Focus | Problem |
|------|-------|---------|
| LangSmith | LLM tracing | SaaS-first, your data leaves your machine |
| OpenTelemetry | Infra metrics | Blind to reasoning chains and decision trees |
| Sentry | Error tracking | No insight into *why* agents chose specific actions |
| **Peaky Peek** | **Agent-native debugging** | **Local-first, open source, privacy by default** |

Peaky Peek captures the **causal chain** behind every action so you can debug agents like distributed systems: trace failures, replay from checkpoints, and search across reasoning paths.

## Key Features

### Decision Tree Visualization
Navigate agent reasoning as an interactive tree. Click nodes to inspect events, zoom to explore complex flows, and trace the causal chain from policy to tool call to safety check.

### Checkpoint Replay
Time-travel through agent execution with checkpoint-aware playback. Play, pause, step, and seek to any point in the trace. Checkpoints are ranked by restore value so you jump to the most useful state.

### Trace Search
Find specific events across all sessions. Search by keyword, filter by event type, and jump directly to results.

### Failure Clustering & Multi-Agent Coordination
Adaptive analysis groups similar failures. Inspect planner/critic debates, speaker topology, and prompt policy parameters across multi-agent systems.

### Session Comparison
Compare two agent runs side-by-side. See diffs in turn count, speaker topology, policies, stance shifts, and grounded decisions.

## Quick Start

```bash
pip install peaky-peek-server
peaky-peek --open
```

This starts the server at http://localhost:8000 and opens your browser.

## Three Ways to Instrument

### 1. Decorator (Simplest)

```python
from agent_debugger_sdk import trace

@trace
async def my_agent(prompt: str) -> str:
    # Your agent logic here — traces are captured automatically
    return await llm_call(prompt)
```

### 2. Context Manager

```python
from agent_debugger_sdk import trace_session

async with trace_session("weather_agent") as ctx:
    await ctx.record_decision(
        reasoning="User asked for weather",
        confidence=0.9,
        chosen_action="call_weather_api",
        evidence=[{"source": "user_input", "content": "What's the weather?"}],
    )
    await ctx.record_tool_call("weather_api", {"city": "Seattle"})
    await ctx.record_tool_result("weather_api", result={"temp": 52, "forecast": "rain"})
```

### 3. Zero-Config Auto-Patch (No Code Changes)

```bash
PEAKY_PEEK_AUTO_PATCH=true python my_agent.py
```

Works with **PydanticAI, LangChain, OpenAI SDK, CrewAI, AutoGen, LlamaIndex, and Anthropic** — no imports or decorators needed.

## Project Status

- **Core debugger** — local path end-to-end, stable
- **SDK** — `@trace`, `trace_session()`, auto-patch for 7 frameworks
- **API** — 11 routers: sessions, traces, replay, search, analytics, cost, comparison
- **Frontend** — 8 specialized panels (decision tree, replay, checkpoints, search)
- **Tests** — 365+ passing, CI on Python 3.10/3.11/3.12

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart guide
- [Installation](installation.md) — Detailed install options
- [Integrations](integrations.md) — Framework-specific setup
- [Architecture](architecture.md) — System design overview
- [API Reference](api-reference.md) — API endpoints documentation
