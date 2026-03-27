"""Tests for SDK core recorders module."""

from __future__ import annotations

import pytest

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import (
    RiskLevel,
    SafetyOutcome,
)


class MockEmitter:
    """Mock emitter to capture emitted events."""

    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


class TestRecordDecision:
    """Tests for record_decision method."""

    @pytest.mark.asyncio
    async def test_records_decision_with_required_fields(self):
        ctx = TraceContext(session_id="test-session")
        async with ctx:
            event_id = await ctx.record_decision(
                reasoning="User asked for weather",
                confidence=0.85,
                evidence=[{"source": "input", "content": "weather?"}],
                chosen_action="call_weather_tool",
            )
            assert event_id is not None
            assert len(event_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_clamps_confidence_to_valid_range(self):
        ctx = TraceContext()
        async with ctx:
            # Test clamping high value
            await ctx.record_decision(
                reasoning="test",
                confidence=1.5,  # Above 1.0
                evidence=[],
                chosen_action="act",
            )
            # Test clamping low value
            await ctx.record_decision(
                reasoning="test",
                confidence=-0.5,  # Below 0.0
                evidence=[],
                chosen_action="act",
            )
            events = await ctx.get_events()
            decisions = [e for e in events if hasattr(e, "confidence")]
            for d in decisions:
                assert 0.0 <= d.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_stores_evidence_event_ids(self):
        ctx = TraceContext()
        async with ctx:
            _ = await ctx.record_decision(
                reasoning="test",
                confidence=0.5,
                evidence=[],
                chosen_action="act",
                evidence_event_ids=["ev-1", "ev-2"],
            )
            events = await ctx.get_events()
            decision = next(e for e in events if hasattr(e, "evidence_event_ids"))
            assert "ev-1" in decision.evidence_event_ids

    @pytest.mark.asyncio
    async def test_stores_alternatives(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_decision(
                reasoning="test",
                confidence=0.5,
                evidence=[],
                chosen_action="act",
                alternatives=[{"action": "alt", "score": 0.3}],
            )
            events = await ctx.get_events()
            decision = next(e for e in events if hasattr(e, "alternatives") and e.alternatives)
            assert len(decision.alternatives) == 1

    @pytest.mark.asyncio
    async def test_raises_before_enter(self):
        ctx = TraceContext()
        with pytest.raises(RuntimeError, match="has not been entered"):
            await ctx.record_decision(
                reasoning="test",
                confidence=0.5,
                evidence=[],
                chosen_action="act",
            )


class TestRecordToolCall:
    """Tests for record_tool_call method."""

    @pytest.mark.asyncio
    async def test_records_tool_call(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_tool_call(
                tool_name="search",
                arguments={"query": "test"},
            )
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_stores_arguments(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_tool_call(
                tool_name="search",
                arguments={"query": "test", "limit": 10},
            )
            events = await ctx.get_events()
            tool_call = next(e for e in events if hasattr(e, "tool_name") and not hasattr(e, "result"))
            assert tool_call.arguments["query"] == "test"
            assert tool_call.arguments["limit"] == 10

    @pytest.mark.asyncio
    async def test_accepts_custom_name(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_tool_call(
                tool_name="search",
                arguments={},
                name="custom_search_call",
            )
            events = await ctx.get_events()
            tool_call = next(e for e in events if hasattr(e, "tool_name"))
            assert tool_call.name == "custom_search_call"


class TestRecordToolResult:
    """Tests for record_tool_result method."""

    @pytest.mark.asyncio
    async def test_records_successful_result(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_tool_result(
                tool_name="search",
                result={"data": "found"},
                duration_ms=100.0,
            )
            events = await ctx.get_events()
            result_event = next(e for e in events if hasattr(e, "result"))
            assert result_event.result == {"data": "found"}
            assert result_event.duration_ms == 100.0
            assert result_event.error is None

    @pytest.mark.asyncio
    async def test_records_error_result(self):
        ctx = TraceContext()
        async with ctx:
            initial_errors = ctx.session.errors
            await ctx.record_tool_result(
                tool_name="search",
                result=None,
                error="Connection failed",
            )
            assert ctx.session.errors == initial_errors + 1

    @pytest.mark.asyncio
    async def test_higher_importance_on_error(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_tool_result(tool_name="t1", result={"ok": True})
            await ctx.record_tool_result(tool_name="t2", result=None, error="failed")

            events = await ctx.get_events()
            results = [e for e in events if hasattr(e, "result")]
            success = next(e for e in results if e.error is None)
            error = next(e for e in results if e.error is not None)
            assert error.importance > success.importance

    @pytest.mark.asyncio
    async def test_increments_tool_calls_counter(self):
        ctx = TraceContext()
        async with ctx:
            initial_calls = ctx.session.tool_calls
            await ctx.record_tool_result(tool_name="t", result={})
            assert ctx.session.tool_calls == initial_calls + 1


class TestRecordLLMRequest:
    """Tests for record_llm_request method."""

    @pytest.mark.asyncio
    async def test_records_request_with_messages(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_llm_request(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
            )
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_stores_tools_and_settings(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_llm_request(
                model="gpt-4",
                messages=[],
                tools=[{"type": "function", "name": "search"}],
                settings={"temperature": 0.7},
            )
            events = await ctx.get_events()
            req = next(e for e in events if hasattr(e, "messages"))
            assert len(req.tools) == 1
            assert req.settings["temperature"] == 0.7


class TestRecordLLMResponse:
    """Tests for record_llm_response method."""

    @pytest.mark.asyncio
    async def test_records_response_with_content(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_llm_response(
                model="gpt-4",
                content="Hello back!",
            )
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_stores_usage_and_cost(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_llm_response(
                model="gpt-4",
                content="response",
                usage={"input_tokens": 100, "output_tokens": 50},
                cost_usd=0.05,
                duration_ms=500.0,
            )
            events = await ctx.get_events()
            resp = next(e for e in events if hasattr(e, "content") and e.content == "response")
            assert resp.usage["input_tokens"] == 100
            assert resp.cost_usd == 0.05


class TestRecordError:
    """Tests for record_error method."""

    @pytest.mark.asyncio
    async def test_records_error_with_stack_trace(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_error(
                error_type="ValueError",
                error_message="Invalid value",
                stack_trace="Traceback...",
            )
            events = await ctx.get_events()
            error = next(e for e in events if hasattr(e, "error_type"))
            assert error.error_type == "ValueError"
            assert error.stack_trace is not None

    @pytest.mark.asyncio
    async def test_increments_error_counter(self):
        ctx = TraceContext()
        async with ctx:
            initial = ctx.session.errors
            await ctx.record_error(
                error_type="ValueError",
                error_message="test",
            )
            assert ctx.session.errors == initial + 1


class TestRecordSafetyCheck:
    """Tests for record_safety_check method."""

    @pytest.mark.asyncio
    async def test_records_safety_check_pass(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_safety_check(
                policy_name="content_filter",
                outcome=SafetyOutcome.PASS,
                risk_level=RiskLevel.LOW,
                rationale="No issues",
            )
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_records_safety_check_fail(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_safety_check(
                policy_name="harmful_content",
                outcome=SafetyOutcome.FAIL,
                risk_level=RiskLevel.HIGH,
                rationale="Detected harmful content",
                blocked_action="generate_response",
            )
            events = await ctx.get_events()
            check = next(e for e in events if hasattr(e, "policy_name"))
            assert check.outcome == SafetyOutcome.FAIL
            assert check.blocked_action == "generate_response"

    @pytest.mark.asyncio
    async def test_accepts_string_outcome_and_risk(self):
        ctx = TraceContext()
        async with ctx:
            await ctx.record_safety_check(
                policy_name="test",
                outcome="pass",  # String instead of enum
                risk_level="low",  # String instead of enum
                rationale="test",
            )
            events = await ctx.get_events()
            check = next(e for e in events if hasattr(e, "policy_name"))
            assert check.outcome == SafetyOutcome.PASS


class TestRecordRefusal:
    """Tests for record_refusal method."""

    @pytest.mark.asyncio
    async def test_records_refusal(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_refusal(
                reason="Request violates policy",
                policy_name="harmful_content",
                risk_level=RiskLevel.HIGH,
                blocked_action="generate_harmful",
                safe_alternative="Provide educational info",
            )
            assert event_id is not None
            events = await ctx.get_events()
            refusal = next(e for e in events if hasattr(e, "safe_alternative"))
            assert refusal.reason == "Request violates policy"


class TestRecordPolicyViolation:
    """Tests for record_policy_violation method."""

    @pytest.mark.asyncio
    async def test_records_violation(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_policy_violation(
                policy_name="rate_limit",
                violation_type="excessive_requests",
                severity=RiskLevel.MEDIUM,
                details={"count": 100},
            )
            assert event_id is not None
            events = await ctx.get_events()
            violation = next(e for e in events if hasattr(e, "violation_type"))
            assert violation.violation_type == "excessive_requests"


class TestRecordPromptPolicy:
    """Tests for record_prompt_policy method."""

    @pytest.mark.asyncio
    async def test_records_prompt_policy(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_prompt_policy(
                template_id="v1_standard",
                policy_parameters={"creativity": 0.8},
                speaker="assistant",
                state_summary="Processing",
                goal="Help user",
            )
            assert event_id is not None
            events = await ctx.get_events()
            policy = next(e for e in events if hasattr(e, "template_id"))
            assert policy.template_id == "v1_standard"


class TestRecordAgentTurn:
    """Tests for record_agent_turn method."""

    @pytest.mark.asyncio
    async def test_records_agent_turn(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_agent_turn(
                agent_id="agent-1",
                speaker="assistant",
                turn_index=5,
                goal="Answer question",
                content="Here is the answer",
            )
            assert event_id is not None
            events = await ctx.get_events()
            turn = next(e for e in events if hasattr(e, "turn_index"))
            assert turn.turn_index == 5


class TestRecordBehaviorAlert:
    """Tests for record_behavior_alert method."""

    @pytest.mark.asyncio
    async def test_records_behavior_alert(self):
        ctx = TraceContext()
        async with ctx:
            event_id = await ctx.record_behavior_alert(
                alert_type="loop_detected",
                signal="repeated_tool_calls",
                severity=RiskLevel.HIGH,
                related_event_ids=["e1", "e2"],
            )
            assert event_id is not None
            events = await ctx.get_events()
            alert = next(e for e in events if hasattr(e, "alert_type"))
            assert alert.alert_type == "loop_detected"


class TestRecorderIntegration:
    """Integration tests for recorder methods."""

    @pytest.mark.asyncio
    async def test_chained_operations(self):
        """Test a typical sequence of operations."""
        ctx = TraceContext(session_id="integration-test")
        async with ctx:
            # Make a decision
            _ = await ctx.record_decision(
                reasoning="Need to search",
                confidence=0.9,
                evidence=[{"source": "user", "content": "find X"}],
                chosen_action="search",
            )

            # Call a tool
            await ctx.record_tool_call("search", {"query": "X"})

            # Get result
            await ctx.record_tool_result("search", {"results": []})

            # Verify all events recorded
            events = await ctx.get_events()
            assert any(hasattr(e, "confidence") for e in events)  # decision
            assert any(hasattr(e, "tool_name") for e in events)  # tool events

    @pytest.mark.asyncio
    async def test_parent_child_relationships(self):
        """Test that parent_id is propagated correctly."""
        ctx = TraceContext()
        async with ctx:
            # Set a parent
            parent_id = await ctx.record_decision(
                reasoning="parent",
                confidence=0.5,
                evidence=[],
                chosen_action="act",
            )
            ctx.set_parent(parent_id)

            # Child should have parent_id
            child_id = await ctx.record_tool_call("tool", {})
            events = await ctx.get_events()
            child_event = next(e for e in events if e.id == child_id)
            assert child_event.parent_id == parent_id
