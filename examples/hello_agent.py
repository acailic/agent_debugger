"""
Hello Agent — minimal Peaky Peek example.

No API keys required. Demonstrates the core trace model in ~50 lines.

Quick start:
    # Install and start the server
    pip install peaky-peek-server
    uvicorn api.main:app --port 8000

    # In another terminal, run this script
    python examples/hello_agent.py

    # Inspect the trace
    curl http://localhost:8000/api/sessions
    # Or open http://localhost:5173 for the visual UI
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk import TraceContext
from agent_debugger_sdk import init

init()  # connects to http://localhost:8000 by default; set AGENT_DEBUGGER_URL to override


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
            label="after_weather_fetch",
            state={"location": location, "result": result},
        )
        print("[trace] checkpoint created: after_weather_fetch")

        return f"{result['temp_c']}°C, {result['condition']} in {location}"


async def main() -> None:
    answer = await weather_agent("Seattle")
    print(f"\nAnswer: {answer}")
    print("\nView the trace:")
    print("  curl http://localhost:8000/api/sessions")
    print("  http://localhost:5173  (visual UI)")


if __name__ == "__main__":
    asyncio.run(main())
