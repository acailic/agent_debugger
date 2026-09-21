# Integration

This page shows the simplest supported ways to integrate the debugger with your code.

## Local Setup

The supported install is the server wheel (see [Getting Started](./getting-started.md)); the checkout below is the development path:

```bash
pip install -e .
pip install fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" aiosqlite alembic aiofiles bcrypt
uvicorn api.main:app --reload --port 8000
```

If you want the frontend UI during development, run it separately:

```bash
cd frontend
npm install
npm run dev
```

Default local addresses:

- API: `http://localhost:8000`
- FastAPI docs: `http://localhost:8000/docs`
- Bundled UI (served by the server when `frontend/dist` is built): `http://localhost:8000/ui/`
- Frontend dev UI: `http://localhost:5173`

## SDK Configuration

The SDK configuration entry point is `init()`:

```python
from agent_debugger_sdk import init

init(endpoint="http://localhost:8000")
```

That resolves local versus cloud mode, endpoint, enablement, sampling, and prompt-redaction settings.

Important:

- the SDK delivers over HTTP only when an endpoint is configured (argument or `AGENT_DEBUGGER_URL`): keyless against a local collector, with a Bearer key in cloud mode. Without an endpoint it stays inert — events are recorded in memory only
- `init()` itself does not auto-patch frameworks; zero-code instrumentation is the separate `PEAKY_PEEK_AUTO_PATCH` mechanism below

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

## Choose An Integration Level

There are three practical ways to integrate today.

### 1. `TraceContext`

Use this when you want explicit control over what gets recorded.

```python
import asyncio

from agent_debugger_sdk import TraceContext, init

init(endpoint="http://localhost:8000")


async def my_agent(question: str) -> str:
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
        return result["forecast"]


asyncio.run(my_agent("What's the weather in Seattle?"))
```

This is the best starting point if you are building your own agent loop.

### 2. Decorators

Use this when you want lighter instrumentation around an existing flow.

```python
from agent_debugger_sdk import init, trace_agent, trace_tool

init(endpoint="http://localhost:8000")


@trace_tool(name="search_docs")
async def search_docs(query: str) -> list[str]:
    return [f"doc result for {query}"]


@trace_agent(name="docs_agent", framework="custom")
async def docs_agent(query: str) -> str:
    results = await search_docs(query)
    return results[0]
```

Available decorators:

- `@trace_agent`
- `@trace_tool`
- `@trace_llm`

### 3. Framework Adapters

Use adapters when the framework already exposes the right integration hooks.

#### PydanticAI

```python
import asyncio

from pydantic_ai import Agent

from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import PydanticAIAdapter

init(endpoint="http://localhost:8000")


async def main() -> None:
    agent = Agent("openai:gpt-4o")
    adapter = PydanticAIAdapter(agent, agent_name="support_agent")

    async with adapter.trace_session() as session_id:
        result = await agent.run("Summarize this issue")
        print(session_id, result)


asyncio.run(main())
```

#### LangChain

Use the tracing handler with your callback flow:

```python
from agent_debugger_sdk import TraceContext, init
from agent_debugger_sdk.adapters import LangChainTracingHandler

init(endpoint="http://localhost:8000")

context = TraceContext(session_id="demo", agent_name="langchain_agent", framework="langchain")
handler = LangChainTracingHandler(session_id="demo")
handler.set_context(context)
```

The current LangChain path is handler-based. For zero-code instrumentation across frameworks (OpenAI, Anthropic, LangChain, PydanticAI, CrewAI, AutoGen, LlamaIndex), set `PEAKY_PEEK_AUTO_PATCH=all` before running your agent — see the [auto-patch module](../../agent_debugger_sdk/auto_patch/__init__.py) for the environment knobs.

## Which Option To Pick

- use `TraceContext` if you want the clearest and most explicit setup
- use decorators if your code already has clear agent and tool boundaries
- use adapters if you are already inside PydanticAI or LangChain integration points

## Related Docs

- [Intro](./intro.md)
- [How It Works](./how-it-works.md)
- [Repo Overview](./repo-overview.md)
- [Progress](./progress.md)
