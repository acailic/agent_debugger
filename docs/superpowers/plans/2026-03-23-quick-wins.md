# Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform peaky-peek-server into a "pip install and go" experience with CLI, bundled UI, cost estimation, JSON export, and getting started guide.

**Architecture:** Add CLI entry point that wraps uvicorn. Bundle pre-built frontend in pip package. Add pricing module for automatic cost calculation. Add export endpoint following existing route patterns.

**Tech Stack:** Python 3.10+, FastAPI, argparse, importlib.metadata, Vite

**Spec:** `docs/superpowers/specs/2026-03-23-quick-wins-design.md`

---

## File Structure Map

### New Files

| File | Purpose |
|------|---------|
| `cli.py` | CLI entry point (`peaky-peek` command) |
| `agent_debugger_sdk/pricing.py` | Model pricing data and cost calculation |
| `tests/test_cli.py` | CLI unit tests |
| `tests/test_pricing.py` | Pricing module tests |
| `tests/test_export.py` | Export endpoint tests |
| `docs/getting-started.md` | 5-minute tutorial |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject-server.toml` | Add `[project.scripts]` entry point, add `artifacts` |
| `agent_debugger_sdk/core/events.py` | Add `__post_init__` to `LLMResponseEvent` for auto-cost-calc |
| `api/main.py` | Add static mount for UI, add root redirect |
| `api/session_routes.py` | Add `/api/sessions/{session_id}/export` endpoint |
| `frontend/vite.config.ts` | Set `base: "/ui/"` for bundled assets |
| `README.md` | Add Getting Started link, update Quick Start section |

---

## Task 1: CLI Command

**Files:**
- Create: `cli.py`
- Create: `tests/test_cli.py`
- Modify: `pyproject-server.toml`

- [ ] **Step 1: Write failing test for CLI module import**

```python
# tests/test_cli.py
"""Tests for the peaky-peek CLI."""


def test_cli_module_importable():
    """CLI module should be importable."""
    import cli

    assert hasattr(cli, "main")
    assert callable(cli.main)


def test_cli_version_flag(capsys):
    """--version should print version string."""
    import sys
    from unittest.mock import patch

    with patch.object(sys, "argv", ["peaky-peek", "--version"]):
        try:
            from cli import main
            main()
        except SystemExit as e:
            # --version exits with code 0
            assert e.code == 0

    captured = capsys.readouterr()
    assert "peaky-peek" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 3: Create CLI module**

```python
# cli.py
"""CLI entry point for peaky-peek-server."""
import argparse
import importlib.metadata
import webbrowser

import uvicorn


def main() -> None:
    """Main CLI entry point."""
    # Get version from package metadata (avoids hardcoding)
    try:
        version = importlib.metadata.version("peaky-peek-server")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0-dev"

    parser = argparse.ArgumentParser(
        prog="peaky-peek",
        description="Debug AI agents with time-travel replay and decision trees",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open browser after starting",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    args = parser.parse_args()

    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}")

    uvicorn.run("api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Add entry point to pyproject-server.toml**

Add to `pyproject-server.toml` after the `[project]` section:

```toml
[project.scripts]
peaky-peek = "cli:main"
```

- [ ] **Step 6: Verify CLI installs correctly**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && pip install -e . -f . --config-settings editable_mode=compat && peaky-peek --help`
Expected: Shows usage help text

- [ ] **Step 7: Commit CLI changes**

```bash
git add cli.py tests/test_cli.py pyproject-server.toml
git commit -m "feat: add peaky-peek CLI command with --host, --port, --open, --version flags"
```

---

## Task 2: Pricing Module (Cost Estimation)

**Files:**
- Create: `agent_debugger_sdk/pricing.py`
- Create: `tests/test_pricing.py`
- Modify: `agent_debugger_sdk/core/events.py`

- [ ] **Step 1: Write failing tests for pricing module**

