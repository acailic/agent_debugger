# Agent Debugger

See **why** your AI agent did that. Agent-native debugging for LangChain, CrewAI, PydanticAI, and custom agents.

## Quickstart (60 seconds)

```bash
pip install agent-debugger
```

```python
import agent_debugger

agent_debugger.init()  # Local mode — no account needed

# Your existing agent code works unchanged
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4")
result = llm.invoke("What's the weather?")

# Open http://localhost:8000 to see the trace
```

## Cloud Mode

```bash
export AGENT_DEBUGGER_API_KEY=ad_live_...
```

Events now flow to the cloud dashboard with team sharing, longer retention, and collaboration.

## Integration Levels

**Auto** (zero code change): `agent_debugger.init()` — patches LangChain/CrewAI automatically.

**Decorators** (selective): `@trace_agent`, `@trace_tool`, `@trace_llm`

**Manual** (full control): `TraceContext` async context manager.

## What You See

- **Decision trees** — why the agent chose each action
- **Evidence provenance** — what evidence justified each decision
- **Time-travel replay** — jump to any checkpoint
- **Live monitoring** — anomaly detection for running agents

## Configuration

```python
agent_debugger.init(
    api_key="ad_live_...",           # Optional: enables cloud mode
    endpoint="https://api.agentdebugger.dev",  # Custom endpoint
    enabled=True,                     # Disable for production silence
    sample_rate=1.0,                  # Sample 10% of traces in prod
    redact_prompts=False,             # Redact LLM prompts before storage
)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_API_KEY` | - | API key for cloud mode |
| `AGENT_DEBUGGER_URL` | `http://localhost:8000` | Collector endpoint |
| `AGENT_DEBUGGER_ENABLED` | `true` | Enable/disable tracing |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Sampling rate (0.0-1.0) |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Redact LLM prompts |

## Framework Adapters

### LangChain

```python
import agent_debugger
agent_debugger.init()

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4")  # Automatically traced
```

### Custom Agents

```python
import agent_debugger
from agent_debugger import TraceContext

agent_debugger.init()

async with TraceContext(agent_name="my_agent", framework="custom") as ctx:
    # Record decisions
    await ctx.record_decision(
        reasoning="User asked about weather",
        confidence=0.9,
        evidence=[{"source": "user_input", "content": "What's the weather?"}],
        chosen_action="call_weather_tool"
    )

    # Record tool calls
    await ctx.record_tool_call("weather_api", {"location": "SF"})
    result = await weather_api.call("SF")
    await ctx.record_tool_result("weather_api", result, duration_ms=150)
```

## License

Apache-2.0