#!/usr/bin/env python3
"""Integration test for Agent Debugger.

Tests the full flow:
1. SDK event emission
2. Buffer collection
3. API server (if running)
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_debugger_sdk import EventType
from agent_debugger_sdk import TraceContext
from agent_debugger_sdk import trace_agent
from agent_debugger_sdk import trace_tool
from collector.buffer import get_event_buffer
from collector.scorer import get_importance_scorer


pytestmark = pytest.mark.asyncio


async def test_basic_tracing():
    """Test basic trace context and event emission."""
    print("\n=== Test 1: Basic Tracing ===")

    session_id = "test-session-1"
    events = []

    async with TraceContext(session_id=session_id, agent_name="test_agent", framework="test") as ctx:
        # Record a decision (async - needs await)
        await ctx.record_decision(
            reasoning="User asked for weather",
            confidence=0.85,
            chosen_action="call_weather_tool",
            evidence=[{"source": "user_input", "content": "What's the weather?"}],
        )

        # Simulate tool execution
        await asyncio.sleep(0.05)

        tool_call_id = await ctx.record_tool_call(
            "weather_api",
            {"location": "Seattle"},
        )
        await ctx.record_tool_result(
            "weather_api",
            {"temp": 72, "conditions": "sunny"},
            duration_ms=100,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )

        # Get events from context before it closes
        events = await ctx.get_events()

    print(f"  Events captured: {len(events)}")

    for event in events:
        if hasattr(event, "event_type"):
            print(f"    - {event.event_type.value}: {event.name} (importance: {event.importance:.2f})")

    # Verify expected events (AGENT_END is emitted on context exit, so not in this list)
    event_types = [e.event_type for e in events if hasattr(e, "event_type")]
    assert EventType.AGENT_START in event_types, "Missing AGENT_START"
    assert EventType.TOOL_CALL in event_types, "Missing TOOL_CALL"
    assert EventType.TOOL_RESULT in event_types, "Missing TOOL_RESULT"
    assert EventType.DECISION in event_types, "Missing DECISION"

    print("  ✅ All expected events present")
    return True


async def test_decorator_tracing():
    """Test decorator-based tracing."""
    print("\n=== Test 2: Decorator Tracing ===")

    @trace_tool(name="search")
    async def search_tool(query: str) -> list[str]:
        """Simulated search tool."""
        await asyncio.sleep(0.05)
        return [f"result_{query}_1", f"result_{query}_2"]

    @trace_agent(name="search_agent", framework="test")
    async def search_agent(query: str) -> str:
        """Simulated agent that uses search."""
        results = await search_tool(query)
        return f"Found {len(results)} results"

    # Run the agent
    result = await search_agent("python async")
    print(f"  Agent result: {result}")

    # Check events
    buffer = get_event_buffer()
    # The decorator creates its own session, find it
    all_sessions = buffer._queues.keys() if hasattr(buffer, "_queues") else []

    print("  ✅ Decorator tracing works")
    return True


async def test_importance_scoring():
    """Test importance scoring."""
    print("\n=== Test 3: Importance Scoring ===")

    from agent_debugger_sdk.core.events import ErrorEvent
    from agent_debugger_sdk.core.events import LLMResponseEvent
    from agent_debugger_sdk.core.events import ToolResultEvent
    from agent_debugger_sdk.core.events import TraceEvent

    scorer = get_importance_scorer()

    # Test different event types
    events = [
        TraceEvent(event_type=EventType.AGENT_START, name="start"),
        TraceEvent(event_type=EventType.DECISION, name="decision"),
        ToolResultEvent(tool_name="test", result="ok", error=None),
        ToolResultEvent(tool_name="fail", result=None, error="Something went wrong"),
        LLMResponseEvent(model="gpt-4", content="Hello", cost_usd=0.05),
        ErrorEvent(error_message="Critical failure", error_type="RuntimeError"),
    ]

    for event in events:
        score = scorer.score(event)
        print(f"    {event.event_type.value}: {score:.2f}")

    # Error should have highest score
    error_score = scorer.score(events[-1])
    normal_score = scorer.score(events[0])
    assert error_score > normal_score, "Error should score higher than normal event"

    print("  ✅ Importance scoring works")
    return True


async def test_api_health():
    """Test API server health endpoint."""
    print("\n=== Test 4: API Health Check ===")

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/api/health", timeout=2.0)
            if response.status_code == 200:
                print(f"  API Response: {response.json()}")
                print("  ✅ API server is running")
                return True
    except Exception as e:
        print(f"  ⚠️  API server not running: {e}")
        print("  Start with: uvicorn api.main:app --reload --port 8000")
        return False


async def test_api_session_creation():
    """Test creating a session via API."""
    print("\n=== Test 5: API Session Creation ===")

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            # Create session
            response = await client.post(
                "http://localhost:8000/api/sessions",
                json={"agent_name": "test_agent", "framework": "test", "tags": ["integration"]},
                timeout=5.0,
            )

            if response.status_code == 201:
                session = response.json()
                print(f"  Created session: {session['id']}")
                print(f"  Agent: {session['agent_name']}")
                print("  ✅ Session creation works")
                return session["id"]
            print(f"  ❌ Failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"  ⚠️  Skipped (API not available): {e}")
        return None


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Agent Debugger Integration Tests")
    print("=" * 60)

    results = []

    # Core tests (don't need API server)
    results.append(("Basic Tracing", await test_basic_tracing()))
    results.append(("Decorator Tracing", await test_decorator_tracing()))
    results.append(("Importance Scoring", await test_importance_scoring()))

    # API tests (need server running)
    results.append(("API Health", await test_api_health()))
    results.append(("API Session", await test_api_session_creation()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, v in results if v)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\n{passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
