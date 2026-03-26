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

from agent_debugger_sdk import TraceContext, init
from agent_debugger_sdk.adapters.langchain import LANGCHAIN_AVAILABLE, LangChainTracingHandler

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
