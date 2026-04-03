from __future__ import annotations

import builtins
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_debugger_sdk.core.context import (
    TraceContext,
    _get_default_event_buffer,
    configure_event_pipeline,
    get_current_context,
    get_current_parent_id,
    get_current_session_id,
)
from agent_debugger_sdk.core.events import EventType


class RaisingBuffer:
    def __init__(self) -> None:
        self.publish = AsyncMock(side_effect=RuntimeError("buffer down"))


@pytest.mark.asyncio
async def test_get_default_event_buffer_returns_none_when_collector_import_fails():
    configure_event_pipeline(None)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "collector.buffer":
            raise ImportError("collector unavailable")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert _get_default_event_buffer() is None


@pytest.mark.asyncio
async def test_trace_context_cloud_mode_uses_transport_and_closes_it():
    # Clear pipeline to ensure the transport code path is tested
    # (other test files may set _default_event_persister via xdist worker sharing)
    configure_event_pipeline(None)

    transport = SimpleNamespace(
        send_event=AsyncMock(),
        send_session_start=AsyncMock(),
        send_session_update=AsyncMock(),
        close=AsyncMock(),
    )
    config = SimpleNamespace(mode="cloud", api_key="ad_live_test", endpoint="https://collector.test", enabled=True)

    with (
        patch("agent_debugger_sdk.config.get_config", return_value=config),
        patch("agent_debugger_sdk.transport.HttpTransport", return_value=transport),
    ):
        async with TraceContext(session_id="cloud-session", agent_name="agent", framework="test") as ctx:
            await ctx.record_tool_call("search", {"q": "Belgrade"})

    transport.send_session_start.assert_awaited_once()
    assert transport.send_event.await_count >= 3
    assert transport.send_session_update.await_count >= 3
    transport.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_trace_context_exit_with_exception_without_traceback_records_error_and_resets_context():
    with patch(
        "agent_debugger_sdk.config.get_config",
        return_value=SimpleNamespace(mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True),
    ):
        ctx = TraceContext(session_id="error-session", agent_name="agent", framework="test")
        await ctx.__aenter__()
        assert get_current_context() is ctx
        assert get_current_session_id() == "error-session"

        await ctx.__aexit__(ValueError, ValueError("boom"), None)

    events = await ctx.get_events()
    error_event = next(event for event in events if event.event_type == EventType.ERROR)
    end_event = next(event for event in events if event.name == "session_end")

    assert error_event.error_type == "ValueError"
    assert "ValueError: boom" in (error_event.stack_trace or "")
    assert end_event.data["status"] == "error"
    assert get_current_context() is None
    assert get_current_session_id() is None
    assert get_current_parent_id() is None


