# ADR-006: SDK Distribution & Developer Experience

**Status:** Accepted
**Date:** 2026-03-23

## Context

SDK adoption is the top-of-funnel for the entire product. If integration is hard, nobody uses the debugger. The SDK must be the easiest part of the developer's day.

## Decision

Ship a pip-installable SDK with three integration levels: auto, decorator, and manual.

### Package

- **PyPI name**: `agent-debugger`
- **Import name**: `agent_debugger`
- **License**: Apache 2.0
- **Python**: 3.10+
- **Dependencies**: Minimal (pydantic, httpx). Framework adapters are optional extras.

### Installation

```bash
# Core SDK
pip install agent-debugger

# With framework adapters
pip install agent-debugger[langchain]
pip install agent-debugger[crewai]
pip install agent-debugger[all]
```

### Three Integration Levels

**Level 1: Auto-instrumentation (zero code change)**

```python
import agent_debugger
agent_debugger.init(api_key="ad_...")  # or AGENT_DEBUGGER_API_KEY env var

# That's it. LangChain/CrewAI calls are automatically traced.
```

Auto-instrumentation patches framework callback systems automatically. Similar to how Sentry or OpenTelemetry auto-instruments. This is the default experience for new users.

**Level 2: Decorator-based (selective tracing)**

```python
from agent_debugger import trace_agent, trace_tool

@trace_agent
async def my_agent(query: str):
    result = await my_tool(query)
    return result

@trace_tool
async def my_tool(query: str):
    return search(query)
```

For developers who want control over what gets traced without full manual instrumentation.

**Level 3: Manual (full control)**

```python
from agent_debugger import TraceContext

async with TraceContext(session_id="debug-123", agent_name="researcher") as ctx:
    await ctx.record_decision(
        reasoning="User asked about weather, choosing weather API",
        confidence=0.92,
        chosen_action="call_weather_api",
        evidence_event_ids=[prior_event.id]
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
| `AGENT_DEBUGGER_MAX_PAYLOAD_KB` | `100` | Truncate payloads larger than this |

### Local Mode Behavior

When no API key is set:
1. SDK starts a background local collector (if not already running)
2. Events go to `localhost:8000`
3. Data persists in `~/.agent-debugger/data.db`
4. UI available at `http://localhost:8000`

No cloud dependency. No signup. No account. Just `pip install` and go.

## Key DX Decisions

1. **No signup required for local**: The product must be useful before asking for an email.
2. **First value in under 60 seconds**: `pip install` → `import` → `init()` → see traces.
3. **No breaking changes to user's agent code**: Auto-instrumentation patches framework internals, not user code.
4. **Graceful degradation**: If collector is down, SDK logs a warning and continues. Never crash the user's agent.
5. **TypeScript SDK is not for v1**: 95%+ of agent development is Python. Ship JS SDK only if there's demand.

## Consequences

- Auto-instrumentation requires deep knowledge of each framework's internals
- Must maintain compatibility with framework version updates
- Must handle SDK errors silently (never disrupt the user's agent)
- Local mode needs a lightweight embedded server (or background process)
- Must document all three integration levels clearly
