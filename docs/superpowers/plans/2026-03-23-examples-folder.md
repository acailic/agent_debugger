# Examples Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `examples/` with numeric prefixes, add 4 new focused example scripts and a README index, and delete the old filenames.

**Architecture:** Flat `examples/` folder, files named `01_` through `08_`, each ≤ 120 lines (new files only), each self-contained and runnable with `python examples/NN_<name>.py` from the repo root. The existing 4 files are renamed only (content unchanged). Four new files are created from scratch.

**Tech Stack:** Python 3.10+, `agent_debugger_sdk` (local), `httpx` (declared dep), `langchain-core` (optional), `pydantic-ai` (optional).

---

## Important notes for all implementors

- Repo root: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger`
- All scripts use `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` to add the repo root to path
- All scripts use `asyncio.run(main())` as entry point
- `create_checkpoint(state=dict, ...)` — **no `label` parameter**; put labels inside the `state` dict
- `record_behavior_alert(alert_type, signal, *, severity)` — second arg is `signal=`, not `description=`
- `record_llm_request(model, messages, ...)` — second arg is `messages=list[dict]`, not `prompt=`
- `record_llm_response(model, content, ...)` — second arg is `content=`, not `response=`
- Commit author: `--author="acailic <acailic@users.noreply.github.com>"`

---

## File Map

| Action | From | To |
|--------|------|----|
| Rename | `examples/hello_agent.py` | `examples/01_hello.py` |
| Rename | `examples/mock_research_agent.py` | `examples/02_research_agent.py` |
| Create | — | `examples/03_langchain.py` |
| Create | — | `examples/04_pydantic_ai.py` |
| Create | — | `examples/05_checkpoint_replay.py` |
| Rename | `examples/demo_safety_audit.py` | `examples/06_safety_audit.py` |
| Create | — | `examples/07_loop_detection.py` |
| Rename | `examples/demo_live_stream.py` | `examples/08_live_stream.py` |
| Create | — | `examples/README.md` |

---

## Task 1 — Rename existing files

**Files:**
- Rename: `examples/hello_agent.py` → `examples/01_hello.py`
- Rename: `examples/mock_research_agent.py` → `examples/02_research_agent.py`
- Rename: `examples/demo_safety_audit.py` → `examples/06_safety_audit.py`
- Rename: `examples/demo_live_stream.py` → `examples/08_live_stream.py`

- [ ] **Step 1: Rename all four files using git mv**

```bash
cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger
git mv examples/hello_agent.py examples/01_hello.py
git mv examples/mock_research_agent.py examples/02_research_agent.py
git mv examples/demo_safety_audit.py examples/06_safety_audit.py
git mv examples/demo_live_stream.py examples/08_live_stream.py
```

- [ ] **Step 2: Verify renames**

```bash
ls examples/*.py | grep -v __pycache__
```

Expected output includes `01_hello.py`, `02_research_agent.py`, `06_safety_audit.py`, `08_live_stream.py`.
Original names (`hello_agent.py`, `mock_research_agent.py`, `demo_safety_audit.py`, `demo_live_stream.py`) must NOT appear.

- [ ] **Step 3: Verify file contents unchanged**

```bash
wc -l examples/01_hello.py examples/02_research_agent.py examples/06_safety_audit.py examples/08_live_stream.py
```

Expected: `01_hello.py` ≈ 71 lines, `02_research_agent.py` ≈ 147 lines, `06_safety_audit.py` ≈ 306 lines, `08_live_stream.py` ≈ 260 lines.

- [ ] **Step 4: Commit renames**

```bash
git commit --author="acailic <acailic@users.noreply.github.com>" -m "refactor: rename examples with numeric prefixes"
```

---

## Task 2 — Create `03_langchain.py`

**Files:**
- Create: `examples/03_langchain.py`

**CRITICAL**: `LangChainTracingHandler.__init__` raises `ImportError` when langchain-core is not installed — the `LANGCHAIN_AVAILABLE` guard must be checked BEFORE creating the handler. The handler requires `handler.set_context(ctx)` to be called before any callbacks, otherwise it silently no-ops.

- [ ] **Step 1: Create the file with exact content**

```python
"""
LangChain Adapter — trace LLM requests and tool calls via LangChainTracingHandler.

What you'll see:
  - LLM request and response events in the session timeline
  - A tool call event (calculator) linked to the LLM run

Run:
    uvicorn api.main:app --port 8000          # Terminal 1
    python examples/03_langchain.py           # Terminal 2
    # Open http://localhost:5173 or: curl http://localhost:8000/api/sessions
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk.adapters.langchain import LANGCHAIN_AVAILABLE, LangChainTracingHandler
from agent_debugger_sdk import TraceContext, init

if not LANGCHAIN_AVAILABLE:
    print("langchain-core is required for this example.")
    print("Install it: pip install langchain-core")
    sys.exit(0)

# LLMResult is only importable when langchain-core is present
from langchain_core.outputs import LLMResult  # noqa: E402

init()


async def main() -> None:
    async with TraceContext(agent_name="langchain_agent", framework="langchain") as ctx:
        print(f"[trace] session_id = {ctx.session_id}")

        # Create the handler and attach it to the active trace context
        handler = LangChainTracingHandler(session_id=ctx.session_id, agent_name="langchain_agent")
        handler.set_context(ctx)  # required — handler silently no-ops without this

        llm_run_id = uuid.uuid4()
        tool_run_id = uuid.uuid4()

        # Simulate: LLM receives a prompt
        await handler.on_llm_start(
            serialized={"name": "mock-llm"},
            prompts=["What is 2 + 2?"],
            run_id=llm_run_id,
        )
        print("[trace] → on_llm_start fired")

        # Simulate: LLM responds
        await handler.on_llm_end(
            response=LLMResult(
                generations=[[type("Gen", (), {"text": "I'll use the calculator tool."})()]],
                llm_output={"model": "mock", "token_usage": {"prompt_tokens": 10, "completion_tokens": 8}},
            ),
            run_id=llm_run_id,
        )
        print("[trace] → on_llm_end fired")

        # Simulate: LLM invokes a tool
        await handler.on_tool_start(
            serialized={"name": "calculator"},
            input_str="2 + 2",
            run_id=tool_run_id,
        )
        await handler.on_tool_end(output="4", run_id=tool_run_id)
        print("[trace] → on_tool_start / on_tool_end fired")

    print(f"\nDone. View trace at: http://localhost:8000/api/sessions/{ctx.session_id}")
    print("Or open the UI: http://localhost:5173")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify file is ≤ 120 lines**

```bash
wc -l examples/03_langchain.py
```

Expected: ≤ 120 lines.

- [ ] **Step 3: Verify syntax**

```bash
python3 -m py_compile examples/03_langchain.py && echo "syntax OK"
```

Expected: `syntax OK`

- [ ] **Step 4: Commit**

```bash
git add examples/03_langchain.py
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat(examples): add 03_langchain.py — LangChain adapter trace"
```

---

## Task 3 — Create `04_pydantic_ai.py`

**Files:**
- Create: `examples/04_pydantic_ai.py`

**CRITICAL**: `PYDANTIC_AI_AVAILABLE` guard must be at the top before any import of `PydanticAIAdapter` — the adapter's `__init__` raises `ImportError` when pydantic-ai is not installed. Use `ctx.record_llm_request(model, messages)` and `ctx.record_llm_response(model, content)` directly — do NOT call `prompt=` or `response=`.

- [ ] **Step 1: Create the file with exact content**

```python
"""
PydanticAI Adapter — trace LLM request/response pairs via PydanticAIAdapter.

What you'll see:
  - LLM request event with messages list in the session timeline
  - LLM response event with content and duration

Run:
    uvicorn api.main:app --port 8000          # Terminal 1
    python examples/04_pydantic_ai.py         # Terminal 2
    # Open http://localhost:5173 or: curl http://localhost:8000/api/sessions

Note: For a real run, set OPENAI_API_KEY and swap the mock trace calls for:
    adapter = PydanticAIAdapter(agent, agent_name="my_agent")
    result = await adapter.run("your question")
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk.adapters.pydantic_ai import PYDANTIC_AI_AVAILABLE
from agent_debugger_sdk import TraceContext, init

if not PYDANTIC_AI_AVAILABLE:
    print("pydantic-ai is required for this example.")
    print("Install it: pip install pydantic-ai")
    sys.exit(0)

from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter  # noqa: E402, F401

init()


async def main() -> None:
    async with TraceContext(agent_name="pydantic_ai_agent", framework="pydantic_ai") as ctx:
        print(f"[trace] session_id = {ctx.session_id}")

        # Record an LLM request (messages= list of dicts, not prompt=)
        await ctx.record_llm_request(
            model="mock-gpt",
            messages=[{"role": "user", "content": "What is 2 + 2?"}],
        )
        print("[trace] → LLM request recorded")

        # Record the LLM response (content=, not response=)
        await ctx.record_llm_response(
            model="mock-gpt",
            content="The answer is 4.",
            duration_ms=42.0,
        )
        print("[trace] → LLM response recorded")

    print(f"\nDone. View trace at: http://localhost:8000/api/sessions/{ctx.session_id}")
    print("Or open the UI: http://localhost:5173")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify ≤ 120 lines and syntax**

```bash
wc -l examples/04_pydantic_ai.py
python3 -m py_compile examples/04_pydantic_ai.py && echo "syntax OK"
```

- [ ] **Step 3: Commit**

```bash
git add examples/04_pydantic_ai.py
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat(examples): add 04_pydantic_ai.py — PydanticAI adapter trace"
```

---

## Task 4 — Create `05_checkpoint_replay.py`

**Files:**
- Create: `examples/05_checkpoint_replay.py`

**CRITICAL**: `create_checkpoint(state=dict)` has NO `label` parameter — put the label inside the `state` dict. Uses `httpx` (already in `pyproject.toml`) to fetch the session after the trace closes.

- [ ] **Step 1: Create the file with exact content**

```python
"""
Checkpoint Replay — create a checkpoint mid-execution and inspect its state.

What you'll see:
  - A checkpoint in the session's Checkpoint panel
  - Printed checkpoint state from the REST API

Run:
    uvicorn api.main:app --port 8000          # Terminal 1
    python examples/05_checkpoint_replay.py   # Terminal 2
    # Open http://localhost:5173 → select the session → Checkpoints tab

To replay from a checkpoint:
    POST http://localhost:8000/api/sessions/{session_id}/replay
    Body: {"checkpoint_id": "<id from output>"}
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from agent_debugger_sdk import TraceContext, init

init()


async def run_agent_with_checkpoint() -> str:
    """Run a 3-step agent and create a checkpoint after the tool call."""
    async with TraceContext(agent_name="checkpoint_agent", framework="custom") as ctx:
        session_id = ctx.session_id
        print(f"[trace] session_id = {session_id}")

        # Step 1: decision
        await ctx.record_decision(
            reasoning="User asked for a calculation. Will call the math tool.",
            confidence=0.95,
            chosen_action="call_math_tool",
            evidence=[{"source": "user_input", "content": "What is 6 * 7?"}],
        )
        print("[trace] decision → call_math_tool")

        # Step 2: tool call + result
        await ctx.record_tool_call("math_tool", {"expression": "6 * 7"})
        result = {"answer": 42}
        await ctx.record_tool_result("math_tool", result=result, duration_ms=5)
        print(f"[trace] tool call → math_tool: {result}")

        # Step 3: checkpoint — label goes inside state, no label= parameter
        await ctx.create_checkpoint(
            state={"label": "after_math_tool", "expression": "6 * 7", "result": result},
            importance=0.9,
        )
        print("[trace] checkpoint created")

    return session_id


async def main() -> None:
    session_id = await run_agent_with_checkpoint()

    # Fetch the session to confirm checkpoint was recorded
    print(f"\nFetching session {session_id} from API...")
    try:
        response = httpx.get(f"http://localhost:8000/api/sessions/{session_id}", timeout=5.0)
        response.raise_for_status()
        data = response.json()

        checkpoints = data.get("checkpoints", [])
        if checkpoints:
            cp = checkpoints[0]
            checkpoint_id = cp.get("id", "")
            print(f"  Checkpoint ID    : {checkpoint_id}")
            print(f"  Checkpoint state : {cp.get('state', {})}")
            print(f"\nTo replay: POST /api/sessions/{session_id}/replay")
            print(f'           Body: {{"checkpoint_id": "{checkpoint_id}"}}')
        else:
            # Checkpoints may be nested under traces; print raw for inspection
            print("  Session data:", data)
    except httpx.ConnectError:
        print("  Could not connect to server. Is uvicorn running on port 8000?")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify ≤ 120 lines and syntax**

```bash
wc -l examples/05_checkpoint_replay.py
python3 -m py_compile examples/05_checkpoint_replay.py && echo "syntax OK"
```

- [ ] **Step 3: Commit**

```bash
git add examples/05_checkpoint_replay.py
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat(examples): add 05_checkpoint_replay.py — checkpoint creation and fetch"
```

---

## Task 5 — Create `07_loop_detection.py`

**Files:**
- Create: `examples/07_loop_detection.py`

**CRITICAL**: Use `record_behavior_alert(alert_type, signal, *, severity)` — second positional arg is `signal=`, NOT `description=`. Call the same tool ≥ 4 times to simulate a stuck loop.

- [ ] **Step 1: Create the file with exact content**

```python
"""
Loop Detection — simulate a stuck agent to trigger the live loop-detection alert.

What you'll see:
  - 4 identical tool call events for "search_tool" in the timeline
  - A BehaviorAlert event: tool_loop_detected (severity: high)
  - Live alert in the UI's alerts timeline

Run:
    uvicorn api.main:app --port 8000          # Terminal 1
    python examples/07_loop_detection.py      # Terminal 2
    # Open http://localhost:5173 → select the session → Live / Alerts tab
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk import TraceContext, init

init()


async def stuck_agent(query: str) -> None:
    """Simulate an agent that keeps retrying the same search tool call."""
    async with TraceContext(agent_name="stuck_agent", framework="custom") as ctx:
        print(f"[trace] session_id = {ctx.session_id}")

        # Simulate a stuck loop — same tool called 4 times with nearly identical inputs
        for attempt in range(1, 5):
            print(f"[trace] attempt {attempt}/4 — calling search_tool...")
            await ctx.record_tool_call("search_tool", {"query": query, "attempt": attempt})
            # Mocked result — always returns the same unhelpful response
            await ctx.record_tool_result(
                "search_tool",
                result={"results": [], "message": "No results found"},
                duration_ms=50,
            )
            if attempt < 4:
                print("         trying again...")
                await asyncio.sleep(0.1)  # small delay so events are visible in live stream

        # Record the loop detection alert
        # NOTE: second arg is signal=, not description=
        await ctx.record_behavior_alert(
            alert_type="tool_loop_detected",
            signal="search_tool called 4 times with identical query — no progress made",
            severity="high",
        )
        print("[trace] behavior alert → tool_loop_detected (severity: high)")


async def main() -> None:
    await stuck_agent("latest AI research papers")
    print("\nDone. Open the UI to see the loop detection alert:")
    print("  http://localhost:5173")
    print("  Navigate to: session → Alerts tab or Live panel")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify ≤ 120 lines and syntax**

```bash
wc -l examples/07_loop_detection.py
python3 -m py_compile examples/07_loop_detection.py && echo "syntax OK"
```

- [ ] **Step 3: Commit**

```bash
git add examples/07_loop_detection.py
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat(examples): add 07_loop_detection.py — stuck agent loop alert"
```

---

## Task 6 — Create `examples/README.md`

**Files:**
- Create: `examples/README.md`

- [ ] **Step 1: Create the README**

Write `examples/README.md` with the exact content below. Use the Write tool directly — do NOT wrap this in a Markdown code block or the nested fences will break.

File content to write verbatim:

---
CONTENT START (write everything between the markers, no markers in the file)

# Examples

Focused, self-contained scenarios for testing and exploring Peaky Peek.

## Prerequisites

Start the API server before running any example:

    # From the repo root
    uvicorn api.main:app --port 8000
    # Optional: open the UI at http://localhost:5173

Then in a second terminal:

    python examples/01_hello.py

## All Examples

| # | File | Demonstrates | What to look for in the UI |
|---|------|--------------|---------------------------|
| 01 | `01_hello.py` | Minimal trace: decision + tool call + checkpoint | Timeline, Decisions panel |
| 02 | `02_research_agent.py` | Multi-step mock research agent | Decision tree, Tool inspector |
| 03 | `03_langchain.py` | LangChain adapter (requires `pip install langchain-core`) | LLM events in timeline |
| 04 | `04_pydantic_ai.py` | PydanticAI adapter (requires `pip install pydantic-ai`) | LLM request/response pairs |
| 05 | `05_checkpoint_replay.py` | Checkpoint creation and state fetch via REST API | Checkpoint panel, replay button |
| 06 | `06_safety_audit.py` | Safety audit trail: 3 adversarial scenarios | Safety filter, Refusals tab |
| 07 | `07_loop_detection.py` | Stuck agent loop triggering live behavior alert | Live alerts timeline |
| 08 | `08_live_stream.py` | Live event streaming with staged delays | Live summary panel |

## Optional dependencies

Examples 03 and 04 require optional framework packages not installed by default:

    pip install langchain-core    # for 03_langchain.py
    pip install pydantic-ai       # for 04_pydantic_ai.py

Both examples print a helpful install message and exit gracefully if the dependency is missing.

CONTENT END
---

- [ ] **Step 2: Verify README renders correctly (spot-check)**

```bash
wc -l examples/README.md
grep -c "\.py" examples/README.md
```

Expected: `README.md` present, ≥ 8 `.py` references in the file.

- [ ] **Step 3: Commit**

```bash
git add examples/README.md
git commit --author="acailic <acailic@users.noreply.github.com>" -m "docs(examples): add README index for all examples"
```

---

## Task 7 — Final verification and push

- [ ] **Step 1: Verify all 8 numbered files exist**

```bash
ls examples/0*.py
```

Expected output (8 files):
```
examples/01_hello.py
examples/02_research_agent.py
examples/03_langchain.py
examples/04_pydantic_ai.py
examples/05_checkpoint_replay.py
examples/06_safety_audit.py
examples/07_loop_detection.py
examples/08_live_stream.py
```

- [ ] **Step 2: Verify old filenames are gone**

```bash
ls examples/hello_agent.py examples/mock_research_agent.py examples/demo_safety_audit.py examples/demo_live_stream.py 2>&1
```

Expected: all 4 produce `No such file or directory`.

- [ ] **Step 3: Verify all new files pass syntax check**

```bash
python3 -m py_compile examples/03_langchain.py && \
python3 -m py_compile examples/04_pydantic_ai.py && \
python3 -m py_compile examples/05_checkpoint_replay.py && \
python3 -m py_compile examples/07_loop_detection.py && \
echo "all new files: syntax OK"
```

Expected: `all new files: syntax OK`

- [ ] **Step 4: Verify line counts for new files**

```bash
wc -l examples/03_langchain.py examples/04_pydantic_ai.py examples/05_checkpoint_replay.py examples/07_loop_detection.py
```

Expected: all ≤ 120 lines each.

- [ ] **Step 5: Push**

```bash
git push
```

---

## Success Criteria

- [ ] `examples/README.md` exists and has 8 rows in the table
- [ ] Files `01_hello.py` through `08_live_stream.py` all exist
- [ ] Old filenames removed: `hello_agent.py`, `mock_research_agent.py`, `demo_safety_audit.py`, `demo_live_stream.py`
- [ ] New files (`03`, `04`, `05`, `07`) are each ≤ 120 lines
- [ ] `03_langchain.py` and `04_pydantic_ai.py` exit gracefully when optional dep missing
- [ ] `07_loop_detection.py` uses `record_behavior_alert` with `signal=` param
- [ ] `05_checkpoint_replay.py` uses `create_checkpoint(state=dict)` without `label=` param
- [ ] All files pass `python3 -m py_compile`
- [ ] All commits pushed to `origin/main`
