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
    SafetyCheckEvent,
    Session,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from collector.intelligence import TraceIntelligence, _event_value, _mean
from collector.replay import _collect_focus_scope_ids, build_replay, build_tree, event_is_failure, matches_breakpoint


def test_trace_event_from_dict_and_serializers_cover_event_models():
    timestamp = "2026-03-23T12:00:00+00:00"
    event = TraceEvent.from_dict(
        {
            "id": "event-1",
            "session_id": "session-1",
            "parent_id": "parent-1",
            "event_type": "error",
            "timestamp": timestamp,
            "name": "failure",
            "data": {"a": 1},
            "metadata": {"b": 2},
            "importance": 0.8,
            "upstream_event_ids": ["upstream-1"],
        }
    )

    assert event.event_type == EventType.ERROR
    assert event.timestamp == datetime.fromisoformat(timestamp)
    assert event.to_dict()["upstream_event_ids"] == ["upstream-1"]

    tool_call = ToolCallEvent(tool_name="search", arguments={"q": "trace"})
    tool_result = ToolResultEvent(tool_name="search", result={"ok": True}, error="boom", duration_ms=12.5)
    request = LLMRequestEvent(model="gpt-test", messages=[{"role": "user", "content": "hi"}], tools=[{"name": "search"}], settings={"temperature": 0.1})
    response = LLMResponseEvent(
        model="gpt-test",
        content="hello",
        tool_calls=[{"name": "search"}],
        usage={"input_tokens": 3, "output_tokens": 4},
        cost_usd=0.02,
        duration_ms=45.0,
    )
    decision = DecisionEvent(
        reasoning="search first",
        confidence=0.4,
        evidence=[{"source": "tool"}],
        evidence_event_ids=["tool-1"],
        alternatives=[{"name": "refuse"}],
        chosen_action="search",
    )
    safety = SafetyCheckEvent(
        policy_name="policy",
        outcome="warn",
        risk_level="medium",
        rationale="careful",
        blocked_action="browse",
        evidence=[{"kind": "policy"}],
    )
    refusal = RefusalEvent(
        reason="unsafe",
        policy_name="policy",
        risk_level="high",
        blocked_action="browse",
        safe_alternative="summarize",
    )
    policy = PolicyViolationEvent(policy_name="policy", severity="high", violation_type="prompt", details={"kind": "pii"})
    prompt_policy = PromptPolicyEvent(
        template_id="tpl-1",
        policy_parameters={"strict": True},
        speaker="system",
        state_summary="policy summary",
        goal="keep user safe",
    )
    turn = AgentTurnEvent(agent_id="agent-1", speaker="assistant", turn_index=2, goal="plan", content="next")
    alert = BehaviorAlertEvent(alert_type="drift", severity="high", signal="looping", related_event_ids=["e1"])
    error = ErrorEvent(error_type="ValueError", error_message="bad input", stack_trace="trace")
    session = Session(
        id="session-1",
        agent_name="agent",
        framework="sdk",
        started_at=datetime.fromisoformat(timestamp),
        ended_at=datetime.fromisoformat(timestamp),
        status="completed",
        total_tokens=7,
        total_cost_usd=0.02,
        tool_calls=1,
        llm_calls=1,
        errors=1,
        config={"mode": "test"},
        tags=["unit"],
    )
    checkpoint = Checkpoint(
        id="checkpoint-1",
        session_id="session-1",
        event_id="event-1",
        sequence=2,
        state={"phase": "done"},
        memory={"summary": "ok"},
        timestamp=datetime.fromisoformat(timestamp),
        importance=0.9,
    )

    assert tool_call.to_dict()["arguments"] == {"q": "trace"}
    assert tool_result.to_dict()["duration_ms"] == 12.5
    assert request.to_dict()["settings"] == {"temperature": 0.1}
    assert response.to_dict()["usage"]["output_tokens"] == 4
    assert decision.to_dict()["evidence_event_ids"] == ["tool-1"]
    assert safety.to_dict()["blocked_action"] == "browse"
    assert refusal.to_dict()["safe_alternative"] == "summarize"
    assert policy.to_dict()["violation_type"] == "prompt"
    assert prompt_policy.to_dict()["template_id"] == "tpl-1"
    assert turn.to_dict()["turn_index"] == 2
    assert alert.to_dict()["related_event_ids"] == ["e1"]
    assert error.to_dict()["error_message"] == "bad input"
    assert session.to_dict()["ended_at"] == timestamp
    assert checkpoint.to_dict()["importance"] == 0.9


