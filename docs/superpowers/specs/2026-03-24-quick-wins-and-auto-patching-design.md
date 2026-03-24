# Quick Wins Completion + Auto-Patching Design

> **Spec for:** Finishing the quick wins (bundled UI, JSON export, getting started guide) and building zero-instrumentation auto-patching for all major AI frameworks
>
> **Based on:** [Agent Debugger Improvement Proposal](../Agent_Debugger_Improvement_Proposal.docx)
> **Date:** 2026-03-24

---

## Overview

Two parallel tracks in one worktree:

| Track | Scope | Estimated Effort |
|-------|-------|-----------------|
| A: Quick Wins | Bundled UI, JSON export, Getting Started guide | 1–2 days |
| B: Auto-Patching | Provider registry + 7 framework adapters | 2–3 weeks |

**Already shipped from quick wins:** `peaky-peek` CLI, pricing module + cost auto-calculation.

---

## Track A: Quick Wins Completion

### A1. Bundled UI

Build the React frontend once in CI, include `dist/` in the pip wheel, serve from FastAPI. Python developers get a true "pip install and go" experience with no Node.js required at runtime.

**Files changed:**

| File | Change |
|------|--------|
| `frontend/vite.config.ts` | Add `base: "/ui/"` |
| `pyproject-server.toml` | Add `artifacts = ["frontend/dist"]` to wheel targets |
| `api/main.py` | Mount `/ui` static files; redirect root to `/ui` if dist exists |

**Behavior:** The static mount activates only when `frontend/dist/` exists. Development mode (`npm run dev`) is unaffected. Root `/` redirects to `/ui/index.html` when bundled, otherwise returns API info.

### A2. JSON Export Endpoint

```
GET /api/sessions/{session_id}/export
```

Returns all session data as a single portable JSON document.

**Response shape:**
```json
{
  "export_version": "1.0",
  "exported_at": "<ISO timestamp>",
  "session": { ... },
  "events": [ ... ],
  "checkpoints": [ ... ]
}
```

Added to existing session routes (~15 lines). Follows existing `repo.get_events()` / `repo.get_checkpoints()` patterns exactly.

### A3. Getting Started Guide

New file: `docs/getting-started.md` — a 5-minute tutorial covering install → start → first trace → explore UI → export. README updated with a prominent link.

---

## Track B: Auto-Patching

### Activation

```bash
# All supported frameworks
PEAKY_PEEK_AUTO_PATCH=all python agent.py

# Specific frameworks
PEAKY_PEEK_AUTO_PATCH=openai,anthropic python agent.py
```

| Env Var | Default | Purpose |
|---------|---------|---------|
| `PEAKY_PEEK_AUTO_PATCH` | unset | `all` or comma-separated adapter names |
| `PEAKY_PEEK_SERVER_URL` | `http://localhost:8000` | Target server for events |
| `PEAKY_PEEK_CAPTURE_CONTENT` | `false` | Opt-in: include prompt/response text |

Requires a running `peaky-peek` server. Fails gracefully (warn once, drop events silently) if server is unreachable.

### Module Structure

```
agent_debugger_sdk/
  auto_patch/
    __init__.py        # env var activation + registry wiring
    registry.py        # BaseAdapter ABC + PatchRegistry
    _transport.py      # non-blocking HTTP client for event delivery
    adapters/
      openai_adapter.py
      anthropic_adapter.py
      langchain_adapter.py
      pydanticai_adapter.py
      crewai_adapter.py
      autogen_adapter.py
      llamaindex_adapter.py
```

### Base Adapter Contract

```python
class BaseAdapter(ABC):
    name: str  # e.g. "openai"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the target library is installed."""

    @abstractmethod
    def patch(self, config: PatchConfig) -> None:
        """Wrap SDK methods, store originals for unpatch."""

    @abstractmethod
    def unpatch(self) -> None:
        """Restore all original SDK methods."""
```

`PatchRegistry` discovers adapters, applies matching ones on activation, and tracks patched state for safe unpatch.

### Adapter Tiers

**Tier 1 — Direct SDK wrapping (new):** `openai_adapter`, `anthropic_adapter`