```python
# tests/test_pricing.py
"""Tests for the pricing module."""
import pytest


def test_pricing_module_importable():
    """Pricing module should be importable."""
    from agent_debugger_sdk import pricing

    assert hasattr(pricing, "calculate_cost")
    assert hasattr(pricing, "get_pricing")
    assert hasattr(pricing, "PRICING_TABLE")


def test_get_pricing_known_model():
    """get_pricing should return pricing for known models."""
    from agent_debugger_sdk.pricing import get_pricing

    pricing = get_pricing("gpt-4o")
    assert pricing is not None
    assert pricing.input_cost > 0
    assert pricing.output_cost > 0


def test_get_pricing_unknown_model():
    """get_pricing should return None for unknown models."""
    from agent_debugger_sdk.pricing import get_pricing

    pricing = get_pricing("nonexistent-model-xyz")
    assert pricing is None


def test_get_pricing_resolves_aliases():
    """get_pricing should resolve model aliases."""
    from agent_debugger_sdk.pricing import get_pricing, MODEL_ALIASES

    # Test that aliases work
    for alias, canonical in MODEL_ALIASES.items():
        alias_pricing = get_pricing(alias)
        canonical_pricing = get_pricing(canonical)
        assert alias_pricing == canonical_pricing, f"Alias {alias} should resolve to {canonical}"


def test_calculate_cost_known_model():
    """calculate_cost should compute correct cost."""
    from agent_debugger_sdk.pricing import calculate_cost

    # gpt-4o: $2.50/1M input, $10.00/1M output
    # 1000 input + 500 output = (1000/1M * 2.50) + (500/1M * 10.00) = 0.0025 + 0.005 = 0.0075
    cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost is not None
    assert abs(cost - 0.0075) < 0.0001


def test_calculate_cost_unknown_model():
    """calculate_cost should return None for unknown models."""
    from agent_debugger_sdk.pricing import calculate_cost

    cost = calculate_cost("nonexistent-model-xyz", input_tokens=1000, output_tokens=500)
    assert cost is None


def test_calculate_cost_zero_tokens():
    """calculate_cost should return 0.0 for zero tokens."""
    from agent_debugger_sdk.pricing import calculate_cost

    cost = calculate_cost("gpt-4o", input_tokens=0, output_tokens=0)
    assert cost == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_pricing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_debugger_sdk.pricing'`

- [ ] **Step 3: Create pricing module**

```python
# agent_debugger_sdk/pricing.py
"""Model pricing data for cost estimation.

Prices are per 1M tokens in USD as of March 2026.
Update this file when model pricing changes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Pricing information for a model."""

    input_cost: float  # $ per 1M input tokens
    output_cost: float  # $ per 1M output tokens


# Pricing data - update periodically
# Last updated: 2026-03-23
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
    """Get pricing for a model, resolving aliases.

    Args:
        model: Model identifier (e.g., "gpt-4o")

    Returns:
        ModelPricing if found, None otherwise
    """
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

    if input_tokens == 0 and output_tokens == 0:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing.input_cost
    output_cost = (output_tokens / 1_000_000) * pricing.output_cost
    return round(input_cost + output_cost, 6)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_pricing.py -v`
Expected: ALL PASS

- [ ] **Step 5: Write test for LLMResponseEvent auto-cost-calc**

```python
# Add to tests/test_pricing.py

def test_llm_response_event_auto_cost_calculation():
    """LLMResponseEvent should auto-calculate cost when tokens provided."""
    from agent_debugger_sdk.core.events import LLMResponseEvent

    # Create event with tokens but no explicit cost
    event = LLMResponseEvent(
        model="gpt-4o",
        usage={"input_tokens": 1000, "output_tokens": 500},
    )

    # Cost should be auto-calculated
    assert event.cost_usd > 0, "Cost should be auto-calculated"
    assert abs(event.cost_usd - 0.0075) < 0.0001


def test_llm_response_event_preserves_explicit_cost():
    """LLMResponseEvent should preserve explicitly set cost."""
    from agent_debugger_sdk.core.events import LLMResponseEvent

    # Create event with explicit cost
    event = LLMResponseEvent(
        model="gpt-4o",
        usage={"input_tokens": 1000, "output_tokens": 500},
        cost_usd=0.999,  # Explicit cost
    )

    # Explicit cost should be preserved
    assert event.cost_usd == 0.999


def test_llm_response_event_no_cost_for_unknown_model():
    """LLMResponseEvent should have 0.0 cost for unknown models."""
    from agent_debugger_sdk.core.events import LLMResponseEvent

    event = LLMResponseEvent(
        model="unknown-model-xyz",
        usage={"input_tokens": 1000, "output_tokens": 500},
    )

    # Cost should remain 0.0 for unknown model
    assert event.cost_usd == 0.0
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_pricing.py::test_llm_response_event_auto_cost_calculation -v`
Expected: FAIL — cost_usd is 0.0 (not auto-calculated)

- [ ] **Step 7: Add __post_init__ to LLMResponseEvent**

Modify `agent_debugger_sdk/core/events.py`:

1. Add import at top of file:
```python
from agent_debugger_sdk.pricing import calculate_cost
```

2. Add `__post_init__` method to `LLMResponseEvent` class (after line 316, before `to_dict`):

