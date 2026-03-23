"""
Mock research agent — no API keys required.

Simulates a multi-step research agent that:
  - Searches the web (mocked)
  - Summarizes results
  - Checks for safety issues
  - Records a final answer

After running this script, open the debugger UI to inspect the trace.

Usage:
    # Terminal 1: start the server
    uvicorn api.main:app --reload --port 8000

    # Terminal 2: run this script
    python examples/mock_research_agent.py

    # Terminal 3: start the frontend (optional)
    cd frontend && npm run dev
    # open http://localhost:5173

    # Or inspect via API directly:
    curl http://localhost:8000/api/sessions
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk import TraceContext
from agent_debugger_sdk import init

# ---------------------------------------------------------------------------
# Mocked "tools" — replace these with real implementations
# ---------------------------------------------------------------------------

async def web_search(query: str) -> list[dict]:
    """Simulated web search."""
    await asyncio.sleep(0.05)
    return [
        {"title": f"Result 1 for '{query}'", "url": "https://example.com/1", "snippet": "...relevant content..."},
        {"title": f"Result 2 for '{query}'", "url": "https://example.com/2", "snippet": "...more content..."},
    ]


async def summarize(text: str) -> str:
    """Simulated summarization."""
    await asyncio.sleep(0.03)
    return f"Summary: {text[:80]}..."


async def safety_check(content: str) -> dict:
    """Simulated safety checker."""
    await asyncio.sleep(0.02)
    return {"safe": True, "flags": []}


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

async def research_agent(question: str) -> str:
    async with TraceContext(agent_name="research_agent", framework="custom") as ctx:

        # Step 1: decide how to answer
        await ctx.record_decision(
            reasoning=f"User asked: '{question}'. Best approach is web search then summarize.",
            confidence=0.9,
            chosen_action="web_search",
            evidence=[{"source": "user_input", "content": question}],
        )

        # Step 2: web search
        await ctx.record_tool_call("web_search", {"query": question})
        results = await web_search(question)
        await ctx.record_tool_result("web_search", result=results, duration_ms=50)

        # Step 3: decide to summarize
        await ctx.record_decision(
            reasoning=f"Got {len(results)} results. Summarizing top result.",
            confidence=0.85,
            chosen_action="summarize",
            evidence=[{"source": "web_search", "content": str(results[0])}],
        )

        # Step 4: summarize
        raw_text = " ".join(r["snippet"] for r in results)
        await ctx.record_tool_call("summarize", {"text": raw_text})
        summary = await summarize(raw_text)
        await ctx.record_tool_result("summarize", result={"summary": summary}, duration_ms=30)

        # Step 5: safety check before returning
        await ctx.record_tool_call("safety_check", {"content": summary})
        safety = await safety_check(summary)
        await ctx.record_tool_result("safety_check", result=safety, duration_ms=20)

        if not safety["safe"]:
            await ctx.record_safety_check(
                policy_name="content_safety",
                outcome="block",
                risk_level="high",
                rationale="Flagged content detected",
            )
            return "Blocked: unsafe content detected."

        await ctx.record_safety_check(
            policy_name="content_safety",
            outcome="pass",
            risk_level="low",
            rationale="Content is safe",
        )

        return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # Use 127.0.0.1 (not localhost) so the SDK keeps the custom endpoint
    # and switches to HTTP transport mode to POST events to the server.
    init(api_key="local-dev", endpoint="http://127.0.0.1:8000")

    questions = [
        "What is agentic AI?",
        "How does LangChain work?",
        "What is time-travel debugging?",
    ]

    print("Running mock research agent...\n")
    for q in questions:
        answer = await research_agent(q)
        print(f"Q: {q}")
        print(f"A: {answer}\n")

    print("Done. Open http://localhost:8000/api/sessions to see recorded sessions.")
    print("Or open http://localhost:5173 for the visual debugger UI.")


if __name__ == "__main__":
    asyncio.run(main())
