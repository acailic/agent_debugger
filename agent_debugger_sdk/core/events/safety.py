"""Safety and policy events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, RiskLevel, SafetyOutcome, TraceEvent

__all__ = ["SafetyCheckEvent", "RefusalEvent", "PolicyViolationEvent", "PromptPolicyEvent"]


@dataclass(kw_only=True)
class SafetyCheckEvent(TraceEvent):
    """Event representing an explicit guard or safety evaluation.

    Attributes:
        event_type: Always EventType.SAFETY_CHECK
        policy_name: Name of the safety policy being checked
        outcome: Result of the safety check (pass/fail/warn/block)
        risk_level: Severity level of the risk detected
        rationale: Explanation for the safety check result
        blocked_action: Action that was blocked, if any
        evidence: Supporting evidence for the safety decision
    """

    event_type: EventType = EventType.SAFETY_CHECK
    policy_name: str = ""
    outcome: SafetyOutcome = SafetyOutcome.PASS
    risk_level: RiskLevel = RiskLevel.LOW
    rationale: str = ""
    blocked_action: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.outcome = SafetyOutcome(self.outcome)
        self.risk_level = RiskLevel(self.risk_level)


@dataclass(kw_only=True)
class RefusalEvent(TraceEvent):
    """Event representing an intentional refusal.

    Attributes:
        event_type: Always EventType.REFUSAL
        reason: Explanation for the refusal
        policy_name: Name of the policy that triggered the refusal
        risk_level: Severity level of the risk
        blocked_action: Action that was refused
        safe_alternative: Suggested alternative action, if any
    """

    event_type: EventType = EventType.REFUSAL
    reason: str = ""
    policy_name: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    blocked_action: str | None = None
    safe_alternative: str | None = None

    def __post_init__(self) -> None:
        self.risk_level = RiskLevel(self.risk_level)


@dataclass(kw_only=True)
class PolicyViolationEvent(TraceEvent):
    """Event representing a policy violation or prompt injection signal.

    Attributes:
        event_type: Always EventType.POLICY_VIOLATION
        policy_name: Name of the violated policy
        severity: Severity level of the violation
        violation_type: Category of violation
        details: Additional details about the violation
    """

    event_type: EventType = EventType.POLICY_VIOLATION
    policy_name: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM
    violation_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.severity = RiskLevel(self.severity)


@dataclass(kw_only=True)
class PromptPolicyEvent(TraceEvent):
    """Event describing prompt policy or prompt-as-action state.

    Attributes:
        event_type: Always EventType.PROMPT_POLICY
        template_id: Identifier for the prompt template
        policy_parameters: Parameters applied to the prompt policy
        speaker: Agent or role associated with this prompt
        state_summary: Summary of the agent's state
        goal: Goal associated with this prompt policy
    """

    event_type: EventType = EventType.PROMPT_POLICY
    template_id: str = ""
    policy_parameters: dict[str, Any] = field(default_factory=dict)
    speaker: str = ""
    state_summary: str = ""
    goal: str = ""
