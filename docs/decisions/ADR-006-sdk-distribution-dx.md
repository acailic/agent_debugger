# ADR-006: SDK Distribution & Developer Experience

**Status:** Accepted
**Date:** 2026-03-23

## Context

SDK adoption is the top-of-funnel for the entire product. If integration is hard, nobody uses the debugger. The SDK must be the easiest part of the developer's day.

## Decision

Ship a pip-installable SDK with three integration levels: decorator, adapter, and manual.

### Package

- **PyPI name**: `agent-debugger`
- **Import name**: `agent_debugger_sdk`
- **License**: Apache 2.0
- **Python**: 3.10+
- **Dependencies**: Minimal (pydantic, httpx). Framework adapters are optional extras.

### Installation

```bash
# Core SDK
pip install agent-debugger

# With framework adapters
pip install agent-debugger[langchain]
pip install agent-debugger[pydantic-ai]
pip install agent-debugger[all]
pip install agent-debugger[server]
```

### Three Integration Levels

**Level 1: Decorator-based (selective tracing)**

```python
from agent_debugger_sdk import init, trace_agent, trace_tool

init()

@trace_agent
async def my_agent(query: str):
    result = await my_tool(query)
    return result

@trace_tool
async def my_tool(query: str):
    return search(query)
```

For developers who want control over what gets traced without full manual instrumentation.

**Level 2: Framework adapters (integration hooks)**

Use adapters when the framework already exposes the right integration hooks.

```python
from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import PydanticAIAdapter

init()

agent = Agent("openai:gpt-4o")
adapter = PydanticAIAdapter(agent, agent_name="support_agent")

async with adapter.trace_session() as session_id:
    result = await agent.run("Summarize this issue")
```

**Level 3: Manual (full control)**

```python
from agent_debugger_sdk import TraceContext, init

init()

async with TraceContext(agent_name="researcher") as ctx:
    await ctx.record_decision(
        reasoning="User asked about weather, choosing weather API",
        confidence=0.92,
        chosen_action="call_weather_api",
        evidence=[{"source": "user_input", "content": query}]
    )
    result = await weather_api.call(query)
    await ctx.record_tool_result("weather_api", result, duration_ms=150)
```

For custom frameworks or when developers need precise control over event semantics.

### Configuration

All configuration via environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_API_KEY` | None | Cloud API key. If unset, runs in local mode. |
| `AGENT_DEBUGGER_URL` | `http://localhost:8000` | Collector endpoint |
| `AGENT_DEBUGGER_ENABLED` | `true` | Kill switch for production |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Event sampling (0.0-1.0) |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Strip prompt content before sending |

### Local Mode Behavior

When no API key is set:
1. Events go to `localhost:8000`
2. Data persists in local SQLite
3. UI available at `http://localhost:5173` (when running frontend)

No cloud dependency. No signup required. Just `pip install` and go.

## Key DX Decisions

1. **No signup required for local**: The product must be useful before asking for an email.
2. **First value in under 60 seconds**: `pip install` → `import` → `init()` → see traces.
3. **No breaking changes to user's agent code**: Adapters plug into framework hooks, not user code.
4. **Graceful degradation**: If collector is down, SDK logs a warning and continues. Never crash the user's agent.

## Consequences

- Decorators and adapters require maintaining compatibility with framework version updates
- Must handle SDK errors silently (never disrupt the user's agent)
- Local mode requires running the API server separately
- Must document all three integration levels clearly
