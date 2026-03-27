"""Contract tests verifying SDK payloads match API schemas.

These tests ensure that SDK event types serialize correctly and can be
validated by the API Pydantic schemas. This catches contract mismatches
early before they reach runtime integration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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
)
from api.schemas import (
    CheckpointSchema,
    ReplayResponse,
    RestoreRequest,
    RestoreResponse,
    SessionSchema,
    TraceEventSchema,
)


class TestSessionContract:
    """Tests for SDK Session matching API SessionSchema."""

    def test_session_to_dict_matches_session_schema(self):
        """SDK Session.to_dict() should validate against SessionSchema."""
        session = Session(
            id="test-session-1",
            agent_name="test_agent",
            framework="pytest",
            started_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            ended_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=timezone.utc),
            status=SessionStatus.COMPLETED,
            total_tokens=1500,
            total_cost_usd=0.05,
            tool_calls=3,
            llm_calls=2,
            errors=0,
            replay_value=0.85,
            config={"temperature": 0.7},
            tags=["test", "contract"],
        )

        data = session.to_dict()
        # API expects datetime objects, but SDK serializes to ISO strings
        # Convert back for schema validation
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data["ended_at"]:
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])

        validated = SessionSchema(**data)
        assert validated.id == "test-session-1"
        assert validated.agent_name == "test_agent"
        assert validated.framework == "pytest"
        assert validated.status == SessionStatus.COMPLETED
        assert validated.total_tokens == 1500
        assert validated.total_cost_usd == 0.05
        assert validated.tool_calls == 3
        assert validated.llm_calls == 2
        assert validated.errors == 0
        assert validated.replay_value == 0.85
        assert validated.config == {"temperature": 0.7}
        assert validated.tags == ["test", "contract"]

    def test_minimal_session_matches_schema(self):
        """Minimal SDK Session should validate against SessionSchema."""
        session = Session(
            id="minimal-session",
            agent_name="minimal",
            framework="test",
            started_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            status=SessionStatus.RUNNING,
        )

        data = session.to_dict()
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data["ended_at"]:
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])

        validated = SessionSchema(**data)
        assert validated.id == "minimal-session"
        assert validated.status == SessionStatus.RUNNING
        assert validated.ended_at is None


class TestToolCallEventContract:
    """Tests for SDK ToolCallEvent matching API TraceEventSchema."""

    def test_tool_call_event_matches_schema(self):
        """SDK ToolCallEvent.to_dict() should validate against TraceEventSchema."""
        event = ToolCallEvent(
            id="tool-call-1",
            session_id="session-1",
            parent_id="llm-response-1",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="search_web",
            data={"query": "test query"},
            metadata={"source": "user"},
            importance=0.7,
            upstream_event_ids=["llm-response-1"],
            tool_name="search",
            arguments={"query": "test query", "limit": 10},
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "tool-call-1"
        assert validated.session_id == "session-1"
        assert validated.parent_id == "llm-response-1"
        assert validated.event_type == EventType.TOOL_CALL
        assert validated.name == "search_web"
        assert validated.importance == 0.7
        assert validated.upstream_event_ids == ["llm-response-1"]
        assert validated.tool_name == "search"
        assert validated.arguments == {"query": "test query", "limit": 10}


class TestToolResultEventContract:
    """Tests for SDK ToolResultEvent matching API TraceEventSchema."""

    def test_tool_result_event_matches_schema(self):
        """SDK ToolResultEvent.to_dict() should validate against TraceEventSchema."""
        event = ToolResultEvent(
            id="tool-result-1",
            session_id="session-1",
            parent_id="tool-call-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime(2025, 1, 1, 12, 0, 5, tzinfo=timezone.utc),
            name="search_result",
            data={},
            metadata={},
            importance=0.6,
            upstream_event_ids=["tool-call-1"],
            tool_name="search",
            result={"items": ["item1", "item2"], "count": 2},
            error=None,
            duration_ms=250.5,
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "tool-result-1"
        assert validated.tool_name == "search"
        assert validated.result == {"items": ["item1", "item2"], "count": 2}
        assert validated.error is None
        assert validated.duration_ms == 250.5

    def test_tool_result_with_error_matches_schema(self):
        """ToolResultEvent with error should validate against schema."""
        event = ToolResultEvent(
            id="tool-error-1",
            session_id="session-1",
            parent_id="tool-call-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime(2025, 1, 1, 12, 0, 5, tzinfo=timezone.utc),
            name="failed_call",
            data={},
            metadata={},
            importance=0.8,
            upstream_event_ids=[],
            tool_name="risky_tool",
            result=None,
            error="Connection timeout after 30s",
            duration_ms=30000.0,
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.error == "Connection timeout after 30s"
        assert validated.result is None


class TestDecisionEventContract:
    """Tests for SDK DecisionEvent matching API TraceEventSchema."""

    def test_decision_event_matches_schema(self):
        """SDK DecisionEvent.to_dict() should validate against TraceEventSchema."""
        event = DecisionEvent(
            id="decision-1",
            session_id="session-1",
            parent_id="tool-result-1",
            event_type=EventType.DECISION,
            timestamp=datetime(2025, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
            name="choose_action",
            data={},
            metadata={},
            importance=0.9,
            upstream_event_ids=["tool-call-1", "tool-result-1"],
            reasoning="Based on the search results, option A has higher relevance",
            confidence=0.85,
            evidence=[{"source": "search", "score": 0.95}],
            evidence_event_ids=["tool-result-1"],
            alternatives=[{"action": "option_b", "score": 0.6}],
            chosen_action="option_a",
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "decision-1"
        assert validated.event_type == EventType.DECISION
        assert validated.reasoning == "Based on the search results, option A has higher relevance"
        assert validated.confidence == 0.85
        assert validated.evidence == [{"source": "search", "score": 0.95}]
        assert validated.evidence_event_ids == ["tool-result-1"]
        assert validated.alternatives == [{"action": "option_b", "score": 0.6}]
        assert validated.chosen_action == "option_a"


class TestLLMRequestEventContract:
    """Tests for SDK LLMRequestEvent matching API TraceEventSchema."""

    def test_llm_request_event_matches_schema(self):
        """SDK LLMRequestEvent.to_dict() should validate against TraceEventSchema."""
        event = LLMRequestEvent(
            id="llm-request-1",
            session_id="session-1",
            parent_id=None,
            event_type=EventType.LLM_REQUEST,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="initial_prompt",
            data={},
            metadata={"provider": "anthropic"},
            importance=0.5,
            upstream_event_ids=[],
            model="claude-3-opus",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the weather?"},
            ],
            tools=[{"name": "get_weather", "description": "Get current weather"}],
            settings={"temperature": 0.7, "max_tokens": 1024},
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "llm-request-1"
        assert validated.event_type == EventType.LLM_REQUEST
        assert validated.model == "claude-3-opus"
        assert len(validated.messages) == 2
        assert validated.messages[0]["role"] == "system"
        assert len(validated.tools) == 1
        assert validated.tools[0]["name"] == "get_weather"
        assert validated.settings == {"temperature": 0.7, "max_tokens": 1024}


class TestLLMResponseEventContract:
    """Tests for SDK LLMResponseEvent matching API TraceEventSchema."""

    def test_llm_response_event_matches_schema(self):
        """SDK LLMResponseEvent.to_dict() should validate against TraceEventSchema."""
        event = LLMResponseEvent(
            id="llm-response-1",
            session_id="session-1",
            parent_id="llm-request-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime(2025, 1, 1, 12, 0, 2, tzinfo=timezone.utc),
            name="response",
            data={},
            metadata={},
            importance=0.6,
            upstream_event_ids=["llm-request-1"],
            model="claude-3-opus",
            content="I'll check the weather for you.",
            tool_calls=[{"name": "get_weather", "arguments": {"location": "NYC"}}],
            usage={"input_tokens": 50, "output_tokens": 25},
            cost_usd=0.002,
            duration_ms=1500.0,
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "llm-response-1"
        assert validated.event_type == EventType.LLM_RESPONSE
        assert validated.model == "claude-3-opus"
        assert validated.content == "I'll check the weather for you."
        assert len(validated.tool_calls) == 1
        assert validated.tool_calls[0]["name"] == "get_weather"
        assert validated.usage == {"input_tokens": 50, "output_tokens": 25}
        assert validated.cost_usd == 0.002
        assert validated.duration_ms == 1500.0


class TestSafetyEventContract:
    """Tests for SDK safety events matching API TraceEventSchema."""

    def test_safety_check_event_matches_schema(self):
        """SDK SafetyCheckEvent.to_dict() should validate against TraceEventSchema."""
        event = SafetyCheckEvent(
            id="safety-1",
            session_id="session-1",
            parent_id="tool-call-1",
            event_type=EventType.SAFETY_CHECK,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="content_filter",
            data={},
            metadata={},
            importance=0.9,
            upstream_event_ids=[],
            policy_name="content_policy",
            outcome=SafetyOutcome.WARN,
            risk_level=RiskLevel.MEDIUM,
            rationale="Potential PII detected in content",
            blocked_action=None,
            evidence=[{"type": "pattern", "match": "email"}],
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "safety-1"
        assert validated.event_type == EventType.SAFETY_CHECK
        assert validated.policy_name == "content_policy"
        assert validated.outcome == SafetyOutcome.WARN
        assert validated.risk_level == RiskLevel.MEDIUM
        assert validated.rationale == "Potential PII detected in content"
        assert validated.blocked_action is None
        assert validated.evidence == [{"type": "pattern", "match": "email"}]

    def test_refusal_event_matches_schema(self):
        """SDK RefusalEvent.to_dict() should validate against TraceEventSchema."""
        event = RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            parent_id="llm-response-1",
            event_type=EventType.REFUSAL,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="blocked_request",
            data={},
            metadata={},
            importance=0.95,
            upstream_event_ids=[],
            reason="Request violates content policy",
            policy_name="harmful_content",
            risk_level=RiskLevel.HIGH,
            blocked_action="generate_harmful_content",
            safe_alternative="Provide educational information instead",
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "refusal-1"
        assert validated.event_type == EventType.REFUSAL
        assert validated.reason == "Request violates content policy"
        assert validated.policy_name == "harmful_content"
        assert validated.risk_level == RiskLevel.HIGH
        assert validated.blocked_action == "generate_harmful_content"
        assert validated.safe_alternative == "Provide educational information instead"

    def test_policy_violation_event_matches_schema(self):
        """SDK PolicyViolationEvent.to_dict() should validate against TraceEventSchema."""
        event = PolicyViolationEvent(
            id="violation-1",
            session_id="session-1",
            parent_id="llm-response-1",
            event_type=EventType.POLICY_VIOLATION,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="injection_detected",
            data={},
            metadata={},
            importance=0.95,
            upstream_event_ids=[],
            policy_name="prompt_injection",
            severity=RiskLevel.CRITICAL,
            violation_type="prompt_injection",
            details={"pattern": "ignore_previous", "position": 42},
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "violation-1"
        assert validated.event_type == EventType.POLICY_VIOLATION
        assert validated.policy_name == "prompt_injection"
        assert validated.severity == RiskLevel.CRITICAL
        assert validated.violation_type == "prompt_injection"
        assert validated.details == {"pattern": "ignore_previous", "position": 42}

    def test_prompt_policy_event_matches_schema(self):
        """SDK PromptPolicyEvent.to_dict() should validate against TraceEventSchema."""
        event = PromptPolicyEvent(
            id="prompt-policy-1",
            session_id="session-1",
            parent_id=None,
            event_type=EventType.PROMPT_POLICY,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="template_applied",
            data={},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            template_id="assistant_v2",
            policy_parameters={"max_length": 500, "tone": "professional"},
            speaker="agent",
            state_summary="Ready to assist user",
            goal="Answer user questions accurately",
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "prompt-policy-1"
        assert validated.event_type == EventType.PROMPT_POLICY
        assert validated.template_id == "assistant_v2"
        assert validated.policy_parameters == {"max_length": 500, "tone": "professional"}
        assert validated.speaker == "agent"
        assert validated.state_summary == "Ready to assist user"
        assert validated.goal == "Answer user questions accurately"


class TestAgentEventContract:
    """Tests for SDK agent events matching API TraceEventSchema."""

    def test_agent_turn_event_matches_schema(self):
        """SDK AgentTurnEvent.to_dict() should validate against TraceEventSchema."""
        event = AgentTurnEvent(
            id="turn-1",
            session_id="session-1",
            parent_id=None,
            event_type=EventType.AGENT_TURN,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="agent_a_turn",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            agent_id="agent-alpha",
            speaker="Agent Alpha",
            turn_index=3,
            goal="Analyze user input",
            content="I've analyzed the input and found 3 key points.",
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "turn-1"
        assert validated.event_type == EventType.AGENT_TURN
        assert validated.agent_id == "agent-alpha"
        assert validated.speaker == "Agent Alpha"
        assert validated.turn_index == 3
        assert validated.goal == "Analyze user input"
        assert validated.content == "I've analyzed the input and found 3 key points."

    def test_behavior_alert_event_matches_schema(self):
        """SDK BehaviorAlertEvent.to_dict() should validate against TraceEventSchema."""
        event = BehaviorAlertEvent(
            id="alert-1",
            session_id="session-1",
            parent_id="tool-call-1",
            event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="loop_detected",
            data={},
            metadata={},
            importance=0.85,
            upstream_event_ids=["tool-call-1", "tool-call-2", "tool-call-3"],
            alert_type="repetition",
            severity=RiskLevel.HIGH,
            signal="Same tool called 3 times with identical arguments",
            related_event_ids=["tool-call-1", "tool-call-2", "tool-call-3"],
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "alert-1"
        assert validated.event_type == EventType.BEHAVIOR_ALERT
        assert validated.alert_type == "repetition"
        assert validated.severity == RiskLevel.HIGH
        assert validated.signal == "Same tool called 3 times with identical arguments"
        assert validated.related_event_ids == ["tool-call-1", "tool-call-2", "tool-call-3"]


class TestErrorEventContract:
    """Tests for SDK ErrorEvent matching API TraceEventSchema."""

    def test_error_event_matches_schema(self):
        """SDK ErrorEvent.to_dict() should validate against TraceEventSchema."""
        event = ErrorEvent(
            id="error-1",
            session_id="session-1",
            parent_id="tool-call-1",
            event_type=EventType.ERROR,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="api_failure",
            data={},
            metadata={},
            importance=0.9,
            upstream_event_ids=[],
            error_type="ConnectionError",
            error_message="Failed to connect to external API",
            stack_trace="Traceback (most recent call last):\n  File ...",
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "error-1"
        assert validated.event_type == EventType.ERROR
        assert validated.error_type == "ConnectionError"
        assert validated.error_message == "Failed to connect to external API"
        assert validated.stack_trace == "Traceback (most recent call last):\n  File ..."

    def test_error_event_without_stack_trace(self):
        """ErrorEvent without stack trace should validate against schema."""
        event = ErrorEvent(
            id="error-2",
            session_id="session-1",
            parent_id=None,
            event_type=EventType.ERROR,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="validation_error",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            error_type="ValidationError",
            error_message="Invalid input format",
            stack_trace=None,
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.error_type == "ValidationError"
        assert validated.stack_trace is None


class TestCheckpointContract:
    """Tests for SDK Checkpoint matching API CheckpointSchema."""

    def test_checkpoint_matches_schema(self):
        """SDK Checkpoint should validate against CheckpointSchema."""
        checkpoint = Checkpoint(
            id="checkpoint-1",
            session_id="session-1",
            event_id="event-5",
            sequence=5,
            state={"counter": 5, "last_action": "search"},
            memory={"context": ["msg1", "msg2"]},
            timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            importance=0.75,
        )

        data = {
            "id": checkpoint.id,
            "session_id": checkpoint.session_id,
            "event_id": checkpoint.event_id,
            "sequence": checkpoint.sequence,
            "state": checkpoint.state,
            "memory": checkpoint.memory,
            "timestamp": checkpoint.timestamp,
            "importance": checkpoint.importance,
        }

        validated = CheckpointSchema(**data)
        assert validated.id == "checkpoint-1"
        assert validated.session_id == "session-1"
        assert validated.event_id == "event-5"
        assert validated.sequence == 5
        assert validated.state == {"counter": 5, "last_action": "search"}
        assert validated.memory == {"context": ["msg1", "msg2"]}
        assert validated.importance == 0.75


class TestReplayRequestResponseContract:
    """Tests for replay request/response payloads matching API schemas."""

    def test_restore_request_schema(self):
        """RestoreRequest should accept valid payloads."""
        request = RestoreRequest(session_id="session-1", label="before_error")
        assert request.session_id == "session-1"
        assert request.label == "before_error"

    def test_restore_request_with_defaults(self):
        """RestoreRequest should work with default values."""
        request = RestoreRequest()
        assert request.session_id is None
        assert request.label == ""

    def test_replay_response_schema(self):
        """ReplayResponse should accept valid event payloads."""
        response_data = {
            "session_id": "session-1",
            "mode": "failure",
            "focus_event_id": "error-1",
            "start_index": 0,
            "events": [
                {
                    "id": "event-1",
                    "session_id": "session-1",
                    "parent_id": None,
                    "event_type": "tool_call",
                    "timestamp": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    "name": "search",
                    "data": {},
                    "metadata": {},
                    "importance": 0.5,
                    "upstream_event_ids": [],
                    "tool_name": "search",
                    "arguments": {"query": "test"},
                }
            ],
            "checkpoints": [],
            "nearest_checkpoint": None,
            "breakpoints": [],
            "failure_event_ids": ["error-1"],
            "collapsed_segments": [],
            "highlight_indices": [0],
            "stopped_at_breakpoint": False,
            "stopped_at_index": None,
        }

        validated = ReplayResponse(**response_data)
        assert validated.session_id == "session-1"
        assert validated.mode == "failure"
        assert validated.focus_event_id == "error-1"
        assert len(validated.events) == 1
        assert validated.failure_event_ids == ["error-1"]
        assert validated.highlight_indices == [0]


class TestBaseTraceEventContract:
    """Tests for base TraceEvent matching API TraceEventSchema."""

    def test_base_trace_event_matches_schema(self):
        """Base SDK TraceEvent.to_dict() should validate against TraceEventSchema."""
        event = TraceEvent(
            id="base-event-1",
            session_id="session-1",
            parent_id=None,
            event_type=EventType.AGENT_START,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            name="agent_started",
            data={"config": "default"},
            metadata={"version": "1.0"},
            importance=0.3,
            upstream_event_ids=[],
        )

        data = event.to_dict()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        validated = TraceEventSchema(**data)
        assert validated.id == "base-event-1"
        assert validated.session_id == "session-1"
        assert validated.parent_id is None
        assert validated.event_type == EventType.AGENT_START
        assert validated.name == "agent_started"
        assert validated.data == {"config": "default"}
        assert validated.metadata == {"version": "1.0"}
        assert validated.importance == 0.3
        assert validated.upstream_event_ids == []


class TestEnumSerialization:
    """Tests for enum serialization matching API expectations."""

    def test_event_type_serializes_to_string(self):
        """EventType enum should serialize to string value."""
        assert str(EventType.TOOL_CALL) == "tool_call"
        assert str(EventType.LLM_REQUEST) == "llm_request"
        assert str(EventType.DECISION) == "decision"

    def test_session_status_serializes_to_string(self):
        """SessionStatus enum should serialize to string value."""
        assert str(SessionStatus.RUNNING) == "running"
        assert str(SessionStatus.COMPLETED) == "completed"
        assert str(SessionStatus.ERROR) == "error"

    def test_risk_level_serializes_to_string(self):
        """RiskLevel enum should serialize to string value."""
        assert str(RiskLevel.LOW) == "low"
        assert str(RiskLevel.MEDIUM) == "medium"
        assert str(RiskLevel.HIGH) == "high"
        assert str(RiskLevel.CRITICAL) == "critical"

    def test_safety_outcome_serializes_to_string(self):
        """SafetyOutcome enum should serialize to string value."""
        assert str(SafetyOutcome.PASS) == "pass"
        assert str(SafetyOutcome.FAIL) == "fail"
        assert str(SafetyOutcome.WARN) == "warn"
        assert str(SafetyOutcome.BLOCK) == "block"