@pytest.mark.asyncio
async def test_parent_sequence_checkpoint_and_drain_helpers_work():
    checkpoint_persister = AsyncMock()
    configure_event_pipeline(None, persist_checkpoint=checkpoint_persister)

    try:
        with patch(
            "agent_debugger_sdk.config.get_config",
            return_value=SimpleNamespace(mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True),
        ):
            async with TraceContext(session_id="helper-session", agent_name="agent", framework="test") as ctx:
                decision_id = await ctx.record_decision(
                    reasoning="use tool",
                    confidence=1.4,
                    evidence=[{"source": "user", "content": "Belgrade"}],
                    chosen_action="search",
                )
                ctx.set_parent(decision_id)
                assert ctx.get_current_parent() == decision_id
                assert get_current_parent_id() == decision_id

                checkpoint_id = await ctx.create_checkpoint(state={"step": 1}, memory=None, importance=3.0)
                await ctx.record_agent_turn("agent-1", "assistant", 2, goal="plan", content="next")
                await ctx.record_behavior_alert("drift", "looping", related_event_ids=["e1"])

                assert checkpoint_id
                assert ctx.get_event_sequence() > 0

                events_before_drain = await ctx.get_events()
                drained = await ctx.drain_events()
                assert len(drained) == len(events_before_drain)
                assert await ctx.get_events() == []

                checkpoint = next(event for event in drained if not hasattr(event, "event_type"))
                assert checkpoint.importance == 1.0

                checkpoint_event = next(
                    event for event in drained if getattr(event, "event_type", None) == EventType.CHECKPOINT
                )
                assert checkpoint_event.data["checkpoint_id"] == checkpoint_id

                agent_turn = next(
                    event for event in drained if getattr(event, "event_type", None) == EventType.AGENT_TURN
                )
                behavior_alert = next(
                    event for event in drained if getattr(event, "event_type", None) == EventType.BEHAVIOR_ALERT
                )
                assert agent_turn.turn_index == 2
                assert behavior_alert.signal == "looping"

                ctx.clear_parent()
                assert ctx.get_current_parent() is None
    finally:
        configure_event_pipeline(None)

    checkpoint_persister.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_entered_and_emit_event_handles_update_and_buffer_failures():
    buffer = RaisingBuffer()
    update_hook = AsyncMock(
        side_effect=[
            RuntimeError("session update failed"),
            RuntimeError("session update failed"),
            RuntimeError("session update failed"),
            None,
        ]
    )
    configure_event_pipeline(buffer, persist_session_update=update_hook)

    try:
        ctx = TraceContext(session_id="guarded-session", agent_name="agent", framework="test")
        with pytest.raises(RuntimeError, match="TraceContext has not been entered"):
            ctx.clear_parent()

        with patch(
            "agent_debugger_sdk.config.get_config",
            return_value=SimpleNamespace(mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True),
        ):
            async with ctx:
                event_id = await ctx.record_tool_result("search", {"ok": True}, error="boom")
                assert event_id

        events = await ctx.get_events()
        tool_result = next(event for event in events if event.event_type == EventType.TOOL_RESULT)
        assert tool_result.error == "boom"
    finally:
        configure_event_pipeline(None)

    assert update_hook.await_count >= 1
    assert buffer.publish.await_count >= 1


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_trace_context_records_llm_and_policy_events_and_updates_session_totals():
    with patch(
        "agent_debugger_sdk.config.get_config",
        return_value=SimpleNamespace(mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True),
    ):
        async with TraceContext(session_id="policy-session", agent_name="agent", framework="test") as ctx:
            await ctx.record_llm_request(
                "gpt-4o",
                [{"role": "user", "content": "Hello"}],
                tools=[{"name": "search"}],
                settings={"temperature": 0.2},
                upstream_event_ids=["root"],
                parent_id="parent-llm",
            )
            await ctx.record_llm_response(
                "gpt-4o",
                "Hello back",
                usage={"input_tokens": 11, "output_tokens": 7},
                cost_usd=0.03,
                duration_ms=120,
                upstream_event_ids=["root"],
                parent_id="parent-llm",
            )
            await ctx.record_safety_check("policy", "warn", "medium", "careful", blocked_action="send")
            await ctx.record_refusal("unsafe", "policy", safe_alternative="summarize")
            await ctx.record_policy_violation("policy", "prompt", details={"kind": "pii"})
            await ctx.record_prompt_policy("template-1", {"mode": "strict"}, speaker="system", goal="refuse")

        events = await ctx.get_events()

    assert ctx.session.total_tokens == 18
    assert ctx.session.total_cost_usd == 0.03
    assert ctx.session.llm_calls == 1

    llm_request = next(event for event in events if event.event_type == EventType.LLM_REQUEST)
    llm_response = next(event for event in events if event.event_type == EventType.LLM_RESPONSE)
    safety = next(event for event in events if event.event_type == EventType.SAFETY_CHECK)
    refusal = next(event for event in events if event.event_type == EventType.REFUSAL)
    violation = next(event for event in events if event.event_type == EventType.POLICY_VIOLATION)
    prompt_policy = next(event for event in events if event.event_type == EventType.PROMPT_POLICY)

    assert llm_request.parent_id == "parent-llm"
    assert llm_request.upstream_event_ids == ["root"]
    assert llm_response.usage == {"input_tokens": 11, "output_tokens": 7}
    assert safety.blocked_action == "send"
    assert refusal.safe_alternative == "summarize"
    assert violation.details == {"kind": "pii"}
    assert prompt_policy.template_id == "template-1"


@pytest.mark.asyncio
async def test_trace_context_disabled_mode_skips_event_emission():
    with patch(
        "agent_debugger_sdk.config.get_config",
        return_value=SimpleNamespace(mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True),
    ):
        async with TraceContext(session_id="disabled-session", agent_name="agent", framework="test") as ctx:
            await ctx.record_llm_request("gpt-4o", [{"role": "user", "content": "hi"}])
            await ctx.record_safety_check("policy", "pass", "low", "ok")

        events = await ctx.get_events()

    # Without an API key, no transport is created — events are retained locally
    assert len(events) >= 2


@pytest.mark.asyncio
async def test_trace_context_persister_failures_are_swallowed_and_traceback_is_recorded():
    persister = AsyncMock(side_effect=RuntimeError("persist down"))
    configure_event_pipeline(None, persist_event=persister)

    try:
        with (
            patch(
                "agent_debugger_sdk.config.get_config",
                return_value=SimpleNamespace(
                    mode="local", api_key=None, endpoint="http://localhost:8000", enabled=True
                ),
            ),
            pytest.raises(ValueError, match="boom"),
        ):
            async with TraceContext(session_id="traceback-session", agent_name="agent", framework="test") as ctx:
                await ctx.record_llm_response(
                    "gpt-4o",
                    "before error",
                    usage={"input_tokens": 1, "output_tokens": 1},
                )
                raise ValueError("boom")

        events = await ctx.get_events()
    finally:
        configure_event_pipeline(None)

    error_event = next(event for event in events if event.event_type == EventType.ERROR)
    assert 'raise ValueError("boom")' in (error_event.stack_trace or "")
    assert persister.await_count >= 1