Wrap `client.chat.completions.create` and its async variant. Tool calls are detected structurally:
- OpenAI: `response.choices[0].finish_reason == "tool_calls"` → read `message.tool_calls`
- Anthropic: `response.stop_reason == "tool_use"` → filter `content` for `ToolUseBlock`

Both normalized to:
```python
{"id": "call_xyz", "tool_name": "name", "arguments": {...}}
```

**Tier 2 — Existing hook system wiring (upgrade):** `langchain_adapter`, `pydanticai_adapter`

The manual `LangChainAdapter` and `PydanticAIAdapter` already exist. Auto-patching registers them automatically instead of requiring developer opt-in. No new patching logic.

**Tier 3 — Top-level method wrapping (new):** `crewai_adapter`, `autogen_adapter`, `llamaindex_adapter`

Wrap `Crew.kickoff()`, `AgentChat.run()`, `QueryEngine.query()` etc. Captures session/span context at the orchestration level. LLM calls inside are captured by Tier 1 adapters.

### Data Flow

```
PEAKY_PEEK_AUTO_PATCH=all python agent.py
  ↓
auto_patch/__init__.py reads env var, iterates PatchRegistry
  ↓
Each adapter: is_available()? → skip silently if not installed
  ↓
patch() wraps SDK methods in-place
  ↓
agent.py calls openai.chat.completions.create(...)
  ↓
Adapter wrapper:
  1. Emit LLMRequestEvent → async HTTP POST (non-blocking)
  2. Call original SDK
  3. Parse response, detect tool_calls structurally
  4. Emit LLMResponseEvent + ToolCallEvent per tool call
  ↓
Events visible in UI immediately
```

### What Gets Captured

| Event | Always | Opt-in (CAPTURE_CONTENT=true) |
|-------|--------|-------------------------------|
| `LLMRequestEvent` | model, tool names/schemas | prompt messages text |
| `LLMResponseEvent` | tokens, cost, latency, stop_reason, tool call IDs | response content text |
| `ToolCallEvent` | tool_name, arguments dict, call_id | — |

**Never captured:** API keys, internal SDK state.

### Session Lifecycle

First intercepted call auto-creates a session named after `sys.argv[0]`. No explicit end signal — server marks sessions complete on inactivity timeout.

### Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| Library not installed | Silent skip |
| Server unreachable | Warn once on startup, drop events silently |
| SDK version incompatible | Log warning, skip adapter |
| Exception in wrapper | Log warning, call original — never crash user's agent |

### Testing Strategy

Each adapter has its own test file. Tests mock the SDK, verify events emitted — no real API calls needed.

```python
# Example: openai_adapter test
with mock.patch("openai.OpenAI") as mock_client:
    mock_client.chat.completions.create.return_value = fake_response_with_tool_calls
    # Activate patch, call SDK, assert LLMResponseEvent + ToolCallEvent emitted
```

Integration test: verify `PEAKY_PEEK_AUTO_PATCH=all` loads all available adapters and skips unavailable ones gracefully.

**Extending:** Adding a new framework = one new file implementing `BaseAdapter`. No changes to `__init__.py` or `registry.py` needed.

---

## Files Changed Summary

### Track A

| File | Action |
|------|--------|
| `frontend/vite.config.ts` | Modify — set `base: "/ui/"` |
| `pyproject-server.toml` | Modify — add frontend/dist artifacts |
| `api/main.py` | Modify — static mount, root redirect, export endpoint |
| `docs/getting-started.md` | Create — 5-min tutorial |
| `README.md` | Modify — link to getting started guide |

### Track B

| File | Action |
|------|--------|
| `agent_debugger_sdk/auto_patch/__init__.py` | Create |
| `agent_debugger_sdk/auto_patch/registry.py` | Create |
| `agent_debugger_sdk/auto_patch/_transport.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/openai_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/anthropic_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/langchain_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/pydanticai_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/crewai_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/autogen_adapter.py` | Create |
| `agent_debugger_sdk/auto_patch/adapters/llamaindex_adapter.py` | Create |
| `tests/auto_patch/test_registry.py` | Create |
| `tests/auto_patch/test_openai_adapter.py` | Create |
| `tests/auto_patch/test_anthropic_adapter.py` | Create |
| `tests/auto_patch/test_langchain_adapter.py` | Create |
| *(+ remaining adapter tests)* | Create |
