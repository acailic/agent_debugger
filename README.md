# Agent Debugger & Visualizer

Visual debugging tool for AI agents that captures execution traces, visualizes decision trees, enables time-travel debugging, and provides real-time monitoring.

For project documentation, start in [docs/README.md](./docs/README.md). The root [LEARNING.md](./LEARNING.md) now points to the focused docs pages.

## Research Inspiration

This repo is informed by recent work around neural debugging, replay, evidence-grounded reasoning, agent safety, and multi-agent control:

- [Towards a Neural Debugger for Python](https://arxiv.org/abs/2603.09951v1) - neural debugger interactions, breakpoint-style execution, and execution-conditioned reasoning
- [MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning](https://arxiv.org/abs/2603.09892v1) - adaptive replay and retention-aware trace prioritization
- [CXReasonAgent: Evidence-Grounded Diagnostic Reasoning Agent for Chest X-rays](https://arxiv.org/abs/2602.23276v1) - evidence-grounded multi-step reasoning and verifiability in high-stakes settings
- [NeuroSkill(tm): Proactive Real-Time Agentic System Capable of Modeling Human State of Mind](https://arxiv.org/abs/2603.03212v1) - real-time agent loops and state-aware interaction design
- [Learning When to Act or Refuse: Guarding Agentic Reasoning Models for Safe Multi-Step Tool Use](https://arxiv.org/abs/2603.03205v1) - safe tool use, explicit checks, and refusal-aware agent traces
- [Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts](https://arxiv.org/abs/2603.09890v1) - controllable multi-agent behavior and policy-like prompt instrumentation

## Quick Start

### 1. Start the API Server

```bash
cd agent_debugger

# Install dependencies (if not already in main amplifier project)
pip install fastapi uvicorn sqlalchemy aiosqlite pydantic

# Start the server
uv run uvicorn api.main:app --reload --port 8000
```

Server runs at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (Swagger UI)
- **Health**: http://localhost:8000/api/health

### 2. Use the SDK in Your Code

```python
import asyncio
from agent_debugger_sdk import TraceContext, EventType

async def my_agent():
    """Simple agent example."""
    async with TraceContext(session_id="my-session", agent_name="my_agent") as ctx:
        # Record a decision
        await ctx.record_decision(
            reasoning="User asked about weather",
            confidence=0.85,
            chosen_action="call_weather_tool",
            evidence=[{"source": "user_input", "content": "What's the weather?"}],
        )

        # Your agent logic here
        result = await call_weather_api("Seattle")

        # Record tool result
        await ctx.record_tool_result(
            "weather_api",
            result=result,
            duration_ms=100,
        )

    return result

async def call_weather_api(location: str) -> dict:
    """Simulated weather API call."""
    await asyncio.sleep(0.1)  # Simulate network delay
    return {"temp": 72, "conditions": "sunny", "location": location}

# Run the agent
asyncio.run(my_agent())
```

### 3. Using Decorators

```python
from agent_debugger_sdk import trace_agent, trace_tool

@trace_agent(name="search_agent", framework="custom")
async def search_agent(query: str) -> str:
    @trace_tool(name="web_search")
    async def web_search(query: str) -> list[str]:
        await asyncio.sleep(0.05)
        return [f"result1: {query}", f"result2: {query}"]

    results = await web_search(query)
    return f"Found {len(results)} results for '{query}'"

# Run the agent
result = asyncio.run(search_agent("python async"))
print(result)
```

### 4. PydanticAI Integration

```python
from pydantic_ai import Agent
from agent_debugger_sdk.adapters import PydanticAIAdapter

# Create and wrap agent
agent = Agent('openai:gpt-4o')
adapter = PydanticAIAdapter(agent, agent_name="my_agent")

# Trace a session
async with adapter.trace_session() as session_id:
    result = await agent.run("Hello!")
    print(f"Session: {session_id}")
```

### 5. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create session |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Get session details |
| `GET` | `/api/sessions/{id}/trace` | Normalized trace bundle for frontend |
| `GET` | `/api/sessions/{id}/traces` | Get all traces |
| `GET` | `/api/sessions/{id}/tree` | Get decision tree |
| `GET` | `/api/sessions/{id}/checkpoints` | List checkpoints |
| `GET` | `/api/sessions/{id}/analysis` | Adaptive trace analysis |
| `GET` | `/api/sessions/{id}/replay` | Checkpoint-aware replay |
| `GET` | `/api/sessions/{id}/stream` | **SSE real-time stream** |
| `GET` | `/api/traces/search` | Search trace events across sessions |
| `POST` | `/api/traces` | Ingest trace event |

Search example:

```bash
curl "http://localhost:8000/api/traces/search?query=Belgrade&event_type=decision&limit=10"
```

### 6. Run Tests

```bash
cd agent_debugger
venv/bin/python -m pytest -q
cd frontend && npm run build
```

### 7. Seed Demo Sessions

```bash
cd agent_debugger
venv/bin/python scripts/seed_demo_sessions.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VISUALIZATION LAYER                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │
│  │ DecisionTree │  │ ToolInspector │  │ LLMViewer + SessionReplay │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │
│                         React Frontend (Vite + TypeScript)                  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ REST + SSE
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│                    FastAPI Server (Python 3.11+)                       │  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │
│  │  Sessions  │  │   Traces    │  │    Real-time Events (SSE)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ SQLite
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            STORAGE LAYER                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│                         Trace Store                                │  │
│  ┌─────────────┐  ┌─────────────┐  └──────────────────────────────────┐ │
│  │  Sessions   │  │   Events    │  │ Checkpoints (Snapshots)          │  │
│  └─────────────┘  └─────────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Status

| Layer | Status |
|-------|--------|
| SDK Core | ✅ Complete |
| Collector | ✅ Complete |
| Storage | ✅ Complete |
| API | ✅ Complete |
| Adapters | ✅ Complete |
| Frontend | ✅ Working debugger UI |

## Next Steps

1. **Add auth + multi-user tenancy** for shared trace workspaces
2. **Add richer benchmark corpora** for safety and replay regressions
3. **Deploy** the API and frontend as one packaged debugger product
