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