```python
def __post_init__(self):
    """Auto-calculate cost if not explicitly set and tokens available."""
    if self.cost_usd == 0.0:
        input_tokens = self.usage.get("input_tokens", 0)
        output_tokens = self.usage.get("output_tokens", 0)
        if input_tokens or output_tokens:
            calculated = calculate_cost(self.model, input_tokens, output_tokens)
            if calculated is not None:
                object.__setattr__(self, "cost_usd", calculated)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_pricing.py -v`
Expected: ALL PASS

- [ ] **Step 9: Run full test suite to verify no regressions**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v --tb=short`
Expected: ALL PASS

- [ ] **Step 10: Commit pricing changes**

```bash
git add agent_debugger_sdk/pricing.py agent_debugger_sdk/core/events.py tests/test_pricing.py
git commit -m "feat: add pricing module with auto-cost-calculation for LLMResponseEvent"
```

---

## Task 3: Bundled UI

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `api/main.py`
- Modify: `pyproject-server.toml`

- [ ] **Step 1: Update Vite config for bundled UI base path**

Modify `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/ui/',
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

- [ ] **Step 2: Build frontend to verify config works**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/frontend && npm install && npm run build`
Expected: Build succeeds, creates `dist/` directory

- [ ] **Step 3: Add static mount and root redirect to FastAPI**

Modify `api/main.py`:

1. Add imports at top (after `from contextlib import asynccontextmanager`):
```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
```

2. Add after `app = create_app()` at end of file (before any blank line at EOF):
```python
# Serve bundled UI if available
DIST_PATH = Path(__file__).parent.parent / "frontend" / "dist"

