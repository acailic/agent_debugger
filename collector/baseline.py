"""Per-agent baseline tracking and drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import EventType


@dataclass
class MultiAgentMetrics:
    """Multi-agent coordination metrics for baseline tracking."""

    avg_policy_shifts_per_session: float = 0.0
    avg_turns_per_session: int = 0
    avg_speaker_count: float = 0.0
    escalation_pattern_rate: float = 0.0  # % of sessions with escalation signals
    evidence_grounding_rate: float = 0.0  # % of decisions with evidence

    def to_dict(self) -> dict[str, Any]:
        """Serialize multi-agent metrics to dictionary."""
        return {
            "avg_policy_shifts_per_session": round(self.avg_policy_shifts_per_session, 4),
            "avg_turns_per_session": self.avg_turns_per_session,
            "avg_speaker_count": round(self.avg_speaker_count, 4),
            "escalation_pattern_rate": round(self.escalation_pattern_rate, 4),
            "evidence_grounding_rate": round(self.evidence_grounding_rate, 4),
        }


@dataclass
class AgentBaseline:
    """Computed baseline metrics for an agent over a time window."""

    agent_name: str
    session_count: int
    computed_at: datetime
    time_window_days: int = 7

    # Decision patterns
    avg_decision_confidence: float = 0.0
    low_confidence_rate: float = 0.0  # % of decisions with confidence < 0.5

    # Performance
    avg_tool_duration_ms: float = 0.0
    error_rate: float = 0.0  # % of tool results with errors

    # Cost
    avg_cost_per_session: float = 0.0
    avg_tokens_per_session: int = 0

    # Behavior
    tool_loop_rate: float = 0.0  # % of sessions with tool loop alerts
    refusal_rate: float = 0.0  # % of sessions with refusals
    avg_session_replay_value: float = 0.0

    # Multi-agent coordination
    multi_agent_metrics: MultiAgentMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize baseline to dictionary."""
        result = {
            "agent_name": self.agent_name,
            "session_count": self.session_count,
            "computed_at": self.computed_at.isoformat(),
            "time_window_days": self.time_window_days,
            "avg_decision_confidence": self.avg_decision_confidence,
            "low_confidence_rate": self.low_confidence_rate,
            "avg_tool_duration_ms": self.avg_tool_duration_ms,
            "error_rate": self.error_rate,
            "avg_cost_per_session": self.avg_cost_per_session,
            "avg_tokens_per_session": self.avg_tokens_per_session,
            "tool_loop_rate": self.tool_loop_rate,
            "refusal_rate": self.refusal_rate,
            "avg_session_replay_value": self.avg_session_replay_value,
        }
        if self.multi_agent_metrics:
            result["multi_agent_metrics"] = self.multi_agent_metrics.to_dict()
        return result


