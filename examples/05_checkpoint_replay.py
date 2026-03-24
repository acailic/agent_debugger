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

init(api_key="local-dev", endpoint="http://127.0.0.1:8000")


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
