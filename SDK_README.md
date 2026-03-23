# Agent Debugger

See why your AI agent did that. This package gives you a tracing SDK for custom agents plus integration points for PydanticAI and LangChain.

## What This Package Gives You

- `TraceContext` for explicit tracing
- decorators for agent, tool, and LLM boundaries
- adapter entry points for supported frameworks
- configuration for local or cloud-oriented transport settings

## Quick Start

```bash
pip install peaky-peek
```

```python
import asyncio

from agent_debugger_sdk import TraceContext, init

init()  # Local mode by default


async def main() -> None:
    async with TraceContext(agent_name="demo_agent", framework="custom") as ctx:
        await ctx.record_decision(
            reasoning="Need external information",
            confidence=0.9,
            chosen_action="call_search_tool",
            evidence=[{"source": "user_input", "content": "What is the weather?"}],
        )


asyncio.run(main())
```

Run the backend locally if you want to receive and inspect events:

```bash
pip install peaky-peek-server
uvicorn api.main:app --reload --port 8000
```

## Configuration

```python
from agent_debugger_sdk import init

init(
    api_key="ad_live_...",            # optional
    endpoint="https://api.agentdebugger.dev",
    enabled=True,
    sample_rate=1.0,
    redact_prompts=False,
)
```

If no API key is set, the SDK stays in local mode and defaults to `http://localhost:8000`.

## Integration Options

### `TraceContext`

Use `TraceContext` when you want explicit control over recorded events.

```python
import asyncio

from agent_debugger_sdk import TraceContext, init

init()


async def main() -> None:
    async with TraceContext(agent_name="my_agent", framework="custom") as ctx:
        await ctx.record_tool_call("weather_api", {"location": "SF"})
        result = {"forecast": "sunny"}
        await ctx.record_tool_result("weather_api", result=result, duration_ms=150)


asyncio.run(main())
```

### Decorators

Use decorators when your code already has clear boundaries:

```python
from agent_debugger_sdk import init, trace_agent, trace_tool

init()

@trace_tool(name="search_docs")
async def search_docs(query: str) -> list[str]:
    return [query]

@trace_agent(name="docs_agent", framework="custom")
async def docs_agent(query: str) -> list[str]:
    return await search_docs(query)
```

### Adapters

#### PydanticAI

```python
from pydantic_ai import Agent

from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import PydanticAIAdapter

init()

agent = Agent("openai:gpt-4o")
adapter = PydanticAIAdapter(agent, agent_name="support_agent")
```

#### LangChain

```python
from agent_debugger_sdk import TraceContext, init
from agent_debugger_sdk.adapters import LangChainTracingHandler

init()

context = TraceContext(session_id="demo", agent_name="langchain_agent", framework="langchain")
handler = LangChainTracingHandler(session_id="demo")
handler.set_context(context)
```

Important:

- the current LangChain path is handler-based
- `init()` does not currently auto-patch LangChain for zero-code instrumentation

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_API_KEY` | - | API key for cloud-oriented mode |
| `AGENT_DEBUGGER_URL` | `http://localhost:8000` | Collector endpoint |
| `AGENT_DEBUGGER_ENABLED` | `true` | Enable or disable tracing |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Sampling rate |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Redact prompts before storage |
| `AGENT_DEBUGGER_MAX_PAYLOAD_KB` | `100` | Max payload size for emitted events |

## More Docs

- [Intro](./docs/intro.md)
- [Integration](./docs/integration.md)
- [Progress](./docs/progress.md)

## License

Apache-2.0