def test_trace_intelligence_helper_and_empty_paths():
    intelligence = TraceIntelligence()
    checkpoint = Checkpoint(id="checkpoint-1")

    assert _event_value(None, "anything", "fallback") == "fallback"
    assert _mean([]) == 0.0
    assert intelligence.retention_tier(
        replay_value=0.1,
        high_severity_count=0,
        failure_cluster_count=0,
        behavior_alert_count=0,
    ) == "downsampled"
    assert intelligence.retention_tier(
        replay_value=0.5,
        high_severity_count=0,
        failure_cluster_count=0,
        behavior_alert_count=0,
    ) == "summarized"

    live_summary = intelligence.build_live_summary([], [checkpoint])
    analysis = intelligence.analyze_session([], [checkpoint])

    assert live_summary["latest"]["checkpoint_id"] == "checkpoint-1"
    assert analysis["session_replay_value"] == 0.0
    assert analysis["retention_tier"] == "downsampled"
    assert analysis["failure_explanations"] == []


def test_trace_intelligence_build_live_summary_derives_recent_alerts():
    intelligence = TraceIntelligence()
    timestamp = datetime(2026, 3, 23, tzinfo=timezone.utc)
    events = [
        ToolCallEvent(id="tool-1", session_id="session-1", tool_name="search", timestamp=timestamp),
        ToolCallEvent(id="tool-2", session_id="session-1", tool_name="search", timestamp=timestamp),
        ToolCallEvent(id="tool-3", session_id="session-1", tool_name="search", timestamp=timestamp),
        SafetyCheckEvent(
            id="safety-1",
            session_id="session-1",
            policy_name="policy",
            outcome="warn",
            risk_level="medium",
            rationale="careful",
            timestamp=timestamp,
        ),
        RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            reason="unsafe",
            policy_name="policy",
            risk_level="high",
            timestamp=timestamp,
        ),
        DecisionEvent(
            id="decision-1",
            session_id="session-1",
            chosen_action="search",
            confidence=0.2,
            evidence=[],
            timestamp=timestamp,
        ),
        DecisionEvent(
            id="decision-2",
            session_id="session-1",
            chosen_action="refuse",
            confidence=0.9,
            evidence=[{"source": "tool", "content": "verified"}],
            timestamp=timestamp,
        ),
        PromptPolicyEvent(id="policy-1", session_id="session-1", template_id="tpl-1", timestamp=timestamp),
        PromptPolicyEvent(id="policy-2", session_id="session-1", template_id="tpl-2", timestamp=timestamp),
        AgentTurnEvent(
            id="turn-1",
            session_id="session-1",
            agent_id="agent-1",
            speaker="assistant",
            turn_index=1,
            goal="respond",
            content="next",
            data={"state_summary": "turn summary"},
            timestamp=timestamp,
        ),
        BehaviorAlertEvent(
            id="alert-1",
            session_id="session-1",
            alert_type="drift",
            severity="medium",
            signal="looping",
            timestamp=timestamp,
        ),
    ]
    checkpoints = [Checkpoint(id="checkpoint-1", session_id="session-1", event_id="decision-2", sequence=1, timestamp=timestamp)]

    live_summary = intelligence.build_live_summary(events, checkpoints)

    alert_types = {alert["alert_type"] for alert in live_summary["recent_alerts"]}
    assert {"drift", "tool_loop", "guardrail_pressure", "policy_shift", "strategy_change"} <= alert_types
    assert live_summary["rolling_summary"] == "turn summary"
    assert live_summary["latest"]["decision_event_id"] == "decision-2"
    assert live_summary["latest"]["policy_event_id"] == "policy-2"
    assert live_summary["latest"]["checkpoint_id"] == "checkpoint-1"


