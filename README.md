# Agent Debugger & Visualizer

[![PyPI peaky-peek](https://img.shields.io/pypi/v/peaky-peek.svg?label=peaky-peek)](https://pypi.org/project/peaky-peek/)
[![PyPI peaky-peek-server](https://img.shields.io/pypi/v/peaky-peek-server.svg?label=peaky-peek-server)](https://pypi.org/project/peaky-peek-server/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

When your AI agent does something wrong, you need to know *why* — not just that it failed. Agent Debugger captures every decision, tool call, and LLM interaction as a queryable event timeline. Inspect live, replay from checkpoints, search across sessions.

| Package | Install | What you get |
|---|---|---|
| [`peaky-peek`](https://pypi.org/project/peaky-peek/) | `pip install peaky-peek` | Tracing SDK — `TraceContext`, decorators, LangChain/CrewAI/PydanticAI adapters |
| [`peaky-peek-server`](https://pypi.org/project/peaky-peek-server/) | `pip install peaky-peek-server` | Full stack — SDK + FastAPI server + SQLite storage + SSE + React UI |

## Quick Start

### 1. Install

```bash
# SDK only (instrument your agents)
pip install peaky-peek

# Full self-hosted stack
pip install peaky-peek-server
```

### 2. Start the local API

```bash
uvicorn api.main:app --reload --port 8000
```

Backend addresses:
- API: `http://localhost:8000`
- FastAPI docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

### 2. Optional: run the frontend UI

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server:
- UI: `http://localhost:5173`

### 3. Instrument your code

```python
import asyncio

from agent_debugger_sdk import TraceContext, init

init()


async def my_agent() -> None:
    async with TraceContext(agent_name="my_agent", framework="custom") as ctx:
        await ctx.record_decision(
            reasoning="The user asked for weather data",
            confidence=0.85,
            chosen_action="call_weather_tool",
            evidence=[{"source": "user_input", "content": "What's the weather?"}],
        )
        await ctx.record_tool_call("weather_api", {"location": "Seattle"})
        await ctx.record_tool_result(
            "weather_api",
            result={"forecast": "rain"},
            duration_ms=100,
        )


asyncio.run(my_agent())
```

More integration paths:

- [Integration guide](./docs/integration.md)
- [SDK package readme](./SDK_README.md)

## Use Cases

- **LangChain agent loops the wrong tool** — inspect the decision tree to see exactly which reasoning step triggered the bad tool selection
- **PydanticAI workflow fails silently** — replay the session step-by-step from the last checkpoint before failure
- **CrewAI task handoffs go wrong** — search events across agents to find where context was lost
- **Prompt iteration** — compare LLM request/response pairs across multiple runs to measure improvement

## Main API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Get session details |
| `GET` | `/api/sessions/{id}/traces` | Session event list |
| `GET` | `/api/sessions/{id}/trace` | Normalized trace bundle |
| `GET` | `/api/sessions/{id}/tree` | Decision tree |
| `GET` | `/api/sessions/{id}/checkpoints` | Checkpoints |
| `GET` | `/api/sessions/{id}/analysis` | Adaptive trace analysis |
| `GET` | `/api/sessions/{id}/live` | Live summary |
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
# Clone and install for development
git clone https://github.com/acailic/agent_debugger
cd agent_debugger
pip install -e ".[server]"  # or: pip install peaky-peek-server

# Run tests
python -m pytest -q

# Build frontend
cd frontend && npm install && npm run build

# Seed demo data
python scripts/seed_demo_sessions.py
```

## Current Shape

- The local debugger path is working end to end.
- The SDK core, API, storage, replay surface, and frontend debugger are usable now.
- Cloud-oriented auth, privacy, and tenant isolation work exists in the repo but is still incomplete.
- PydanticAI and LangChain integration points exist, but finished zero-code auto-instrumentation is not the current story.

## Documentation

- [Docs start page](./docs/README.md)
- [Intro](./docs/intro.md)
- [Integration](./docs/integration.md)
- [Architecture overview](./ARCHITECTURE.md)
- [Progress tracker](./docs/progress.md)

## Research

This tool draws on recent work in neural debugging, replay mechanisms, evidence-grounded reasoning, and agentic safety:

- [Towards a Neural Debugger for Python](https://arxiv.org/abs/2603.09951v1)
- [MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning](https://arxiv.org/abs/2603.09892v1)
- [Learning When to Act or Refuse](https://arxiv.org/abs/2603.03205v1) — safe tool use and refusal-aware agent traces
- [Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts](https://arxiv.org/abs/2603.09890v1)

## License

MIT
