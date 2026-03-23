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
