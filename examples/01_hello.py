"""
Hello Agent — minimal Peaky Peek example.

No API keys required. Demonstrates the core trace model in ~50 lines.

Quick start:
    # Install and start the server
    pip install peaky-peek-server
    peaky-peek --open

    # In another terminal, run this script
    python examples/01_hello.py

    # Inspect the trace
    curl http://localhost:8000/api/sessions
    # Or open http://localhost:8000/ui/ for the visual UI
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk import TraceContext, init

# An endpoint is all the SDK needs to deliver events over HTTP — no API key
# for a local collector (loopback delivery is unauthenticated). Override the
# endpoint with AGENT_DEBUGGER_URL when the server runs elsewhere.
init(endpoint="http://127.0.0.1:8000")


async def weather_agent(location: str) -> str:
    """Minimal agent that traces a decision, a tool call, and a checkpoint."""
    async with TraceContext(agent_name="weather_agent", framework="custom") as ctx:
        print(f"[trace] session_id = {ctx.session_id}")

        # 1. Decision: what should I do?
        await ctx.record_decision(
            reasoning=f"User wants weather for {location!r}. Calling the weather API.",
            confidence=0.9,
            chosen_action="call_weather_api",
            evidence=[{"source": "user_input", "content": f"What's the weather in {location}?"}],
        )
        print("[trace] decision → call_weather_api (confidence=0.90)")

        # 2. Tool call + result (replace with a real API call)
        await ctx.record_tool_call("weather_api", {"location": location, "units": "metric"})
        result = {"temp_c": 14, "condition": "cloudy", "humidity": 72}  # mocked
        await ctx.record_tool_result("weather_api", result=result, duration_ms=120)
        print(f"[trace] tool call → weather_api result: {result}")

        # 3. Checkpoint: save state so you can replay from here
        await ctx.create_checkpoint(
            state={"location": location, "result": result},
        )
        print("[trace] checkpoint created")

        return f"{result['temp_c']}°C, {result['condition']} in {location}"


async def main() -> None:
    answer = await weather_agent("Seattle")
    print(f"\nAnswer: {answer}")
    print("\nView the trace:")
    print("  curl http://localhost:8000/api/sessions")
    print("  http://localhost:8000/ui/  (visual UI)")


if __name__ == "__main__":
    asyncio.run(main())
