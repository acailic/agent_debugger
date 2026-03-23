# Quick Wins Design: One-Line Setup Experience

> **Spec for:** Making Peaky Peek the "pip install and go" choice for AI agent debugging
>
> **Based on:** [Agent Debugger Improvement Proposal](../Agent_Debugger_Improvement_Proposal.docx)

## Overview

Transform `peaky-peek-server` into a zero-friction debugging experience with 5 quick wins:

| Feature | Impact |
|---------|--------|
| **CLI command** | `peaky-peek` starts everything with one command |
| **Bundled UI** | No separate `npm install` — frontend included in pip package |
| **Cost estimation** | Automatic token-based cost calculation |
| **JSON export** | Portable session data via single endpoint |
| **Getting Started guide** | 5-minute tutorial for new users |

**Estimated effort:** 1-2 weeks

**Package changes:**
- `pyproject-server.toml` — Add CLI entry point, include frontend assets
- `agent_debugger_sdk/pricing.py` — New module with model pricing data
- `agent_debugger_sdk/core/events.py` — Add auto-calculation of `cost_usd` (field exists)
- `api/main.py` — Add static file serving and export endpoint
- `cli.py` — New CLI entry point
- `docs/getting-started.md` — New tutorial

**No breaking changes** to existing SDK or server API.

---

## 1. CLI Command (`peaky-peek`)

### Command Interface

```bash
# Start server (default behavior)
peaky-peek

# Start with options
peaky-peek --port 8080 --host 0.0.0.0

# Start and open browser
peaky-peek --open

# Show help
peaky-peek --help

# Show version
peaky-peek --version
```

### Behavior

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Host to bind |
| `--port` | `8000` | Port to bind |
| `--open` | `false` | Open browser after starting |
| `--version` | — | Print version and exit |
| `--help` | — | Show usage |

### Implementation

**New file:** `cli.py` at project root

```python
"""CLI entry point for peaky-peek-server."""
import argparse
import importlib.metadata
import webbrowser

import uvicorn


def main() -> None:
    # Get version from package metadata (avoids hardcoding)
    version = importlib.metadata.version("peaky-peek-server")

    parser = argparse.ArgumentParser(
        prog="peaky-peek",
        description="Debug AI agents with time-travel replay and decision trees",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--open", action="store_true", help="Open browser after starting")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version}")

    args = parser.parse_args()

    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}")

    uvicorn.run("api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

**Entry point in `pyproject-server.toml`:**

```toml
[project.scripts]
peaky-peek = "cli:main"
```

---

## 2. Bundled UI

### Strategy

Build the React frontend once during packaging, include `dist/` in the wheel, serve from FastAPI.

### Implementation

**1. Build step (CI/release):**

```bash
cd frontend && npm install && npm run build
# Creates frontend/dist/
```

**2. Include assets in `pyproject-server.toml`:**

```toml
[tool.hatch.build.targets.wheel]
packages = ["agent_debugger_sdk", "api", "auth", "collector", "redaction", "storage"]
artifacts = ["frontend/dist"]
```

**3. Serve from FastAPI in `api/main.py`:**

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DIST_PATH = Path(__file__).parent.parent / "frontend" / "dist"

if DIST_PATH.exists():
    app.mount("/ui", StaticFiles(directory=DIST_PATH, html=True), name="ui")

@app.get("/")
async def root():
    """Redirect root to UI if available, otherwise API docs."""
    if DIST_PATH.exists():
        return FileResponse(DIST_PATH / "index.html")
    return {"message": "Agent Debugger API", "docs": "/docs"}
```

**4. Vite config adjustment in `frontend/vite.config.ts`:**

```typescript
export default defineConfig({
  base: "/ui/",
  // ... rest of config
})
```

### User Experience

| Step | Command/URL |
|------|-------------|
| Install | `pip install peaky-peek-server` |
| Start | `peaky-peek` |
| Access UI | `http://localhost:8000` (redirects to `/ui`) |

