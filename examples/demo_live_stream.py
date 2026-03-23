"""
Demo: Live Streaming

Runs a realistic customer-support triage agent with staged delays so every
event is visible in the UI live stream as it arrives.

Usage:
    # Terminal 1 — start the API
    uvicorn api.main:app --reload --port 8000

    # Terminal 2 (optional) — start the frontend
    cd frontend && npm run dev   # → http://localhost:5173

    # Terminal 3 — run this demo
    python examples/demo_live_stream.py

Open http://localhost:5173, select the live session, and watch events appear
in real time in the Timeline and Live Summary panels.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_debugger_sdk import TraceContext, init


# ---------------------------------------------------------------------------
# Simulated tool implementations (no API keys required)
# ---------------------------------------------------------------------------

async def classify_issue(description: str) -> dict:
    await asyncio.sleep(0.6)
    keywords = description.lower()
    if "billing" in keywords or "charge" in keywords:
        return {"category": "billing", "severity": "medium", "auto_resolve": False}
    if "password" in keywords or "login" in keywords:
        return {"category": "auth", "severity": "low", "auto_resolve": True}
    return {"category": "general", "severity": "low", "auto_resolve": True}


async def lookup_account(user_id: str) -> dict:
    await asyncio.sleep(0.4)
    return {
        "user_id": user_id,
        "plan": "pro",
        "open_tickets": 2,
        "last_login": "2026-03-22T14:30:00Z",
        "billing_ok": True,
    }


async def search_knowledge_base(query: str) -> list[dict]:
    await asyncio.sleep(0.8)
    return [
        {"title": f"How to fix: {query}", "url": "/kb/1", "relevance": 0.92},
        {"title": "Common troubleshooting steps", "url": "/kb/2", "relevance": 0.74},
    ]


async def escalate_to_human(ticket_id: str, reason: str) -> dict:
    await asyncio.sleep(0.3)
    return {"escalated": True, "queue": "tier-2", "ticket_id": ticket_id, "eta_minutes": 12}


async def send_resolution(user_id: str, message: str) -> dict:
    await asyncio.sleep(0.2)
    return {"sent": True, "channel": "email", "user_id": user_id}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

async def support_triage_agent(ticket: dict) -> str:
    """
    Multi-step support triage agent that:
      1. Classifies the issue
      2. Looks up the account
      3. Decides: auto-resolve or escalate
      4. Searches KB if resolving
      5. Sends resolution or escalates to human
      6. Creates a checkpoint before final action
    """
    async with TraceContext(
        agent_name="support_triage",
        framework="custom",
        tags=["demo", "live-stream", "customer-support"],
    ) as ctx:

        # Step 1: Classify the issue
        await asyncio.sleep(0.3)
        await ctx.record_decision(
            reasoning=(
                f"Received ticket #{ticket['id']}: \"{ticket['description']}\". "
                "Need to classify before routing."
            ),
            confidence=0.95,
            chosen_action="classify_issue",
            evidence=[{"source": "ticket", "content": ticket["description"]}],
        )

        await ctx.record_tool_call("classify_issue", {"description": ticket["description"]})
        classification = await classify_issue(ticket["description"])
        await ctx.record_tool_result("classify_issue", result=classification, duration_ms=600)

        print(f"  → classified as: {classification['category']} / severity: {classification['severity']}")

        # Step 2: Look up account
        await asyncio.sleep(0.2)
        await ctx.record_tool_call("lookup_account", {"user_id": ticket["user_id"]})
        account = await lookup_account(ticket["user_id"])
        await ctx.record_tool_result("lookup_account", result=account, duration_ms=400)

        print(f"  → account: plan={account['plan']}, open_tickets={account['open_tickets']}")

        # Step 3: Decide routing
        await asyncio.sleep(0.4)
        if classification["auto_resolve"] and account["open_tickets"] < 3:
            chosen = "auto_resolve"
            confidence = 0.88
            reasoning = (
                f"Issue is {classification['category']} (low severity) and account "
                f"has only {account['open_tickets']} open tickets. Safe to auto-resolve."
            )
        else:
            chosen = "escalate"
            confidence = 0.72
            reasoning = (
                f"{classification['category']} issue with severity={classification['severity']}. "
                f"Account has {account['open_tickets']} open tickets — escalating to tier-2."
            )

        decision_id = await ctx.record_decision(
            reasoning=reasoning,
            confidence=confidence,
            chosen_action=chosen,
            evidence=[
                {"source": "classify_issue", "content": str(classification)},
                {"source": "lookup_account", "content": str(account)},
            ],
            alternatives=[
                {
                    "action": "escalate" if chosen == "auto_resolve" else "auto_resolve",
                    "reason_rejected": "Not appropriate given current context",
                }
            ],
        )

        # Step 4a: Auto-resolve path
        if chosen == "auto_resolve":
            await asyncio.sleep(0.3)
            await ctx.record_tool_call("search_knowledge_base", {"query": ticket["description"]})
            kb_results = await search_knowledge_base(ticket["description"])
            await ctx.record_tool_result("search_knowledge_base", result=kb_results, duration_ms=800)

            print(f"  → found {len(kb_results)} KB articles")

            # Checkpoint before sending resolution
            await ctx.create_checkpoint(
                state={"action": "send_resolution", "kb_results": len(kb_results)},
                memory={"decision_id": decision_id, "top_article": kb_results[0]["title"]},
                importance=0.85,
            )

            await asyncio.sleep(0.2)
            message = f"Hi! Here's how to resolve your issue: {kb_results[0]['title']} ({kb_results[0]['url']})"
            await ctx.record_tool_call("send_resolution", {"user_id": ticket["user_id"], "message": message})
            result = await send_resolution(ticket["user_id"], message)
            await ctx.record_tool_result("send_resolution", result=result, duration_ms=200)

            await ctx.record_safety_check(
                policy_name="auto_resolution_gate",
                outcome="pass",
                risk_level="low",
                rationale="KB article matched with >0.9 relevance; resolution sent safely.",
            )

            print(f"  → resolution sent via {result['channel']}")
            return f"Resolved: sent KB article to {ticket['user_id']}"

        # Step 4b: Escalation path
        else:
            await ctx.record_safety_check(
                policy_name="escalation_guard",
                outcome="warn",
                risk_level="medium",
                rationale=(
                    f"Auto-resolution not safe for {classification['category']} "
                    f"severity={classification['severity']}. Routing to human."
                ),
            )

            # Checkpoint before escalating
            await ctx.create_checkpoint(
                state={"action": "escalate", "category": classification["category"]},
                memory={"decision_id": decision_id, "severity": classification["severity"]},
                importance=0.93,
            )

            await asyncio.sleep(0.3)
            await ctx.record_tool_call(
                "escalate_to_human",
                {"ticket_id": ticket["id"], "reason": f"{classification['category']} requires human review"},
            )
            escalation = await escalate_to_human(
                ticket["id"],
                f"{classification['category']} / {classification['severity']}",
            )
            await ctx.record_tool_result("escalate_to_human", result=escalation, duration_ms=300)

            print(f"  → escalated to {escalation['queue']}, ETA {escalation['eta_minutes']}m")
            return f"Escalated ticket {ticket['id']} to {escalation['queue']}"


# ---------------------------------------------------------------------------
# Main — runs 3 tickets sequentially to populate session list
# ---------------------------------------------------------------------------

DEMO_TICKETS = [
    {
        "id": "TKT-1001",
        "user_id": "user_alice",
        "description": "I forgot my password and can't login to my account",
    },
    {
        "id": "TKT-1002",
        "user_id": "user_bob",
        "description": "I was charged twice for my subscription this month",
    },
    {
        "id": "TKT-1003",
        "user_id": "user_carol",
        "description": "The dashboard keeps showing a loading spinner and never loads",
    },
]


async def main() -> None:
    init(api_key="local-dev", endpoint="http://127.0.0.1:8000")

    print("Support Triage Demo — Live Stream\n")
    print("Open http://localhost:5173 and watch events appear in real time.\n")
    print("-" * 50)

    for ticket in DEMO_TICKETS:
        print(f"\nProcessing {ticket['id']}: {ticket['description'][:50]}...")
        outcome = await support_triage_agent(ticket)
        print(f"  ✓ {outcome}")
        await asyncio.sleep(1.5)  # pause between tickets so list populates visibly

    print("\n" + "-" * 50)
    print("Done. Open http://localhost:8000/api/sessions to inspect all sessions.")
    print("Or open http://localhost:5173 for the visual debugger UI.")


if __name__ == "__main__":
    asyncio.run(main())
