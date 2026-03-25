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
- Auto-patch mode (basic LLM call)
- In-memory event capture via `EventBuffer`

### Out of scope

- Streaming responses
- Full API + storage pipeline (in-memory only)
- CI integration (tests gated behind `ZAI_API_KEY`)
- Token cost accuracy assertions
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

Register `integration` marker in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: End-to-end tests requiring API keys (deselected by default)",
]
```

### How to run

```bash
# All integration tests
python3 -m pytest -m integration tests/integration/

# Specific test file
python3 -m pytest -m integration tests/integration/test_langchain_integration.py

# Normal CI (excludes integration)
python3 -m pytest
```

## Conftest fixtures

### `integration_enabled`

- Session-scoped
- Checks `ZAI_API_KEY` is set in environment
- Skips entire module if absent

### `zai_chat_model`

- Creates `ChatOpenAI` instance with:
  - `base_url="https://api.z.ai/api/coding/paas/v4"`
  - `api_key=os.environ["ZAI_API_KEY"]`
  - Configurable `model` (defaults to sensible choice)
  - Small `max_tokens` to minimize cost
  - Low `temperature` for deterministic output

### `trace_context` (per-test)

- Creates `TraceContext` with unique `session_id`, `agent_name="integration-test"`, `framework="langchain"`
- Enters context via `async with`, yields context + session_id
- Exits context after test completes

### `captured_events` (per-test)

- After test body runs, reads all events from global `EventBuffer` for the test's `session_id`
- Returns `list[TraceEvent]`

### `langchain_handler` (per-test)

- Creates `LangChainTracingHandler` wired to `trace_context`
- Used by manual-mode tests

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
   - Parent-child relationships: tool events have `parent_id` pointing to the LLM event that triggered them

### Test 4: Auto-patch mode (basic LLM call)

1. Call `auto_patch.activate()` to install global handler
2. Create `ChatOpenAI` **without** explicit callbacks
3. Call `await llm.ainvoke("Say hello")`
4. Assert events are captured (global handler picks them up):
   - `LLM_REQUEST` and `LLM_RESPONSE` present
5. Call `auto_patch.deactivate()` in cleanup (teardown fixture)

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
