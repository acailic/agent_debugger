# Examples Folder Design

**Date:** 2026-03-23
**Goal:** Reorganize and expand `examples/` so developers can quickly find and run focused, self-contained scenarios that demonstrate each major capability of Peaky Peek.

---

## Design Decisions

- **Flat structure with numeric prefixes** — all files stay in `examples/`, named `NN_<topic>.py`. Numbers create a natural learning path (basic → frameworks → features). No subfolders means no `sys.path` complexity; every script runs with `python examples/NN_<topic>.py` from the repo root.
- **One scenario per file** — each file demonstrates exactly one concept. Short (~50–100 lines), heavily commented, self-contained.
- **No real API keys required** — all LLM calls are mocked or use the existing mock framework. Files document what to swap in for real usage.
- **Consistent docstring header** — every file starts with the same 5-line format (what it demonstrates, what you'll see, run instructions).
- **`examples/README.md` as the index** — one-stop reference listing all examples with a one-line description, run command, and what to look for in the UI.

---

## File Map

### Files to rename (content unchanged, only filename)

| Current name | New name | Why |
|---|---|---|
| `hello_agent.py` | `01_hello.py` | First example in the learning path |
| `mock_research_agent.py` | `02_research_agent.py` | Second example, multi-step |
| `demo_safety_audit.py` | `06_safety_audit.py` | Existing feature demo |
| `demo_live_stream.py` | `08_live_stream.py` | Existing feature demo |

### Files to create (new content)

| File | What it demonstrates |
|---|---|
| `03_langchain.py` | LangChain adapter — attach `LangChainTracingHandler` to a mock LangChain chain and trace LLM requests + tool calls |
| `04_pydantic_ai.py` | PydanticAI adapter — wrap a mock `Agent` with `PydanticAIAdapter` and trace a run |
| `05_checkpoint_replay.py` | Create a trace with a checkpoint mid-execution, then fetch and print the checkpoint state via the REST API to show replay capability |
| `07_loop_detection.py` | Simulate an agent that calls the same tool 4 times in a row, triggering the live loop-detection heuristic |

### File to create (documentation)

| File | Purpose |
|---|---|
| `examples/README.md` | Index table: example number, filename, one-line description, run command, what to look for in the UI |

---

## Docstring Header Format (every file)

```python
"""
<Title> — <one-line description of what this demonstrates>

What you'll see:
  - <bullet: first observable thing in the UI>
  - <bullet: second observable thing>

Run:
    uvicorn api.main:app --port 8000          # Terminal 1
    python examples/NN_<name>.py             # Terminal 2
    # Open http://localhost:5173 or: curl http://localhost:8000/api/sessions
"""
```

---

## Example Content Sketches

### `03_langchain.py`
- Imports `LangChainTracingHandler` from `agent_debugger_sdk.adapters`
- Creates a mock LangChain-style callback flow (no real LLM — uses `LANGCHAIN_AVAILABLE` guard same as adapter)
- Attaches the handler to a `TraceContext`
- Manually fires `on_llm_start`, `on_llm_end`, `on_tool_start`, `on_tool_end` to simulate a chain run
- Prints session ID and trace URL

### `04_pydantic_ai.py`
- Imports `PydanticAIAdapter` from `agent_debugger_sdk.adapters`
- Uses a mock agent (no real API key) wrapped with the adapter
- Runs a single mock turn, records LLM request/response
- Prints session ID

### `05_checkpoint_replay.py`
- Runs a 3-step agent (decide → tool call → checkpoint)
- After the trace closes, fetches the session via `httpx` or `urllib` (stdlib only) to show the checkpoint exists
- Prints checkpoint label and state dict
- Comment block explains: "to replay, restart the server and POST to /api/sessions/{id}/replay"

### `07_loop_detection.py`
- Runs a simple agent that calls `search_tool` 4 times with near-identical inputs (simulating a stuck loop)
- Between calls, logs: "trying again..." to console
- After the 4th call, records a `record_decision` with reasoning: "loop detected, stopping"
- What to look for: live alert in the UI timeline

---

## `examples/README.md` Structure

```
# Examples

Run any example from the repo root after starting the server:
    uvicorn api.main:app --port 8000

| # | File | Demonstrates | What to look for |
|---|------|-------------|-----------------|
| 01 | 01_hello.py | Minimal trace: decision + tool call + checkpoint | Timeline, Decisions panel |
| 02 | 02_research_agent.py | Multi-step mock research agent | Decision tree, tool inspector |
| 03 | 03_langchain.py | LangChain adapter | LLM events in timeline |
| 04 | 04_pydantic_ai.py | PydanticAI adapter | LLM request/response pairs |
| 05 | 05_checkpoint_replay.py | Checkpoint creation and state fetch | Checkpoint panel, replay button |
| 06 | 06_safety_audit.py | Safety audit trail (3 adversarial scenarios) | Safety filter, Refusals tab |
| 07 | 07_loop_detection.py | Tool loop triggering live alert | Live alerts timeline |
| 08 | 08_live_stream.py | Live event streaming with staged delays | Live summary panel |
```

---

## Constraints

- No real API keys required for any example
- Each file ≤ 120 lines
- No new dependencies beyond what is already in `pyproject.toml`
- All examples use `sys.path.insert(0, ...)` pattern already established in `hello_agent.py`
- LangChain and PydanticAI examples use `if not LANGCHAIN_AVAILABLE` / `if not PYDANTIC_AI_AVAILABLE` guards and print a helpful install message if the optional dependency is missing

---

## Success Criteria

- `examples/README.md` exists and lists all 8 examples
- Files `01_hello.py` through `08_live_stream.py` exist in `examples/`
- Old filenames (`hello_agent.py`, `mock_research_agent.py`, `demo_safety_audit.py`, `demo_live_stream.py`) are removed
- Each new file has the standard docstring header
- `03_langchain.py` and `04_pydantic_ai.py` print a clear error if optional deps are missing
- `05_checkpoint_replay.py` fetches and prints checkpoint state after the trace closes
- `07_loop_detection.py` calls the same tool ≥ 4 times within one trace