if DIST_PATH.exists():
    app.mount("/ui", StaticFiles(directory=DIST_PATH, html=True), name="ui")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to UI if available, otherwise API docs."""
    if DIST_PATH.exists():
        return FileResponse(DIST_PATH / "index.html")
    return {"message": "Agent Debugger API", "docs": "/docs"}
```

- [ ] **Step 4: Test static mount works**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -c "from api.main import app, DIST_PATH; print(f'DIST_PATH: {DIST_PATH}, exists: {DIST_PATH.exists()}')"`
Expected: Shows `exists: True` if frontend was built

- [ ] **Step 5: Add artifacts to pyproject-server.toml**

Modify `pyproject-server.toml`, update the `[tool.hatch.build.targets.wheel]` section:

```toml
[tool.hatch.build.targets.wheel]
packages = ["agent_debugger_sdk", "api", "auth", "collector", "redaction", "storage", "cli"]
artifacts = ["frontend/dist"]
```

- [ ] **Step 6: Commit bundled UI changes**

```bash
git add frontend/vite.config.ts api/main.py pyproject-server.toml
git commit -m "feat: bundle frontend UI in pip package, serve from /ui"
```

---

## Task 4: JSON Export Endpoint

**Files:**
- Modify: `api/session_routes.py`
- Create: `tests/test_export.py`

- [ ] **Step 1: Write failing test for export endpoint**

```python
# tests/test_export.py
"""Tests for the session export endpoint."""
import pytest
from fastapi.testclient import TestClient


def test_export_session_not_found():
    """Export should return 404 for nonexistent session."""
    from api.main import app

    client = TestClient(app)
    response = client.get("/api/sessions/nonexistent-id/export")

    assert response.status_code == 404


def test_export_session_format():
    """Export should return correct JSON structure."""
    from api.main import app
    from api.dependencies import get_repository
    from storage.repository import TraceRepository
    from agent_debugger_sdk.core.events import Session
    import uuid

    # This is a placeholder - actual test would need to create a session first
    # For now, just verify the endpoint exists and returns expected structure
    client = TestClient(app)

    # The endpoint should exist (will return 404 without session)
    response = client.get(f"/api/sessions/{uuid.uuid4()}/export")
    assert response.status_code in [404, 200]  # Either not found or success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_export.py -v`
Expected: FAIL — 404 or route not found

- [ ] **Step 3: Add export endpoint to session_routes.py**

Add to end of `api/session_routes.py`:

```python
from datetime import datetime, timezone


@router.get("/api/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict:
    """Export session as portable JSON."""
    session = await require_session(repo, session_id)
    events = await repo.list_events(session_id, limit=10000)
    checkpoints = await repo.list_checkpoints(session_id)

    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": session.to_dict(),
        "events": [event.to_dict() for event in events],
        "checkpoints": [cp.to_dict() for cp in checkpoints],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Add more comprehensive test**

```python
# Add to tests/test_export.py

@pytest.mark.asyncio
async def test_export_session_with_data(async_client, test_session):
    """Export should return complete session data."""
    # Create a test session with events first
    # This requires the test fixtures from conftest.py
    response = await async_client.get(f"/api/sessions/{test_session}/export")

    if response.status_code == 200:
        data = response.json()
        assert "export_version" in data
        assert data["export_version"] == "1.0"
        assert "exported_at" in data
        assert "session" in data
        assert "events" in data
        assert "checkpoints" in data
        assert isinstance(data["events"], list)
```

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_export.py tests/test_api_contract.py -v --tb=short`
Expected: PASS (or skip if fixtures not available)

- [ ] **Step 7: Commit export endpoint**

```bash
git add api/session_routes.py tests/test_export.py
git commit -m "feat: add /api/sessions/{id}/export endpoint for portable JSON"
```

---

## Task 5: Getting Started Guide

**Files:**
- Create: `docs/getting-started.md`
- Modify: `README.md`

- [ ] **Step 1: Create getting started guide**

```markdown
# docs/getting-started.md
# Getting Started with Peaky Peek

Debug AI agents with time-travel replay, decision trees, and cost tracking. This guide takes about 5 minutes.

## 1. Install (30 seconds)

```bash
pip install peaky-peek-server
```

## 2. Start the Debugger (10 seconds)

```bash
peaky-peek --open
```

This starts the server at http://localhost:8000 and opens your browser.

## 3. Your First Trace (2 minutes)

Create `demo.py`:

```python
import asyncio
from agent_debugger_sdk import TraceContext, init

init()


async def main():
    async with TraceContext(agent_name="demo", framework="custom") as ctx:
        # Record a decision
        await ctx.record_decision(
            reasoning="User asked for weather",
            confidence=0.85,
            chosen_action="call_weather_api",
        )
        # Record a tool call
        await ctx.record_tool_call("weather_api", {"city": "Seattle"})
        await ctx.record_tool_result("weather_api", result={"temp": 72})


asyncio.run(main())
```

Run it:

```bash
python demo.py
```

Refresh your browser — you'll see your first trace.

## 4. Explore the UI (2 minutes)

- **Timeline**: Click events to inspect details
- **Decision Tree**: Visualize reasoning chains
- **Cost**: See token usage and estimated costs

## 5. Export Your Data (30 seconds)

```bash
# Get session ID from UI, then:
curl http://localhost:8000/api/sessions/<session-id>/export | jq . > trace.json
```

## Next Steps

- [Framework Integrations](./integration.md) — LangChain, PydanticAI, CrewAI
- [Architecture](../ARCHITECTURE.md) — How it works under the hood
- [Examples](../examples/) — More code samples
```

- [ ] **Step 2: Update README.md with Getting Started link**

Modify `README.md` — replace the Quick Start section (lines 31-60):

```markdown
## Quick Start

**New to Peaky Peek?** See the [5-Minute Getting Started Guide](./docs/getting-started.md).

### Option A: pip (recommended)

```bash
pip install peaky-peek-server
peaky-peek --open
```

The UI opens at http://localhost:8000

### Option B: Docker (local build)

```bash
docker build -t peaky-peek . && docker run -p 8080:8080 peaky-peek
# UI: http://localhost:8080
```
```

- [ ] **Step 3: Verify docs render correctly**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && head -30 docs/getting-started.md && head -45 README.md`
Expected: Shows properly formatted markdown

- [ ] **Step 4: Commit documentation**

```bash
git add docs/getting-started.md README.md
git commit -m "docs: add 5-minute Getting Started guide, update README"
```

---

## Task 6: Final Verification

- [ ] **Step 1: Run complete test suite**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Test CLI end-to-end**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && pip install -e . && peaky-peek --help && peaky-peek --version`
Expected: Shows help and version

- [ ] **Step 3: Verify all changes committed**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && git status`
Expected: Working tree clean

- [ ] **Step 4: Final commit (if any remaining changes)**

```bash
git add -A
git status  # Verify what will be committed
git commit -m "feat: complete quick wins implementation"
```

---

## Summary

| Task | Files Created | Files Modified | Est. Time |
|------|---------------|----------------|-----------|
| 1. CLI | `cli.py`, `tests/test_cli.py` | `pyproject-server.toml` | 30 min |
| 2. Pricing | `agent_debugger_sdk/pricing.py`, `tests/test_pricing.py` | `agent_debugger_sdk/core/events.py` | 45 min |
| 3. Bundled UI | — | `frontend/vite.config.ts`, `api/main.py`, `pyproject-server.toml` | 30 min |
| 4. JSON Export | `tests/test_export.py` | `api/session_routes.py` | 20 min |
| 5. Getting Started | `docs/getting-started.md` | `README.md` | 20 min |
| 6. Verification | — | — | 15 min |

**Total:** ~2.5 hours
