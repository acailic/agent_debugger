# Agent Debugger & Visualizer

[![PyPI version](https://img.shields.io/pypi/v/agent-debugger.svg)](https://pypi.org/project/agent-debugger/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)

Agent-native visual debugger for AI agents. Capture execution traces, visualize decision trees, enable time-travel replay, and monitor agents in real time.

## Install

```bash
pip install agent-debugger
```

For framework integrations:

```bash
pip install "agent-debugger[langchain]"
pip install "agent-debugger[crewai]"
pip install "agent-debugger[pydantic-ai]"
pip install "agent-debugger[all]"   # all adapters
pip install "agent-debugger[server]"  # self-hosted server
```

## Quick Start

### 1. Start the API Server

```bash
pip install "agent-debugger[server]"
uvicorn api.main:app --reload --port 8000
```

Server runs at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (Swagger UI)
- **Health**: http://localhost:8000/api/health

### 2. Use the SDK in Your Code

```python
import asyncio
from agent_debugger_sdk import TraceContext

async def my_agent():
    async with TraceContext(session_id="my-session", agent_name="my_agent") as ctx:
        await ctx.record_decision(
            reasoning="User asked about weather",
            confidence=0.85,
            chosen_action="call_weather_tool",
            evidence=[{"source": "user_input", "content": "What's the weather?"}],
        )
        result = await call_weather_api("Seattle")
        await ctx.record_tool_result("weather_api", result=result, duration_ms=100)
    return result

asyncio.run(my_agent())
```

### 3. Decorator API

```python
from agent_debugger_sdk import trace_agent, trace_tool

@trace_agent(name="search_agent", framework="custom")
async def search_agent(query: str) -> str:
    @trace_tool(name="web_search")
    async def web_search(query: str) -> list[str]:
        return [f"result1: {query}", f"result2: {query}"]

    results = await web_search(query)
    return f"Found {len(results)} results for '{query}'"
```

### 4. PydanticAI Integration

```python
from pydantic_ai import Agent
from agent_debugger_sdk.adapters import PydanticAIAdapter

agent = Agent('openai:gpt-4o')
adapter = PydanticAIAdapter(agent, agent_name="my_agent")

async with adapter.trace_session() as session_id:
    result = await agent.run("Hello!")
    print(f"Session: {session_id}")
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create session |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Get session details |
| `GET` | `/api/sessions/{id}/trace` | Normalized trace bundle |
| `GET` | `/api/sessions/{id}/tree` | Decision tree |
| `GET` | `/api/sessions/{id}/checkpoints` | Checkpoints |
| `GET` | `/api/sessions/{id}/analysis` | Adaptive trace analysis |
| `GET` | `/api/sessions/{id}/replay` | Checkpoint-aware replay |
| `GET` | `/api/sessions/{id}/stream` | SSE real-time stream |
| `GET` | `/api/traces/search` | Search across sessions |
| `POST` | `/api/traces` | Ingest trace event |

```bash
curl "http://localhost:8000/api/traces/search?query=weather&event_type=decision&limit=10"
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  VISUALIZATION LAYER                  │
│   DecisionTree  │  ToolInspector  │  SessionReplay   │
│          React + TypeScript (Vite)                    │
└────────────────────────┬────────────────────────────┘
                         │ REST + SSE
                         ▼
┌─────────────────────────────────────────────────────┐
│                     API LAYER                         │
│            FastAPI Server (Python 3.10+)              │
│   Sessions  │   Traces   │  Real-time Events (SSE)   │
└────────────────────────┬────────────────────────────┘
                         │ SQLite
                         ▼
┌─────────────────────────────────────────────────────┐
│                   STORAGE LAYER                       │
│   Sessions  │   Events   │  Checkpoints (Snapshots)  │
└─────────────────────────────────────────────────────┘
```

## Development

```bash
# Clone and install
git clone https://github.com/acailic/agent_debugger
cd agent_debugger
pip install -e ".[server]"

# Run tests
python -m pytest -q

# Build frontend
cd frontend && npm install && npm run build

# Seed demo data
python scripts/seed_demo_sessions.py
```

## Status

| Layer | Status |
|-------|--------|
| SDK Core | Complete |
| Collector | Complete |
| Storage | Complete |
| API | Complete |
| Adapters (LangChain, CrewAI, PydanticAI) | Complete |
| Frontend | Working debugger UI |
| Auth primitives | In progress |
| Redaction | Module complete, ingestion wiring pending |
| Tenant isolation | Planned |

## Documentation

- [Architecture overview](./ARCHITECTURE.md)
- [Full API docs](./docs/README.md)
- [Progress tracker](./docs/progress.md)

## Research

This tool draws on recent work in neural debugging, replay mechanisms, evidence-grounded reasoning, and agentic safety:

- [Towards a Neural Debugger for Python](https://arxiv.org/abs/2603.09951v1)
- [MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning](https://arxiv.org/abs/2603.09892v1)
- [Learning When to Act or Refuse](https://arxiv.org/abs/2603.03205v1) — safe tool use and refusal-aware agent traces
- [Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts](https://arxiv.org/abs/2603.09890v1)

## License

Apache 2.0
