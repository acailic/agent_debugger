"""Regression tests to catch known issues early in CI."""

from __future__ import annotations


class TestSDKImports:
    """Tests that SDK imports work correctly."""

    def test_import_main_sdk_module(self):
        import agent_debugger_sdk

        assert agent_debugger_sdk is not None

    def test_import_events_package(self):
        from agent_debugger_sdk.core.events import (
            EVENT_TYPE_REGISTRY,
            AgentTurnEvent,
            BehaviorAlertEvent,
            Checkpoint,
            DecisionEvent,
            ErrorEvent,
            EventType,
            LLMRequestEvent,
            LLMResponseEvent,
            PolicyViolationEvent,
            PromptPolicyEvent,
            RefusalEvent,
            SafetyCheckEvent,
            Session,
            ToolCallEvent,
            ToolResultEvent,
            TraceEvent,
        )

        # All imports should be available
        assert all(
            [
                AgentTurnEvent,
                BehaviorAlertEvent,
                Checkpoint,
                DecisionEvent,
                ErrorEvent,
                EVENT_TYPE_REGISTRY,
                EventType,
                LLMRequestEvent,
                LLMResponseEvent,
                PolicyViolationEvent,
                PromptPolicyEvent,
                RefusalEvent,
                SafetyCheckEvent,
                Session,
                ToolCallEvent,
                ToolResultEvent,
                TraceEvent,
            ]
        )

    def test_import_checkpoint_module(self):
        from agent_debugger_sdk.checkpoints import (
            BaseCheckpointState,
            CustomCheckpointState,
            LangChainCheckpointState,
        )

        assert all([BaseCheckpointState, CustomCheckpointState, LangChainCheckpointState])

    def test_import_config_module(self):
        from agent_debugger_sdk.config import get_config

        assert callable(get_config)

    def test_no_import_cycles(self):
        import agent_debugger_sdk
        from agent_debugger_sdk.auto_patch import registry
        from agent_debugger_sdk.checkpoints import schemas
        from agent_debugger_sdk.core import events

        assert all([agent_debugger_sdk, events, schemas, registry])


class TestEventSerialization:
    """Tests for event serialization regressions."""

    def test_event_to_dict_json_serializable(self):
        import json

        from agent_debugger_sdk.core.events import ToolCallEvent

        event = ToolCallEvent(id="test-1", session_id="session-1", tool_name="search", arguments={"query": "test"})
        data = event.to_dict()
        json_str = json.dumps(data)
        assert json_str is not None

    def test_event_from_dict_round_trip(self):
        from agent_debugger_sdk.core.events import EventType, TraceEvent

        original = TraceEvent(
            id="round-trip-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            name="test",
        )
        data = original.to_dict()
        restored = TraceEvent.from_dict(data)
        assert restored.id == original.id
        assert restored.session_id == original.session_id
        assert restored.event_type == original.event_type


class TestEventTypeRegistry:
    """Tests for event type registry regressions."""

    def test_registry_complete(self):
        from agent_debugger_sdk.core.events import EVENT_TYPE_REGISTRY, EventType

        expected = {
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.LLM_REQUEST,
            EventType.LLM_RESPONSE,
            EventType.DECISION,
            EventType.SAFETY_CHECK,
            EventType.REFUSAL,
            EventType.POLICY_VIOLATION,
            EventType.PROMPT_POLICY,
            EventType.AGENT_TURN,
            EventType.BEHAVIOR_ALERT,
            EventType.ERROR,
        }
        for et in expected:
            assert et in EVENT_TYPE_REGISTRY, f"{et} missing from registry"

    def test_registry_returns_correct_classes(self):
        from agent_debugger_sdk.core.events import (
            EVENT_TYPE_REGISTRY,
            DecisionEvent,
            ErrorEvent,
            EventType,
            ToolCallEvent,
        )

        assert EVENT_TYPE_REGISTRY[EventType.TOOL_CALL] is ToolCallEvent
        assert EVENT_TYPE_REGISTRY[EventType.DECISION] is DecisionEvent
        assert EVENT_TYPE_REGISTRY[EventType.ERROR] is ErrorEvent


class TestAPIContractBasics:
    """Basic API contract tests."""

    def test_session_schema_has_required_fields(self):
        from agent_debugger_sdk.core.events import Session

        assert hasattr(Session, "__dataclass_fields__")
        fields = Session.__dataclass_fields__
        assert "id" in fields
        assert "agent_name" in fields
        assert "framework" in fields

    def test_checkpoint_schema_has_required_fields(self):
        from agent_debugger_sdk.core.events import Checkpoint

        assert hasattr(Checkpoint, "__dataclass_fields__")
        fields = Checkpoint.__dataclass_fields__
        assert "id" in fields
        assert "session_id" in fields
        assert "event_id" in fields


class TestKnownIssuePatterns:
    """Tests for known issue patterns."""

    def test_no_duplicate_event_ids_in_benchmark(self):
        import asyncio

        from benchmarks import run_prompt_injection_session

        async def check():
            session = await run_prompt_injection_session("no-dup")
            ids = [e.id for e in session.events]
            assert len(ids) == len(set(ids)), "Duplicate event IDs found"

        asyncio.run(check())

    def test_event_type_enum_values_are_strings(self):
        from agent_debugger_sdk.core.events import EventType

        for et in EventType:
            assert isinstance(et.value, str), f"{et} value is not a string"
