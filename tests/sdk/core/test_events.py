"""Tests for SDK core events module."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import (
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
    RiskLevel,
    SafetyCheckEvent,
    SafetyOutcome,
    Session,
    SessionStatus,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
    _serialize_field_value,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        assert EventType.AGENT_START.value == "agent_start"
        assert EventType.AGENT_END.value == "agent_end"
        assert EventType.DECISION.value == "decision"
        assert EventType.TOOL_CALL.value == "tool_call"
        assert EventType.TOOL_RESULT.value == "tool_result"
        assert EventType.LLM_REQUEST.value == "llm_request"
        assert EventType.LLM_RESPONSE.value == "llm_response"
        assert EventType.ERROR.value == "error"
        assert EventType.CHECKPOINT.value == "checkpoint"


class TestSessionStatus:
    """Tests for SessionStatus enum."""

    def test_status_values(self):
        assert SessionStatus.RUNNING.value == "running"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.ERROR.value == "error"


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestSafetyOutcome:
    """Tests for SafetyOutcome enum."""

    def test_outcome_values(self):
        assert SafetyOutcome.PASS.value == "pass"
        assert SafetyOutcome.FAIL.value == "fail"
        assert SafetyOutcome.WARN.value == "warn"
        assert SafetyOutcome.BLOCK.value == "block"


class TestSerializeFieldValue:
    """Tests for _serialize_field_value helper."""

    def test_serializes_datetime_to_iso(self):
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _serialize_field_value(now)
        assert "2024-01-15" in result

    def test_serializes_enum_to_value(self):
        result = _serialize_field_value(EventType.DECISION)
        assert result == "decision"

    def test_serializes_list(self):
        result = _serialize_field_value([1, 2, 3])
        assert result == [1, 2, 3]

    def test_serializes_dict(self):
        result = _serialize_field_value({"key": "value"})
        assert result == {"key": "value"}

    def test_passes_through_primitives(self):
        assert _serialize_field_value("string") == "string"
        assert _serialize_field_value(123) == 123
        assert _serialize_field_value(0.5) == 0.5
        assert _serialize_field_value(None) is None


class TestTraceEvent:
    """Tests for base TraceEvent class."""

    def test_creates_with_required_fields(self):
        event = TraceEvent(
            session_id="session-1",
            event_type=EventType.AGENT_START,
            name="start",
        )
        assert event.session_id == "session-1"
        assert event.event_type == EventType.AGENT_START
        assert event.name == "start"

    def test_auto_generates_id(self):
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.AGENT_START,
            name="start",
        )
        assert event.id is not None
        assert len(event.id) == 36  # UUID format

    def test_to_dict_includes_all_fields(self):
        event = TraceEvent(
            session_id="session-1",
            parent_id="parent-1",
            event_type=EventType.DECISION,
            name="decision",
            data={"key": "value"},
            importance=0.5,
        )
        d = event.to_dict()
        assert d["session_id"] == "session-1"
        assert d["parent_id"] == "parent-1"
        assert d["event_type"] == "decision"
        assert d["name"] == "decision"
        assert d["data"] == {"key": "value"}
        assert d["importance"] == 0.5

    def test_from_dict_recreates_event(self):
        original = TraceEvent(
            session_id="s1",
            parent_id="p1",
            event_type=EventType.TOOL_CALL,
            name="tool",
            data={"arg": "val"},
        )
        d = original.to_dict()
        recreated = TraceEvent.from_dict(d)
        assert recreated.session_id == original.session_id
        assert recreated.parent_id == original.parent_id
        assert recreated.event_type == original.event_type
        assert recreated.name == original.name


class TestSession:
    """Tests for Session dataclass."""

    def test_creates_with_all_fields(self):
        session = Session(
            id="session-1",
            agent_name="test_agent",
            framework="custom",
            config={"key": "value"},
            tags=["tag1", "tag2"],
        )
        assert session.id == "session-1"
        assert session.agent_name == "test_agent"
        assert session.framework == "custom"
        assert session.config == {"key": "value"}
        assert session.tags == ["tag1", "tag2"]

    def test_default_status_is_running(self):
        session = Session(id="s1")
        assert session.status == SessionStatus.RUNNING

    def test_default_counters_are_zero(self):
        session = Session(id="s1")
        assert session.tool_calls == 0
        assert session.errors == 0
        assert session.llm_calls == 0
        assert session.total_tokens == 0
        assert session.total_cost_usd == 0.0

    def test_to_dict_contains_all_fields(self):
        session = Session(
            id="s1",
            agent_name="agent",
            framework="framework",
            status=SessionStatus.COMPLETED,
        )
        d = session.to_dict()
        assert d["id"] == "s1"
        assert d["agent_name"] == "agent"
        assert d["framework"] == "framework"
        assert d["status"] == "completed"


class TestToolCallEvent:
    """Tests for ToolCallEvent."""

    def test_creates_with_arguments(self):
        event = ToolCallEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="search_call",
            tool_name="search",
            arguments={"query": "test"},
        )
        assert event.tool_name == "search"
        assert event.arguments == {"query": "test"}

    def test_serializes_correctly(self):
        event = ToolCallEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="call",
            tool_name="tool",
            arguments={},
        )
        d = event.to_dict()
        assert d["tool_name"] == "tool"
        assert d["arguments"] == {}


class TestToolResultEvent:
    """Tests for ToolResultEvent."""

    def test_creates_with_result(self):
        event = ToolResultEvent(
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="search_result",
            tool_name="search",
            result={"data": "found"},
            duration_ms=100.0,
        )
        assert event.result == {"data": "found"}
        assert event.duration_ms == 100.0

    def test_creates_with_error(self):
        event = ToolResultEvent(
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="result",
            tool_name="tool",
            result=None,
            error="Connection failed",
        )
        assert event.error == "Connection failed"


class TestDecisionEvent:
    """Tests for DecisionEvent."""

    def test_creates_with_all_fields(self):
        event = DecisionEvent(
            session_id="s1",
            event_type=EventType.DECISION,
            name="decision",
            reasoning="User asked for weather",
            confidence=0.85,
            evidence=[{"source": "input", "content": "What's the weather?"}],
            chosen_action="call_weather_tool",
            alternatives=[{"action": "ask_clarification", "score": 0.3}],
        )
        assert event.reasoning == "User asked for weather"
        assert event.confidence == 0.85
        assert len(event.evidence) == 1
        assert event.chosen_action == "call_weather_tool"

    def test_default_alternatives_empty(self):
        event = DecisionEvent(
            session_id="s1",
            event_type=EventType.DECISION,
            name="decision",
            reasoning="test",
            confidence=0.5,
            evidence=[],
            chosen_action="act",
        )
        assert event.alternatives == []


class TestLLMRequestEvent:
    """Tests for LLMRequestEvent."""

    def test_creates_with_messages(self):
        event = LLMRequestEvent(
            session_id="s1",
            event_type=EventType.LLM_REQUEST,
            name="request",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[{"type": "function", "name": "search"}],
            settings={"temperature": 0.7},
        )
        assert event.model == "gpt-4"
        assert len(event.messages) == 1
        assert len(event.tools) == 1
        assert event.settings["temperature"] == 0.7


class TestLLMResponseEvent:
    """Tests for LLMResponseEvent."""

    def test_creates_with_content(self):
        event = LLMResponseEvent(
            session_id="s1",
            event_type=EventType.LLM_RESPONSE,
            name="response",
            model="gpt-4",
            content="Hello!",
            usage={"input_tokens": 10, "output_tokens": 5},
            cost_usd=0.001,
            duration_ms=500.0,
        )
        assert event.content == "Hello!"
        assert event.usage["input_tokens"] == 10
        assert event.cost_usd == 0.001

    def test_default_tool_calls_empty(self):
        event = LLMResponseEvent(
            session_id="s1",
            event_type=EventType.LLM_RESPONSE,
            name="response",
            model="gpt-4",
            content="Hi",
        )
        assert event.tool_calls == []


class TestSafetyCheckEvent:
    """Tests for SafetyCheckEvent."""

    def test_creates_with_policy(self):
        event = SafetyCheckEvent(
            session_id="s1",
            name="check",
            policy_name="content_filter",
            outcome=SafetyOutcome.PASS,
            risk_level=RiskLevel.LOW,
            rationale="No issues detected",
        )
        assert event.policy_name == "content_filter"
        assert event.outcome == SafetyOutcome.PASS
        assert event.risk_level == RiskLevel.LOW


class TestRefusalEvent:
    """Tests for RefusalEvent."""

    def test_creates_with_reason(self):
        event = RefusalEvent(
            session_id="s1",
            name="refusal",
            reason="Request violates policy",
            policy_name="harmful_content",
            risk_level=RiskLevel.HIGH,
            blocked_action="generate_harmful_content",
            safe_alternative="Provide educational information instead",
        )
        assert event.reason == "Request violates policy"
        assert event.safe_alternative is not None


class TestPolicyViolationEvent:
    """Tests for PolicyViolationEvent."""

    def test_creates_with_violation_type(self):
        event = PolicyViolationEvent(
            session_id="s1",
            name="violation",
            policy_name="rate_limit",
            violation_type="excessive_requests",
            severity=RiskLevel.MEDIUM,
            details={"count": 100, "limit": 10},
        )
        assert event.violation_type == "excessive_requests"
        assert event.severity == RiskLevel.MEDIUM


class TestPromptPolicyEvent:
    """Tests for PromptPolicyEvent."""

    def test_creates_with_parameters(self):
        event = PromptPolicyEvent(
            session_id="s1",
            name="policy",
            template_id="v1_standard",
            policy_parameters={"creativity": 0.8, "strictness": 0.3},
            speaker="assistant",
            state_summary="Processing user request",
            goal="Answer helpfully",
        )
        assert event.template_id == "v1_standard"
        assert event.policy_parameters["creativity"] == 0.8


class TestErrorEvent:
    """Tests for ErrorEvent."""

    def test_creates_with_stack_trace(self):
        event = ErrorEvent(
            session_id="s1",
            event_type=EventType.ERROR,
            name="error",
            error_type="ValueError",
            error_message="Invalid input",
            stack_trace="Traceback...\n  File ...",
        )
        assert event.error_type == "ValueError"
        assert event.stack_trace is not None

    def test_creates_without_stack_trace(self):
        event = ErrorEvent(
            session_id="s1",
            event_type=EventType.ERROR,
            name="error",
            error_type="ValueError",
            error_message="Invalid input",
        )
        assert event.stack_trace is None


class TestAgentTurnEvent:
    """Tests for AgentTurnEvent."""

    def test_creates_with_turn_info(self):
        event = AgentTurnEvent(
            session_id="s1",
            name="turn",
            agent_id="agent-1",
            speaker="assistant",
            turn_index=5,
            goal="Answer question",
            content="Here is the answer",
        )
        assert event.agent_id == "agent-1"
        assert event.turn_index == 5


class TestBehaviorAlertEvent:
    """Tests for BehaviorAlertEvent."""

    def test_creates_with_alert_info(self):
        event = BehaviorAlertEvent(
            session_id="s1",
            name="alert",
            alert_type="loop_detected",
            signal="repeated_tool_calls",
            severity=RiskLevel.HIGH,
            related_event_ids=["e1", "e2", "e3"],
        )
        assert event.alert_type == "loop_detected"
        assert event.severity == RiskLevel.HIGH


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_creates_with_state(self):
        cp = Checkpoint(
            id="cp-1",
            session_id="s1",
            event_id="e1",
            sequence=1,
            state={"step": 5, "data": "processed"},
            memory={"history": []},
            timestamp=datetime.now(timezone.utc),
            importance=0.8,
        )
        assert cp.id == "cp-1"
        assert cp.state["step"] == 5
        assert cp.importance == 0.8

    def test_default_memory_empty(self):
        cp = Checkpoint(
            id="cp-1",
            session_id="s1",
            event_id="e1",
            sequence=1,
            state={},
            timestamp=datetime.now(timezone.utc),
            importance=0.5,
        )
        assert cp.memory == {}


class TestEventSerialization:
    """Tests for event serialization edge cases."""

    def test_serializes_datetime_to_iso(self):
        now = datetime.now(timezone.utc)
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.AGENT_START,
            name="start",
            timestamp=now,
        )
        d = event.to_dict()
        assert "timestamp" in d

    def test_handles_nested_data(self):
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.AGENT_START,
            name="start",
            data={
                "nested": {"deep": {"value": 123}},
                "list": [1, 2, 3],
            },
        )
        d = event.to_dict()
        assert d["data"]["nested"]["deep"]["value"] == 123
        assert d["data"]["list"] == [1, 2, 3]
