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

init(endpoint="http://localhost:8000")  # no API key needed for a local collector


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

Run the backend locally to receive and inspect the events:

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

Delivery depends on the endpoint, not the API key. With an endpoint and no
API key the SDK sends unauthenticated (local collector mode). With an API
key it sends the same events plus an `Authorization` header (cloud mode).
Without an endpoint the SDK stays inert: events are recorded in memory only
and nothing is sent.

### HTTP delivery and retries

When HTTP transport is active, temporary failures (timeouts, disconnects, HTTP
408, 429, and 5xx responses) receive up to three retries. Authentication errors
and redirects fail immediately; point the endpoint directly at the collector.

For direct `HttpTransport` use, customize retries and observe failed delivery:

```python
import logging

from agent_debugger_sdk.transport import HttpTransport, RetryConfig

transport = HttpTransport(
    endpoint="http://localhost:8000",
    retry_config=RetryConfig(max_retries=3, max_backoff_seconds=10),
    on_delivery_failure=lambda error: logging.warning("Trace delivery failed: %s", error),
)
# Use `async with transport:` when sending events to close its HTTP client.
```

The default backoff starts at 0.5 seconds, doubles after each retry, and is capped
at 30 seconds per delay. The transport honors `Retry-After` seconds and HTTP
dates. If the server requests a delay above the configured cap, delivery ends
with a failure callback instead of retrying early. Delivery failures are logged
and do not raise into your agent; retries are finite and do not guarantee delivery.

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
| `AGENT_DEBUGGER_URL` | - | Collector endpoint; enables HTTP delivery when set |
| `AGENT_DEBUGGER_ENABLED` | `true` | Enable or disable tracing |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Sampling rate |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Redact prompts before storage |
| `AGENT_DEBUGGER_MAX_PAYLOAD_KB` | `100` | Max payload size for emitted events |

## More Docs

- [Intro](../docs/guides/intro.md)
- [Integration](../docs/guides/integration.md)
- [Progress](../docs/guides/progress.md)

## License

MIT
