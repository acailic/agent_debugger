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
- Check `LANGCHAIN_AVAILABLE` at top; if `False`, print `"Install langchain-core: pip install langchain-core"` and `sys.exit(0)`
- Create a `TraceContext` with `async with TraceContext(...) as ctx:`
- Create `handler = LangChainTracingHandler(session_id=ctx.session_id)` then call `handler.set_context(ctx)` — **required** before any callbacks fire (handler silently no-ops without it)
- Call `await handler.on_llm_start(serialized={}, prompts=["What is 2+2?"], run_id=uuid.uuid4())` to simulate an LLM request
- Call `await handler.on_llm_end(response=LLMResult(generations=[[]], llm_output={"model": "mock"}), run_id=uuid.uuid4())` to simulate the response
- Call `await handler.on_tool_start(serialized={"name": "calculator"}, input_str="2+2", run_id=uuid.uuid4())` and `await handler.on_tool_end(output="4", run_id=uuid.uuid4())` to simulate a tool call
- Print session ID — all events visible in the UI timeline under that session

### `04_pydantic_ai.py`
- Check `PYDANTIC_AI_AVAILABLE` at top; if `False`, print `"Install pydantic-ai: pip install pydantic-ai"` and `sys.exit(0)` — **must** be before any adapter instantiation since `PydanticAIAdapter.__init__` raises `ImportError` when the dep is absent
- Create a `TraceContext` with `async with TraceContext(...) as ctx:`
- Use `PydanticAIAdapter` with a mock `Agent("openai:gpt-4o-mini")` — agent will not be invoked (no real API key); only the wrapper's trace methods are called directly
- Call `await ctx.record_llm_request(model="mock", messages=[{"role": "user", "content": "What is 2+2?"}])` and `await ctx.record_llm_response(model="mock", content="4", duration_ms=50)` directly on the context to produce visible LLM events (use `messages=` not `prompt=`; use `content=` not `response=`)
- Add a comment: "For a real run: set OPENAI_API_KEY and call `await adapter.run('your question')`"
- Prints session ID

### `05_checkpoint_replay.py`
- Runs a 3-step agent (decide → tool call → checkpoint)
- After the trace closes, fetches the session via `httpx` (already a declared dependency in `pyproject.toml`) — use `httpx.get(f"http://localhost:8000/api/sessions/{session_id}")`
- Prints the checkpoint label and state dict extracted from the response JSON
- Comment block explains: "to replay from this checkpoint: POST /api/sessions/{id}/replay with the checkpoint id"

### `07_loop_detection.py`
- Runs a simple agent that calls `search_tool` 4 times with near-identical inputs (simulating a stuck loop)
- Between calls, prints: "trying again..." to console
- After the 4th call, calls `await ctx.record_behavior_alert(alert_type="tool_loop_detected", signal="search_tool called 4 times with similar inputs", severity="high")` — second arg is `signal=`, not `description=` (verified against `context.py` signature)
- Do NOT use `record_decision` for this — use `record_behavior_alert` for consistency
- What to look for in the UI: Live alerts timeline, loop detection heuristic panel

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
- **≤ 120 lines applies only to newly created files** (`03_langchain.py`, `04_pydantic_ai.py`, `05_checkpoint_replay.py`, `07_loop_detection.py`). Renamed files (`01`, `02`, `06`, `08`) keep their original content unchanged — line count constraint does not apply to them.
- No new dependencies beyond what is already in `pyproject.toml`
- All examples use `sys.path.insert(0, ...)` pattern and `asyncio.run(main())` entry point
- LangChain example: check `LANGCHAIN_AVAILABLE` at top; print install hint and `sys.exit(0)` if missing
- PydanticAI example: check `PYDANTIC_AI_AVAILABLE` at top; print install hint and `sys.exit(0)` if missing (the adapter raises `ImportError` on `__init__` when dep is absent — the guard must be at the top of the script before instantiation)

---

## Success Criteria

- `examples/README.md` exists and lists all 8 examples
- Files `01_hello.py` through `08_live_stream.py` exist in `examples/`
- Old filenames (`hello_agent.py`, `mock_research_agent.py`, `demo_safety_audit.py`, `demo_live_stream.py`) are removed
- Each new file has the standard docstring header
- `03_langchain.py` and `04_pydantic_ai.py` print a clear error if optional deps are missing
- `05_checkpoint_replay.py` fetches and prints checkpoint state after the trace closes
- `07_loop_detection.py` calls the same tool ≥ 4 times within one trace