def test_trace_intelligence_analyze_session_clusters_and_rankings():
    intelligence = TraceIntelligence()
    timestamp = datetime(2026, 3, 23, tzinfo=timezone.utc)
    events = [
        ToolCallEvent(id="tool-1", session_id="session-1", tool_name="search", timestamp=timestamp),
        ToolCallEvent(id="tool-2", session_id="session-1", tool_name="search", timestamp=timestamp),
        ToolCallEvent(id="tool-3", session_id="session-1", tool_name="search", timestamp=timestamp),
        LLMResponseEvent(id="llm-1", session_id="session-1", model="gpt-test", content="reply", cost_usd=0.04, timestamp=timestamp),
        SafetyCheckEvent(
            id="safety-1",
            session_id="session-1",
            policy_name="policy",
            outcome="warn",
            risk_level="medium",
            rationale="careful",
            timestamp=timestamp,
        ),
        RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            reason="unsafe",
            policy_name="policy",
            risk_level="high",
            timestamp=timestamp,
        ),
        DecisionEvent(
            id="decision-1",
            session_id="session-1",
            chosen_action="search",
            confidence=0.1,
            evidence=[],
            evidence_event_ids=["llm-1"],
            timestamp=timestamp,
        ),
        ToolResultEvent(id="tool-result-1", session_id="session-1", tool_name="search", error="boom", timestamp=timestamp),
        ToolResultEvent(
            id="tool-result-2",
            session_id="session-1",
            tool_name="search",
            error="boom",
            upstream_event_ids=["decision-1"],
            timestamp=timestamp,
        ),
    ]
    checkpoints = [
        Checkpoint(
            id="checkpoint-1",
            session_id="session-1",
            event_id="tool-result-2",
            sequence=2,
            importance=0.9,
            timestamp=timestamp,
        )
    ]

    analysis = intelligence.analyze_session(events, checkpoints)

    assert intelligence.fingerprint(ErrorEvent(error_type="ValueError", error_message="bad", timestamp=timestamp)).startswith("error:ValueError")
    assert intelligence.fingerprint(PolicyViolationEvent(policy_name="policy", violation_type="prompt", timestamp=timestamp)).startswith("policy:policy:prompt")
    assert intelligence.fingerprint(BehaviorAlertEvent(alert_type="drift", timestamp=timestamp)).startswith("alert:drift")
    assert intelligence.fingerprint(events[4]).startswith("safety:")
    assert intelligence.fingerprint(events[5]).startswith("refusal:")
    assert intelligence.fingerprint(events[7]).startswith("tool:search:True")
    assert intelligence.severity(events[4]) > intelligence.severity(events[0])
    assert analysis["behavior_alerts"][0]["alert_type"] == "tool_loop"
    assert analysis["failure_clusters"][0]["representative_event_id"] == "tool-result-2"
    assert analysis["representative_failure_ids"][0] == "tool-result-2"
    assert analysis["checkpoint_rankings"][0]["checkpoint_id"] == "checkpoint-1"
    assert analysis["checkpoint_rankings"][0]["retention_tier"] == "full"
    assert analysis["retention_tier"] == "full"
    assert analysis["session_summary"]["behavior_alert_count"] == 1
    assert "tool-result-2" in analysis["high_replay_value_ids"]
    explanation = next(item for item in analysis["failure_explanations"] if item["failure_event_id"] == "tool-result-2")
    assert explanation["failure_mode"] == "ungrounded_decision"
    assert explanation["likely_cause_event_id"] == "decision-1"
    assert explanation["next_inspection_event_id"] == "decision-1"
    assert explanation["candidates"][0]["event_id"] == "decision-1"