### Dev Mode

For development, continue using `npm run dev` in frontend directory. The FastAPI static mount only activates when `frontend/dist/` exists.

---

## 3. Cost Estimation

### Strategy

Add a `pricing.py` module with hardcoded model prices. Calculate costs when `LLMResponseEvent` is recorded.

### Pricing Data

**New file:** `agent_debugger_sdk/pricing.py`

```python
"""Model pricing data for cost estimation.

Prices are per 1M tokens in USD as of March 2026.
Update this file when model pricing changes.
"""

from dataclasses import dataclass


@dataclass
class ModelPricing:
    input_cost: float  # $ per 1M input tokens
    output_cost: float  # $ per 1M output tokens


# Pricing data - update periodically
PRICING_TABLE: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(2.50, 10.00),
    "gpt-4o-mini": ModelPricing(0.15, 0.60),
    "gpt-4-turbo": ModelPricing(10.00, 30.00),
    "gpt-4": ModelPricing(30.00, 60.00),
    "gpt-3.5-turbo": ModelPricing(0.50, 1.50),
    # Anthropic
    "claude-opus-4-6": ModelPricing(15.00, 75.00),
    "claude-sonnet-4-6": ModelPricing(3.00, 15.00),
    "claude-haiku-4-5": ModelPricing(0.80, 4.00),
    "claude-3-5-sonnet": ModelPricing(3.00, 15.00),
    "claude-3-haiku": ModelPricing(0.25, 1.25),
    # Google
    "gemini-2.0-flash": ModelPricing(0.10, 0.40),
    "gemini-1.5-pro": ModelPricing(1.25, 5.00),
}

# Aliases for common shorthand
MODEL_ALIASES: dict[str, str] = {
    "gpt-4": "gpt-4-turbo",
    "claude-3-sonnet": "claude-3-5-sonnet",
}


def get_pricing(model: str) -> ModelPricing | None:
    """Get pricing for a model, resolving aliases."""
    model = MODEL_ALIASES.get(model, model)
    return PRICING_TABLE.get(model)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Calculate cost in USD for a request.

    Args:
        model: Model identifier (e.g., "gpt-4o")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Cost in USD, or None if model not in pricing table
    """
    pricing = get_pricing(model)
    if pricing is None:
        return None

    input_cost = (input_tokens / 1_000_000) * pricing.input_cost
    output_cost = (output_tokens / 1_000_000) * pricing.output_cost
    return round(input_cost + output_cost, 6)
```

### Integration with LLMResponseEvent

**Note:** The `cost_usd` field already exists in `LLMResponseEvent`. This spec adds automatic calculation.

**Modify:** `agent_debugger_sdk/core/events.py` — Add auto-calculation in `__post_init__` or factory method

```python
from agent_debugger_sdk.pricing import calculate_cost

@dataclass
class LLMResponseEvent(BaseEvent):
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float = 0.0  # Already exists
    # ... existing fields

    def __post_init__(self):
        # Auto-calculate cost if not explicitly set and tokens available
        if self.cost_usd == 0.0 and self.input_tokens and self.output_tokens:
            calculated = calculate_cost(self.model, self.input_tokens, self.output_tokens)
            if calculated is not None:
                self.cost_usd = calculated
```

### UI Display

- Session summary: Total cost across all events
- Per-event detail: Individual request cost
- Unknown models: Display `--` (no cost calculated)

### Maintenance

Update `PRICING_TABLE` when model pricing changes. This is a manual process — add a comment noting the last update date.

---

## 4. JSON Export Endpoint

### Endpoint

```
GET /api/sessions/{session_id}/export
```

### Response Format

