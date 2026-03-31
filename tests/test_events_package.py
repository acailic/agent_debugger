"""Comprehensive tests for the SDK events package.

Tests cover:
- EventType registry and lazy loading
- All 13 event types and their fields
- Serialization and deserialization
- Event hierarchy and inheritance
"""

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import (
    BASE_EVENT_FIELDS,
    EVENT_TYPE_REGISTRY,
    AgentTurnEvent,
    BehaviorAlertEvent,
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
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)


class TestEventTypeRegistry:
    """Tests for the EventType registry and lazy loading."""

    def test_registry_has_all_event_types(self):
        """Registry should contain mappings for all registered event types."""
        # Access the registry to trigger lazy loading
        event_types = [
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
        ]

        for event_type in event_types:
            assert event_type in EVENT_TYPE_REGISTRY, f"EventType {event_type} should be in registry"
            assert EVENT_TYPE_REGISTRY[event_type] is not None

    def test_registry_returns_correct_class_for_tool_call(self):
        """Registry should return ToolCallEvent for TOOL_CALL event type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.TOOL_CALL]
        assert event_cls is ToolCallEvent

    def test_registry_returns_correct_class_for_decision(self):
        """Registry should return DecisionEvent for DECISION event type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.DECISION]
        assert event_cls is DecisionEvent

    def test_registry_returns_correct_class_for_safety_check(self):
        """Registry should return SafetyCheckEvent for SAFETY_CHECK event type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.SAFETY_CHECK]
        assert event_cls is SafetyCheckEvent


class TestEventTypes:
    """Tests for all 13 event types and their specific fields."""

    def test_tool_call_event_fields(self):
        """ToolCallEvent should have tool_name and arguments fields."""
        event = ToolCallEvent(
            session_id="test-session",
            tool_name="read_file",
            arguments={"path": "/tmp/test.txt"},
        )

        assert event.event_type == EventType.TOOL_CALL
        assert event.tool_name == "read_file"
        assert event.arguments == {"path": "/tmp/test.txt"}
        assert event.id is not None
        assert event.timestamp is not None

    def test_tool_result_event_fields(self):
        """ToolResultEvent should have tool_name, result, error, and duration_ms fields."""
        event = ToolResultEvent(
            session_id="test-session",
            tool_name="read_file",
            result="file contents here",
            duration_ms=150.5,
        )

        assert event.event_type == EventType.TOOL_RESULT
        assert event.tool_name == "read_file"
        assert event.result == "file contents here"
        assert event.error is None
        assert event.duration_ms == 150.5

    def test_tool_result_event_with_error(self):
        """ToolResultEvent should properly capture error information."""
        event = ToolResultEvent(
            session_id="test-session",
            tool_name="read_file",
            result=None,
            error="File not found: /tmp/test.txt",
            duration_ms=10.0,
        )

        assert event.error == "File not found: /tmp/test.txt"
        assert event.result is None

    def test_llm_request_event_fields(self):
        """LLMRequestEvent should have model, messages, tools, and settings fields."""
        event = LLMRequestEvent(
            session_id="test-session",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[{"name": "get_weather"}],
            settings={"temperature": 0.7, "max_tokens": 1000},
        )

        assert event.event_type == EventType.LLM_REQUEST
        assert event.model == "gpt-4"
        assert len(event.messages) == 1
        assert event.messages[0]["role"] == "user"
        assert len(event.tools) == 1
        assert event.settings["temperature"] == 0.7

    def test_llm_response_event_fields(self):
        """LLMResponseEvent should have model, content, tool_calls, usage, cost_usd, duration_ms."""
        event = LLMResponseEvent(
            session_id="test-session",
            model="gpt-4",
            content="Hello! How can I help?",
            tool_calls=[],
            usage={"input_tokens": 10, "output_tokens": 20},
            cost_usd=0.001,
            duration_ms=500.0,
        )

        assert event.event_type == EventType.LLM_RESPONSE
        assert event.model == "gpt-4"
        assert event.content == "Hello! How can I help?"
        assert event.usage["input_tokens"] == 10
        assert event.cost_usd == 0.001
        assert event.duration_ms == 500.0

    def test_decision_event_fields(self):
        """DecisionEvent should have reasoning, confidence, evidence, alternatives, chosen_action."""
        event = DecisionEvent(
            session_id="test-session",
            reasoning="Based on the analysis, option A is best",
            confidence=0.85,
            evidence=[{"fact": "data supports A"}],
            evidence_event_ids=["evt-1", "evt-2"],
            alternatives=[{"option": "B", "pros": "cheaper"}],
            chosen_action="proceed_with_option_a",
        )

        assert event.event_type == EventType.DECISION
        assert event.reasoning == "Based on the analysis, option A is best"
        assert event.confidence == 0.85
        assert len(event.evidence) == 1
        assert len(event.evidence_event_ids) == 2
        assert len(event.alternatives) == 1
        assert event.chosen_action == "proceed_with_option_a"

    def test_safety_check_event_fields(self):
        """SafetyCheckEvent should have policy_name, outcome, risk_level, rationale, etc."""
        event = SafetyCheckEvent(
            session_id="test-session",
            policy_name="no_file_deletion",
            outcome=SafetyOutcome.FAIL,
            risk_level=RiskLevel.HIGH,
            rationale="Attempted to delete system file",
            blocked_action="rm -rf /",
            evidence=[{"file": "/etc/passwd"}],
        )

        assert event.event_type == EventType.SAFETY_CHECK
        assert event.policy_name == "no_file_deletion"
        assert event.outcome == SafetyOutcome.FAIL
        assert event.risk_level == RiskLevel.HIGH
        assert event.rationale == "Attempted to delete system file"
        assert event.blocked_action == "rm -rf /"
        assert len(event.evidence) == 1

    def test_refusal_event_fields(self):
        """RefusalEvent should have reason, policy_name, risk_level, blocked_action, safe_alternative."""
        event = RefusalEvent(
            session_id="test-session",
            reason="Cannot access unauthorized resource",
            policy_name="access_control",
            risk_level=RiskLevel.MEDIUM,
            blocked_action="read_private_data",
            safe_alternative="request_access_through_admin",
        )

        assert event.event_type == EventType.REFUSAL
        assert event.reason == "Cannot access unauthorized resource"
        assert event.policy_name == "access_control"
        assert event.risk_level == RiskLevel.MEDIUM
        assert event.blocked_action == "read_private_data"
        assert event.safe_alternative == "request_access_through_admin"

    def test_policy_violation_event_fields(self):
        """PolicyViolationEvent should have policy_name, severity, violation_type, details."""
        event = PolicyViolationEvent(
            session_id="test-session",
            policy_name="prompt_injection_prevention",
            severity=RiskLevel.CRITICAL,
            violation_type="prompt_injection",
            details={"detected_patterns": ["ignore previous instructions"]},
        )

        assert event.event_type == EventType.POLICY_VIOLATION
        assert event.policy_name == "prompt_injection_prevention"
        assert event.severity == RiskLevel.CRITICAL
        assert event.violation_type == "prompt_injection"
        assert "detected_patterns" in event.details

    def test_prompt_policy_event_fields(self):
        """PromptPolicyEvent should have template_id, policy_parameters, speaker, state_summary, goal."""
        event = PromptPolicyEvent(
            session_id="test-session",
            template_id="agent-instruction-v1",
            policy_parameters={"max_actions": 5},
            speaker="assistant",
            state_summary="Processing user request",
            goal="Complete the task safely",
        )

        assert event.event_type == EventType.PROMPT_POLICY
        assert event.template_id == "agent-instruction-v1"
        assert event.policy_parameters == {"max_actions": 5}
        assert event.speaker == "assistant"
        assert event.state_summary == "Processing user request"
        assert event.goal == "Complete the task safely"

    def test_agent_turn_event_fields(self):
        """AgentTurnEvent should have agent_id, speaker, turn_index, goal, content."""
        event = AgentTurnEvent(
            session_id="test-session",
            agent_id="agent-001",
            speaker="assistant",
            turn_index=3,
            goal="Analyze the data",
            content="I have analyzed the data and found patterns.",
        )

        assert event.event_type == EventType.AGENT_TURN
        assert event.agent_id == "agent-001"
        assert event.speaker == "assistant"
        assert event.turn_index == 3
        assert event.goal == "Analyze the data"
        assert event.content == "I have analyzed the data and found patterns."

    def test_behavior_alert_event_fields(self):
        """BehaviorAlertEvent should have alert_type, severity, signal, related_event_ids."""
        event = BehaviorAlertEvent(
            session_id="test-session",
            alert_type="loop_detected",
            severity=RiskLevel.HIGH,
            signal="Repeated tool calls with identical arguments",
            related_event_ids=["evt-1", "evt-2", "evt-3"],
        )

        assert event.event_type == EventType.BEHAVIOR_ALERT
        assert event.alert_type == "loop_detected"
        assert event.severity == RiskLevel.HIGH
        assert event.signal == "Repeated tool calls with identical arguments"
        assert len(event.related_event_ids) == 3

    def test_error_event_fields(self):
        """ErrorEvent should have error_type, error_message, and stack_trace fields."""
        event = ErrorEvent(
            session_id="test-session",
            error_type="ValueError",
            error_message="Invalid input provided",
            stack_trace="Traceback (most recent call last):\n  File ...",
        )

        assert event.event_type == EventType.ERROR
        assert event.error_type == "ValueError"
        assert event.error_message == "Invalid input provided"
        assert event.stack_trace is not None
        assert "Traceback" in event.stack_trace


class TestEventSerialization:
    """Tests for event serialization and deserialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all event fields."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        event = ToolCallEvent(
            id="evt-123",
            session_id="sess-456",
            parent_id="parent-789",
            timestamp=timestamp,
            name="Tool Call",
            data={"extra": "data"},
            metadata={"source": "test"},
            importance=0.8,
            upstream_event_ids=["up-1"],
            tool_name="test_tool",
            arguments={"arg1": "value1"},
        )

        result = event.to_dict()

        assert result["id"] == "evt-123"
        assert result["session_id"] == "sess-456"
        assert result["parent_id"] == "parent-789"
        assert result["event_type"] == "tool_call"
        assert result["timestamp"] == "2024-01-15T10:30:00+00:00"
        assert result["name"] == "Tool Call"
        assert result["data"] == {"extra": "data"}
        assert result["metadata"] == {"source": "test"}
        assert result["importance"] == 0.8
        assert result["upstream_event_ids"] == ["up-1"]
        assert result["tool_name"] == "test_tool"
        assert result["arguments"] == {"arg1": "value1"}

    def test_from_dict_reconstructs_event(self):
        """from_dict should properly reconstruct a base TraceEvent from a dictionary."""
        data = {
            "id": "evt-123",
            "session_id": "sess-456",
            "parent_id": "parent-789",
            "event_type": "agent_start",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "name": "Agent Start",
            "data": {"extra": "data"},
            "metadata": {"source": "test"},
            "importance": 0.8,
            "upstream_event_ids": ["up-1"],
        }

        event = TraceEvent.from_dict(data)

        assert event.id == "evt-123"
        assert event.session_id == "sess-456"
        assert event.parent_id == "parent-789"
        assert event.event_type == EventType.AGENT_START
        assert event.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert event.name == "Agent Start"
        assert event.data == {"extra": "data"}
        assert event.importance == 0.8

    def test_from_data_reconstructs_typed_event(self):
        """from_data should reconstruct typed events with their specific fields."""
        base_kwargs = {
            "id": "evt-123",
            "session_id": "sess-456",
            "parent_id": "parent-789",
            "timestamp": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "name": "Tool Call",
            "metadata": {"source": "test"},
            "importance": 0.8,
            "upstream_event_ids": ["up-1"],
        }
        data = {
            "extra": "data",
            "tool_name": "test_tool",
            "arguments": {"arg1": "value1"},
        }

        event = TraceEvent.from_data(EventType.TOOL_CALL, base_kwargs, data)

        assert isinstance(event, ToolCallEvent)
        assert event.id == "evt-123"
        assert event.session_id == "sess-456"
        assert event.tool_name == "test_tool"
        assert event.arguments == {"arg1": "value1"}

    def test_timestamp_serialization_preserves_isoformat(self):
        """Timestamp serialization should produce ISO format string."""
        timestamp = datetime(2024, 6, 15, 14, 25, 30, 123456, tzinfo=timezone.utc)
        event = TraceEvent(timestamp=timestamp)

        result = event.to_dict()

        assert isinstance(result["timestamp"], str)
        assert "2024-06-15" in result["timestamp"]
        assert "14:25:30" in result["timestamp"]

    def test_timestamp_deserialization_from_isoformat(self):
        """Timestamp deserialization should parse ISO format strings."""
        data = {
            "timestamp": "2024-06-15T14:25:30.123456+00:00",
        }

        event = TraceEvent.from_dict(data)

        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.year == 2024
        assert event.timestamp.month == 6
        assert event.timestamp.day == 15

    def test_event_type_serialization(self):
        """Event type serialization should produce string values."""
        event = TraceEvent(event_type=EventType.DECISION)

        result = event.to_dict()

        assert result["event_type"] == "decision"

    def test_event_type_deserialization(self):
        """Event type deserialization should convert strings to EventType enum."""
        data = {
            "event_type": "safety_check",
        }

        event = TraceEvent.from_dict(data)

        assert isinstance(event.event_type, EventType)
        assert event.event_type == EventType.SAFETY_CHECK

    def test_nested_data_serialization(self):
        """Nested data structures should be properly serialized."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = TraceEvent(
            data={
                "nested": {
                    "level1": {
                        "level2": [1, 2, 3],
                    }
                },
                "list_of_dicts": [{"key": "value"}],
                "timestamp_in_data": timestamp,
            }
        )

        result = event.to_dict()

        assert result["data"]["nested"]["level1"]["level2"] == [1, 2, 3]
        assert result["data"]["list_of_dicts"] == [{"key": "value"}]
        assert isinstance(result["data"]["timestamp_in_data"], str)


class TestEventHierarchy:
    """Tests for event class hierarchy and inheritance."""

    def test_all_events_inherit_from_trace_event(self):
        """All concrete event classes should inherit from TraceEvent."""
        event_classes = [
            ToolCallEvent,
            ToolResultEvent,
            LLMRequestEvent,
            LLMResponseEvent,
            DecisionEvent,
            SafetyCheckEvent,
            RefusalEvent,
            PolicyViolationEvent,
            PromptPolicyEvent,
            AgentTurnEvent,
            BehaviorAlertEvent,
            ErrorEvent,
        ]

        for event_cls in event_classes:
            assert issubclass(event_cls, TraceEvent), f"{event_cls.__name__} should inherit from TraceEvent"

    def test_trace_event_has_base_fields(self):
        """TraceEvent should have all base fields defined."""
        event = TraceEvent()

        for field_name in BASE_EVENT_FIELDS:
            assert hasattr(event, field_name), f"TraceEvent should have field: {field_name}"

    def test_event_parent_chain(self):
        """Events should support parent-child relationships via parent_id."""
        parent = TraceEvent(id="parent-1", session_id="session-1")
        child = TraceEvent(
            id="child-1",
            session_id="session-1",
            parent_id="parent-1",
        )

        assert parent.parent_id is None
        assert child.parent_id == "parent-1"

    def test_upstream_event_ids(self):
        """Events should track upstream event IDs for causal chains."""
        event = TraceEvent(
            session_id="session-1",
            upstream_event_ids=["evt-1", "evt-2", "evt-3"],
        )

        assert len(event.upstream_event_ids) == 3
        assert "evt-1" in event.upstream_event_ids
        assert "evt-2" in event.upstream_event_ids
        assert "evt-3" in event.upstream_event_ids

    def test_typed_field_names_excludes_base(self):
        """_typed_field_names should return event-specific fields only, not base fields."""
        # ToolCallEvent has tool_name and arguments as typed fields
        typed_fields = ToolCallEvent._typed_field_names()

        assert "tool_name" in typed_fields
        assert "arguments" in typed_fields
        # Base fields should not be included
        assert "id" not in typed_fields
        assert "session_id" not in typed_fields
        assert "event_type" not in typed_fields
        assert "timestamp" not in typed_fields

        # DecisionEvent has multiple typed fields
        decision_fields = DecisionEvent._typed_field_names()
        assert "reasoning" in decision_fields
        assert "confidence" in decision_fields
        assert "evidence" in decision_fields
        assert "chosen_action" in decision_fields


class TestEnumStringValues:
    """Tests for enum string representation and values."""

    def test_event_type_string_values(self):
        """EventType enum values should be lowercase snake_case strings."""
        assert str(EventType.TOOL_CALL) == "tool_call"
        assert str(EventType.LLM_REQUEST) == "llm_request"
        assert str(EventType.SAFETY_CHECK) == "safety_check"
        assert str(EventType.POLICY_VIOLATION) == "policy_violation"
        assert str(EventType.BEHAVIOR_ALERT) == "behavior_alert"

    def test_risk_level_values(self):
        """RiskLevel enum values should be lowercase strings."""
        assert str(RiskLevel.LOW) == "low"
        assert str(RiskLevel.MEDIUM) == "medium"
        assert str(RiskLevel.HIGH) == "high"
        assert str(RiskLevel.CRITICAL) == "critical"

    def test_safety_outcome_values(self):
        """SafetyOutcome enum values should be lowercase strings."""
        assert str(SafetyOutcome.PASS) == "pass"
        assert str(SafetyOutcome.FAIL) == "fail"
        assert str(SafetyOutcome.WARN) == "warn"
        assert str(SafetyOutcome.BLOCK) == "block"


class TestDefaultValues:
    """Tests for default values on events."""

    def test_trace_event_defaults(self):
        """TraceEvent should have sensible default values."""
        event = TraceEvent()

        assert event.session_id == ""
        assert event.parent_id is None
        assert event.event_type == EventType.AGENT_START
        assert event.name == ""
        assert event.data == {}
        assert event.metadata == {}
        assert event.importance == 0.5
        assert event.upstream_event_ids == []
        # id and timestamp are auto-generated
        assert event.id is not None
        assert len(event.id) > 0
        assert event.timestamp is not None

    def test_tool_result_default_error_is_none(self):
        """ToolResultEvent error should default to None."""
        event = ToolResultEvent()
        assert event.error is None

    def test_llm_response_default_usage(self):
        """LLMResponseEvent usage should default to zero tokens."""
        event = LLMResponseEvent()
        assert event.usage == {"input_tokens": 0, "output_tokens": 0}

    def test_safety_check_default_outcome(self):
        """SafetyCheckEvent outcome should default to PASS."""
        event = SafetyCheckEvent()
        assert event.outcome == SafetyOutcome.PASS

    def test_decision_default_confidence(self):
        """DecisionEvent confidence should default to 0.5."""
        event = DecisionEvent()
        assert event.confidence == 0.5