def test_replay_helpers_cover_focus_failure_and_breakpoint_paths():
    timestamp = datetime(2026, 3, 23, tzinfo=timezone.utc)
    root = TraceEvent(id="root", session_id="session-1", timestamp=timestamp)
    child = TraceEvent(id="child", session_id="session-1", parent_id="root", timestamp=timestamp)
    early_child = TraceEvent(id="early-child", session_id="session-1", parent_id="focus", timestamp=timestamp)
    focus = DecisionEvent(
        id="focus",
        session_id="session-1",
        parent_id="child",
        confidence=0.3,
        chosen_action="search",
        upstream_event_ids=["evidence", "evidence"],
        timestamp=timestamp,
    )
    evidence = SafetyCheckEvent(
        id="evidence",
        session_id="session-1",
        policy_name="policy",
        outcome="warn",
        risk_level="high",
        rationale="careful",
        timestamp=timestamp,
    )
    tool = ToolCallEvent(id="tool", session_id="session-1", parent_id="focus", tool_name="search", timestamp=timestamp)
    failure = ToolResultEvent(id="failure", session_id="session-1", parent_id="tool", tool_name="search", error="boom", timestamp=timestamp)
    behavior = BehaviorAlertEvent(id="alert", session_id="session-1", alert_type="drift", signal="looping", timestamp=timestamp)
    events = [root, child, early_child, evidence, focus, tool, failure, behavior]

    assert build_tree([]) is None
    assert build_tree(events)["event"]["id"] == "root"
    assert event_is_failure(behavior) is True
    assert event_is_failure(RefusalEvent(id="refusal", session_id="session-1", reason="unsafe", timestamp=timestamp)) is True
    assert event_is_failure(ToolResultEvent(id="ok", session_id="session-1", tool_name="search", timestamp=timestamp)) is False
    assert matches_breakpoint(behavior, event_types={"behavior_alert"}, tool_names=set(), confidence_below=None, safety_outcomes=set()) is True
    assert matches_breakpoint(tool, event_types=set(), tool_names={"search"}, confidence_below=None, safety_outcomes=set()) is True
    assert matches_breakpoint(focus, event_types=set(), tool_names=set(), confidence_below=0.4, safety_outcomes=set()) is True
    assert matches_breakpoint(evidence, event_types=set(), tool_names=set(), confidence_below=None, safety_outcomes={"warn"}) is True
    assert matches_breakpoint(root, event_types=set(), tool_names=set(), confidence_below=None, safety_outcomes=set()) is False

    assert _collect_focus_scope_ids(events, focus_event_id="missing", start_index=1) == {
        "child",
        "early-child",
        "evidence",
        "focus",
        "tool",
        "failure",
        "alert",
    }
    assert _collect_focus_scope_ids(events, focus_event_id="focus", start_index=3) == {
        "evidence",
        "focus",
        "tool",
        "failure",
    }
    duplicate_scope_events = [
        TraceEvent(id="focus-root", session_id="session-1", timestamp=timestamp),
        TraceEvent(id="dup", session_id="session-1", parent_id="focus-root", timestamp=timestamp),
        TraceEvent(id="dup", session_id="session-1", parent_id="focus-root", timestamp=timestamp),
    ]
    assert _collect_focus_scope_ids(duplicate_scope_events, focus_event_id="focus-root", start_index=0) == {
        "focus-root",
        "dup",
    }

    empty_replay = build_replay([], [], mode="full", focus_event_id=None)
    assert empty_replay["events"] == []

    full_replay = build_replay(events, [], mode="full", focus_event_id=None)
    assert [event["id"] for event in full_replay["events"]] == [
        "root",
        "child",
        "early-child",
        "evidence",
        "focus",
        "tool",
        "failure",
        "alert",
    ]

    focus_replay = build_replay(
        events,
        [Checkpoint(id="missing-checkpoint", session_id="session-1", event_id="missing", sequence=1, timestamp=timestamp)],
        mode="focus",
        focus_event_id="focus",
    )
    assert focus_replay["start_index"] == 0
    assert focus_replay["nearest_checkpoint"]["id"] == "missing-checkpoint"
    assert focus_replay["checkpoints"][0]["id"] == "missing-checkpoint"

    failure_replay = build_replay(
        events,
        [Checkpoint(id="checkpoint-1", session_id="session-1", event_id="child", sequence=2, timestamp=timestamp)],
        mode="failure",
        focus_event_id=None,
        breakpoint_event_types={"behavior_alert"},
        breakpoint_tool_names={"search"},
        breakpoint_confidence_below=0.4,
        breakpoint_safety_outcomes={"warn"},
    )
    assert failure_replay["focus_event_id"] == "alert"
    assert failure_replay["nearest_checkpoint"]["id"] == "checkpoint-1"
    assert failure_replay["failure_event_ids"] == ["evidence", "failure", "alert"]
    assert {event["id"] for event in failure_replay["breakpoints"]} == {"evidence", "focus", "tool", "failure", "alert"}