```json
{
  "export_version": "1.0",
  "exported_at": "2026-03-23T10:30:00Z",
  "session": {
    "id": "abc-123",
    "agent_name": "weather_agent",
    "framework": "langchain",
    "status": "completed",
    "created_at": "2026-03-23T10:00:00Z",
    "total_tokens": 1542,
    "total_cost_usd": 0.00231
  },
  "events": [
    {
      "id": "evt-1",
      "type": "decision",
      "timestamp": "2026-03-23T10:00:01Z",
      "data": {}
    }
  ],
  "checkpoints": [
    {
      "id": "cp-1",
      "event_id": "evt-5",
      "state_summary": "After tool call",
      "created_at": "2026-03-23T10:00:05Z"
    }
  ]
}
```

### Implementation

Add to `api/session_routes.py` (follows existing route patterns):

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from api.services import require_session
from storage.repository import TraceRepository

@router.get("/api/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Export session as portable JSON."""
    session = await require_session(repo, session_id)
    events = await repo.get_events(session_id)
    checkpoints = await repo.get_checkpoints(session_id)

    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": session.model_dump(),
        "events": [e.model_dump() for e in events],
        "checkpoints": [c.model_dump() for c in checkpoints],
    }
```

### Usage

```bash
# Export via curl
curl http://localhost:8000/api/sessions/abc-123/export > session.json

# Pretty print
curl http://localhost:8000/api/sessions/abc-123/export | jq .
```

---

## 5. Getting Started Guide

### File Location

```
docs/getting-started.md  # NEW
```

### Content

```markdown
# Getting Started with Peaky Peek

Debug AI agents with time-travel replay, decision trees, and cost tracking. This guide takes about 5 minutes.

## 1. Install (30 seconds)

pip install peaky-peek-server

## 2. Start the Debugger (10 seconds)

peaky-peek --open

This starts the server at http://localhost:8000 and opens your browser.

## 3. Your First Trace (2 minutes)

Create demo.py:

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

Run it:

python demo.py

Refresh your browser -- you'll see your first trace.

## 4. Explore the UI (2 minutes)

- Timeline: Click events to inspect details
- Decision Tree: Visualize reasoning chains
- Cost: See token usage and estimated costs

## 5. Export Your Data (30 seconds)

curl http://localhost:8000/api/sessions/<session-id>/export | jq . > trace.json

## Next Steps

- Framework Integrations: LangChain, PydanticAI, CrewAI
- Architecture: How it works under the hood
- Examples: More code samples
```

### README Update

Add prominent link in main README:

```markdown
## Quick Start

**New to Peaky Peek?** See the [5-Minute Getting Started Guide](./docs/getting-started.md).

### Option A: pip (recommended)
...
```

---

## Implementation Order

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| **1. CLI** | Create `cli.py`, add entry point to `pyproject-server.toml` | 2-3 hours |
| **2. Bundled UI** | Update vite config, add static mount, update build config | 3-4 hours |
| **3. Cost estimation** | Create `pricing.py`, update events, integrate | 2-3 hours |
| **4. JSON export** | Add endpoint to `api/main.py` | 1-2 hours |
| **5. Getting Started** | Write guide, update README | 1-2 hours |
| **6. Testing** | Test end-to-end flow, update CI | 2-3 hours |

**Total:** ~12-17 hours (1.5-2 days)

---

## Files Changed Summary

| File | Action | Changes |
|------|--------|---------|
| `cli.py` | CREATE | CLI entry point |
| `pyproject-server.toml` | MODIFY | Add `[project.scripts]`, add artifacts |
| `agent_debugger_sdk/pricing.py` | CREATE | Pricing data and calculation |
| `agent_debugger_sdk/core/events.py` | MODIFY | Add `cost_usd` field |
| `api/main.py` | MODIFY | Static mount, root redirect, export endpoint |
| `frontend/vite.config.ts` | MODIFY | Set `base: "/ui/"` |
| `docs/getting-started.md` | CREATE | Tutorial |
| `README.md` | MODIFY | Link to getting started guide |
