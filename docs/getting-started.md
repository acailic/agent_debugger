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

## Next Steps

- [How It Works](./how-it-works.md)
- [Architecture](./architecture.md)
- [Examples](../examples/)