@dataclass
class DriftAlert:
    """A detected drift between baseline and recent behavior."""

    metric: str
    metric_label: str
    baseline_value: float
    current_value: float
    change_percent: float
    severity: str  # "warning" | "critical"
    description: str
    likely_cause: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize drift alert to dictionary."""
        return {
            "metric": self.metric,
            "metric_label": self.metric_label,
            "baseline_value": round(self.baseline_value, 4),
            "current_value": round(self.current_value, 4),
            "change_percent": round(self.change_percent, 1),
            "severity": self.severity,
            "description": self.description,
            "likely_cause": self.likely_cause,
        }


# Thresholds for drift detection
WARNING_THRESHOLD = 0.25  # 25% change
CRITICAL_THRESHOLD = 0.50  # 50% change


def compute_baseline_from_sessions(
    agent_name: str,
    sessions: list[Any],  # List of Session objects
    events_by_session: dict[str, list[Any]],  # session_id -> events
    include_multi_agent: bool = True,
) -> AgentBaseline:
    """Compute baseline metrics from a list of sessions.

    Args:
        agent_name: Name of the agent
        sessions: List of Session objects
        events_by_session: Mapping of session_id to events
        include_multi_agent: Whether to compute multi-agent metrics

    Returns:
        AgentBaseline with computed metrics
    """
    if not sessions:
        return AgentBaseline(
            agent_name=agent_name,
            session_count=0,
            computed_at=datetime.now(timezone.utc),
        )

    total_decision_confidence = 0.0
    low_confidence_count = 0
    decision_count = 0

    total_tool_duration = 0.0
    tool_error_count = 0
    tool_result_count = 0

    total_cost = 0.0
    total_tokens = 0

    tool_loop_sessions = 0
    refusal_sessions = 0
    total_replay_value = 0.0

    # Multi-agent metrics tracking
    total_policy_shifts = 0
    total_turns = 0
    total_speakers = 0
    escalation_sessions = 0
    grounded_decisions = 0

    for session in sessions:
        events = events_by_session.get(session.id, [])
        total_cost += getattr(session, "total_cost_usd", 0) or 0
        total_tokens += getattr(session, "total_tokens", 0) or 0
        total_replay_value += getattr(session, "replay_value", 0) or 0

        has_tool_loop = False
        has_refusal = False
        has_escalation = False
        speakers_in_session: set[str] = set()
        prev_policy_template = None
        policy_shift_count = 0
        turn_count = 0

        for event in events:
            event_type = getattr(event, "event_type", None)
            data = getattr(event, "data", {})

            if event_type == EventType.DECISION:
                confidence = data.get("confidence", 0.5)
                total_decision_confidence += confidence
                decision_count += 1
                if confidence < 0.5:
                    low_confidence_count += 1

                # Track evidence grounding
                evidence_ids = data.get("evidence_event_ids", [])
                if evidence_ids:
                    grounded_decisions += 1

            elif event_type == EventType.TOOL_RESULT:
                duration = data.get("duration_ms") or getattr(event, "duration_ms", 0) or 0
                total_tool_duration += duration
                tool_result_count += 1
                if data.get("error") or getattr(event, "error", None):
                    tool_error_count += 1

            elif event_type == EventType.REFUSAL or event_type == EventType.POLICY_VIOLATION:
                has_refusal = True

            elif event_type == EventType.BEHAVIOR_ALERT:
                if data.get("alert_type") == "tool_loop":
                    has_tool_loop = True

            # Multi-agent event tracking
            elif event_type == EventType.AGENT_TURN:
                turn_count += 1
                speaker = data.get("speaker") or data.get("agent_id") or getattr(event, "speaker", None)
                if speaker:
                    speakers_in_session.add(speaker)

            elif event_type == EventType.PROMPT_POLICY:
                template = data.get("template_id") or data.get("name") or getattr(event, "template_id", None)
                if template and prev_policy_template is not None and template != prev_policy_template:
                    policy_shift_count += 1
                if template:
                    prev_policy_template = template

            # Escalation detection
            elif event_type in (EventType.SAFETY_CHECK, EventType.POLICY_VIOLATION):
                has_escalation = True

        if has_tool_loop:
            tool_loop_sessions += 1
        if has_refusal:
            refusal_sessions += 1
        if has_escalation or policy_shift_count > 2:
            escalation_sessions += 1

        # Aggregate multi-agent metrics
        total_policy_shifts += policy_shift_count
        total_turns += turn_count
        total_speakers += len(speakers_in_session)

    session_count = len(sessions)

    multi_agent_metrics = None
    if include_multi_agent:
        multi_agent_metrics = MultiAgentMetrics(
            avg_policy_shifts_per_session=total_policy_shifts / session_count if session_count > 0 else 0.0,
            avg_turns_per_session=int(total_turns / session_count) if session_count > 0 else 0,
            avg_speaker_count=total_speakers / session_count if session_count > 0 else 0.0,
            escalation_pattern_rate=escalation_sessions / session_count if session_count > 0 else 0.0,
            evidence_grounding_rate=grounded_decisions / decision_count if decision_count > 0 else 0.0,
        )

    return AgentBaseline(
        agent_name=agent_name,
        session_count=session_count,
        computed_at=datetime.now(timezone.utc),
        time_window_days=7,
        avg_decision_confidence=total_decision_confidence / decision_count if decision_count > 0 else 0.0,
        low_confidence_rate=low_confidence_count / decision_count if decision_count > 0 else 0.0,
        avg_tool_duration_ms=total_tool_duration / tool_result_count if tool_result_count > 0 else 0.0,
        error_rate=tool_error_count / tool_result_count if tool_result_count > 0 else 0.0,
        avg_cost_per_session=total_cost / session_count,
        avg_tokens_per_session=int(total_tokens / session_count),
        tool_loop_rate=tool_loop_sessions / session_count,
        refusal_rate=refusal_sessions / session_count,
        avg_session_replay_value=total_replay_value / session_count,
        multi_agent_metrics=multi_agent_metrics,
    )


def detect_drift(
    baseline: AgentBaseline,
    current: AgentBaseline,
) -> list[DriftAlert]:
    """Detect significant drift between baseline and current metrics."""
    alerts = []

    # Need at least 3 sessions for meaningful baseline
    if baseline.session_count < 3:
        return alerts

    def check_drift(
        metric: str,
        label: str,
        baseline_val: float,
        current_val: float,
        higher_is_better: bool = True,
        likely_cause: str | None = None,
    ) -> DriftAlert | None:
        if baseline_val == 0:
            if current_val > 0:
                # Went from zero to non-zero
                return DriftAlert(
                    metric=metric,
                    metric_label=label,
                    baseline_value=baseline_val,
                    current_value=current_val,
                    change_percent=100.0,
                    severity="warning",
                    description=f"{label} increased from 0 to {current_val:.2f}",
                    likely_cause=likely_cause,
                )
            return None

        change = (current_val - baseline_val) / baseline_val
        abs_change = abs(change)

        # Determine severity
        if higher_is_better:
            # Increase is good, decrease is bad
            is_negative = change < 0
        else:
            # Decrease is good, increase is bad
            is_negative = change > 0

        if abs_change >= CRITICAL_THRESHOLD and is_negative:
            severity = "critical"
        elif abs_change >= WARNING_THRESHOLD and is_negative:
            severity = "warning"
        else:
            return None

        direction = "decreased" if current_val < baseline_val else "increased"
        return DriftAlert(
            metric=metric,
            metric_label=label,
            baseline_value=baseline_val,
            current_value=current_val,
            change_percent=abs_change * 100,
            severity=severity,
            description=f"{label} {direction} from {baseline_val:.2f} to {current_val:.2f}",
            likely_cause=likely_cause,
        )

    # Check each metric
    alert = check_drift(
        "decision_confidence",
        "Decision confidence",
        baseline.avg_decision_confidence,
        current.avg_decision_confidence,
        higher_is_better=True,
        likely_cause="Possible prompt or context changes affecting decision quality",
    )
    if alert:
        alerts.append(alert)

    alert = check_drift(
        "error_rate",
        "Error rate",
        baseline.error_rate,
        current.error_rate,
        higher_is_better=False,
        likely_cause="Possible API changes, service degradation, or config drift",
    )
    if alert:
        alerts.append(alert)

    alert = check_drift(
        "tool_loop_rate",
        "Tool loop rate",
        baseline.tool_loop_rate,
        current.tool_loop_rate,
        higher_is_better=False,
        likely_cause="Agent may be stuck in repetitive patterns",
    )
    if alert:
        alerts.append(alert)

    alert = check_drift(
        "refusal_rate",
        "Refusal rate",
        baseline.refusal_rate,
        current.refusal_rate,
        higher_is_better=False,
        likely_cause="Possible policy changes or increased guardrail triggers",
    )
    if alert:
        alerts.append(alert)

    alert = check_drift(
        "avg_cost",
        "Cost per session",
        baseline.avg_cost_per_session,
        current.avg_cost_per_session,
        higher_is_better=False,
        likely_cause="Possible model changes or increased complexity",
    )
    if alert:
        alerts.append(alert)

    alert = check_drift(
        "tool_duration",
        "Tool duration",
        baseline.avg_tool_duration_ms,
        current.avg_tool_duration_ms,
        higher_is_better=False,
        likely_cause="Possible API latency or increased payload sizes",
    )
    if alert:
        alerts.append(alert)

    # Sort by severity (critical first)
    alerts.sort(key=lambda a: (0 if a.severity == "critical" else 1, -a.change_percent))
    return alerts
