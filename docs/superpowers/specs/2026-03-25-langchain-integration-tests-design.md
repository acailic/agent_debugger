# LangChain Integration Tests Design

**Date:** 2026-03-25
**Status:** Approved

## Problem

The existing LangChain adapter tests (`tests/adapters/tests/test_langchain.py`) are pure unit tests — they mock LangChain's callback system and never run real LLM calls. As a LangChain user, there is no way to verify that the adapter correctly captures traces when running against a live LLM API.

## Goal

Add end-to-end integration tests that invoke real LangChain chains against the z.ai LLM endpoint and assert that Peaky Peek captures the correct trace events through both the manual handler and auto-patch modes.

## Scope

### In scope

- Basic LLM call (manual mode)
- LLM with tool calling (manual mode)
- Multi-step agent chain with multiple tools (manual mode)
- Auto-patch mode (basic LLM call) — uses transport-level interception, not `EventBuffer`
- In-memory event capture via `EventBuffer` (manual mode) and `SyncTransport` spy (auto-patch mode)

### Out of scope

- Streaming responses
- Full API + storage pipeline (in-memory/intercept only)
- CI integration (tests gated behind `ZAI_API_KEY`)
- Token cost accuracy assertions (`cost_usd` may be 0.0 for models not in the pricing table)
- Other adapter integrations

## LLM Provider

All tests use the z.ai endpoint:
- **Base URL:** `https://api.z.ai/api/coding/paas/v4`
- **Auth:** `ZAI_API_KEY` environment variable
- **Transport:** OpenAI-compatible (LangChain's `ChatOpenAI` with custom `base_url`)
- **Model:** Parametrized, defaults to a reasonable model (e.g., `gpt-4o-mini`)

## Architecture

### File structure

```
tests/integration/
    __init__.py
    conftest.py
    test_langchain_integration.py
```

### Pytest markers

Register `integration` marker in `pyproject.toml` and exclude it from default runs:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: End-to-end tests requiring API keys (deselected by default)",
]
addopts = "-ra --timeout=120 -m 'not integration'"
```

Note: `tests/integration/` is a subdirectory of `tests/` (which is already in `testpaths`), so pytest discovers it by recursion. No `testpaths` change needed.

### How to run

```bash
# All integration tests (override addopts to include them)
python3 -m pytest tests/integration/ -m integration -o "addopts="

# Normal CI (excludes integration via addopts)
python3 -m pytest
```

### Root conftest inheritance

The integration tests inherit from the root `tests/conftest.py`, which runs the `setup_test_db` session fixture. This is expected — integration tests run within the same pytest session infrastructure. No special handling needed.

## Conftest fixtures

### `integration_enabled`

- Session-scoped
- Checks `ZAI_API_KEY` is set in environment
- Skips entire module if absent
- Applied via `pytestmark = pytest.mark.integration` on the test module

### `zai_chat_model`

- Creates `ChatOpenAI` instance with:
  - `base_url="https://api.z.ai/api/coding/paas/v4"`
  - `api_key=os.environ["ZAI_API_KEY"]`
  - Configurable `model` (defaults to sensible choice)
  - Small `max_tokens` to minimize cost
  - Low `temperature` for deterministic output

### `trace_context` (per-test)

- Creates `TraceContext` with unique `session_id`, `agent_name="integration-test"`, `framework="langchain"`
- Enters context via `async with`, yields `(context, session_id)` tuple
- Exits context after test completes
- After exit, flushes events from the global `EventBuffer` for this session to prevent cross-test contamination

### `captured_events` (per-test, depends on `trace_context`)

- After test body runs, reads all events from `TraceContext`'s local `_events` list (not the global `EventBuffer`)
- Returns `list[TraceEvent]`
- Uses context-local storage to avoid cross-test contamination via the shared singleton

### `langchain_handler` (per-test, depends on `trace_context`)

- Creates `LangChainTracingHandler(session_id=context.session_id)`
- Calls `handler.set_context(context)` after `TraceContext` is entered
- Order: `trace_context.__aenter__()` → `handler.set_context(context)` → yield handler → `trace_context.__aexit__()`

## Test scenarios

### Test 1: Basic LLM call (manual mode)

1. Create `ChatOpenAI` with `callbacks=[handler]`
2. Call `await llm.ainvoke("Say hello in one word")`
3. Assert captured events contain, in order:
   - `AGENT_START` (context enter)
   - `LLM_REQUEST` with: correct model name, messages containing the prompt, settings with temperature/max_tokens
   - `LLM_RESPONSE` with: non-empty `content`, positive `duration_ms`
   - `AGENT_END` (context exit)

### Test 2: LLM with tool calling (manual mode)

1. Define a simple tool (e.g., `add_numbers(a: int, b: int) -> int`)
2. Bind tool to `ChatOpenAI`, pass `callbacks=[handler]`
3. Call `await llm.ainvoke("What is 2 + 3?")`
4. Assert captured events contain:
   - `LLM_REQUEST` and `LLM_RESPONSE` (at least one pair)
   - `TOOL_CALL` with `tool_name` matching our tool
   - `TOOL_RESULT` with correct computed result
5. Handle both cases: LangChain auto-executes the tool, or LangChain only returns the tool call without execution

### Test 3: Multi-step agent chain (manual mode)

1. Use `create_openai_tools_agent` + `AgentExecutor` with 2-3 simple tools (e.g., `add`, `multiply`)
2. Run `await agent.ainvoke({"input": "Add 2 and 3, then multiply the result by 4"})`
3. Assert captured events contain:
   - Multiple `LLM_REQUEST`/`LLM_RESPONSE` pairs (agent loops)
   - `TOOL_CALL`/`TOOL_RESULT` events for each tool invocation
   - Chain start/end events from `AgentExecutor`
   - Parent-child relationships: tool events have a non-None `parent_id` that corresponds to an event in the session (note: the parent may be a chain event, not directly an LLM event, due to LangChain's internal run tree structure)
4. Do NOT assert that `parent_id` of tool events points to a specific LLM event — LangChain may insert intermediate chain runs

### Test 4: Auto-patch mode (basic LLM call)

The auto-patch `LangChainAdapter` uses `SyncTransport` (HTTP POST to collector) rather than the async `TraceContext`/`EventBuffer` pipeline. Therefore, this test validates at the transport level, not the `EventBuffer` level.

1. Patch `SyncTransport.send_event` to capture event payloads in a local list
2. Call `auto_patch.activate()` to install global handler (does NOT require a running server — the transport patch intercepts calls)
3. Create `ChatOpenAI` **without** explicit callbacks
4. Call `await llm.ainvoke("Say hello")`
5. Assert captured transport payloads include events with `LLM_REQUEST` and `LLM_RESPONSE` event types
6. Call `auto_patch.deactivate()` in teardown

This test does NOT use the `captured_events` or `trace_context` fixtures — it operates entirely through the auto-patch transport layer.

## Assertions across all tests

For every test, verify:
- Event count is non-zero
- Event ordering is temporally consistent (sequence numbers increase)
- Session ID is consistent across all events
- No unexpected error events
- Duration fields are positive where expected

## Dependencies

- `langchain-openai` (for `ChatOpenAI`)
- `langchain` (for `AgentExecutor`, `create_openai_tools_agent`)
- `langchain-core` (already in optional deps)
- `ZAI_API_KEY` environment variable

Install: `pip install -e ".[langchain]" langchain-openai langchain`
