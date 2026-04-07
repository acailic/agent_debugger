---
title: Getting Started
description: Get up and running with Peaky Peek in 5 minutes
---

# Getting Started with Peaky Peek

Debug AI agents with time-travel replay, decision trees, and cost tracking. This guide takes about 5 minutes.

## 1. Install

```bash
pip install peaky-peek-server
```

## 2. Start the Debugger

```bash
peaky-peek --open
```

This starts the server at http://localhost:8000 and opens your browser.

## 3. Instrument Your Agent

```python
import asyncio
from agent_debugger_sdk import TraceContext, init

init()

async def main():
    async with TraceContext(agent_name="demo", framework="custom") as ctx:
        await ctx.record_decision(
            reasoning="User asked for weather",
            confidence=0.85,
            chosen_action="call_weather_api",
        )
        await ctx.record_tool_call("weather_api", {"city": "Seattle"})
        await ctx.record_tool_result("weather_api", result={"temp": 72})

asyncio.run(main())
```

## 4. Explore the UI

Refresh your browser — you'll see your first trace.

- **Timeline**: Click events to inspect details
- **Decision Tree**: Visualize reasoning chains
- **Cost**: See token usage and estimated costs

## 5. Export Your Data

```bash
curl http://localhost:8000/api/sessions/<session-id>/export | jq . > trace.json
```

## Zero-Config Auto-Patching (No Code Changes)

Already have an agent using OpenAI or Anthropic SDK? No code changes needed:

```bash
PEAKY_PEEK_AUTO_PATCH=all python your_agent.py
```

Peaky Peek automatically captures all LLM calls and tool use.

## SDK Configuration Options

The SDK configuration entry point is `init()`:

```python
from agent_debugger_sdk import init

init()
```

That resolves local versus cloud mode, endpoint, enablement, sampling, and prompt-redaction settings.

Cloud-style configuration uses the same entry point:

```python
from agent_debugger_sdk import init

init(
    api_key="ad_live_...",
    endpoint="https://api.agentdebugger.dev",
    sample_rate=1.0,
    redact_prompts=False,
)
```

## Choosing Your Integration Method

### Use `TraceContext` When

You want explicit control over what gets recorded:

```python
async with TraceContext(agent_name="weather_agent", framework="custom") as ctx:
    await ctx.record_decision(
        reasoning="The user asked for live weather data",
        confidence=0.91,
        chosen_action="call_weather_api",
        evidence=[{"source": "user_input", "content": question}],
    )
    await ctx.record_tool_call("weather_api", {"location": "Seattle"})
    result = {"forecast": "rain", "temperature_c": 12}
    await ctx.record_tool_result("weather_api", result=result, duration_ms=120)
```

### Use Decorators When

You want lighter instrumentation around an existing flow:

```python
from agent_debugger_sdk import init, trace_agent, trace_tool

init()

@trace_tool(name="search_docs")
async def search_docs(query: str) -> list[str]:
    return [f"doc result for {query}"]

@trace_agent(name="docs_agent", framework="custom")
async def docs_agent(query: str) -> str:
    results = await search_docs(query)
    return results[0]
```

### Use Adapters When

The framework already exposes the right integration hooks:

```python
from pydantic_ai import Agent
from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import PydanticAIAdapter

init()

agent = Agent("openai:gpt-4o")
adapter = PydanticAIAdapter(agent, agent_name="support_agent")
```

## Next Steps

- [How It Works](../docs/how-it-works.md) — Understanding the system architecture
- [Installation](installation.md) — Detailed installation options
- [Integrations](integrations.md) — Framework-specific setup guides
- [Configuration](configuration.md) — Environment variables and settings
