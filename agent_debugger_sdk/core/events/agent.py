"""Agent lifecycle and behavior events."""

from dataclasses import dataclass, field

from .base import EventType, RiskLevel, TraceEvent


@dataclass(kw_only=True)
class AgentTurnEvent(TraceEvent):
    """Event representing a single turn in a multi-agent session.

    Attributes:
        event_type: Always EventType.AGENT_TURN
        agent_id: Identifier for the agent taking this turn
        speaker: Name or role of the speaker
        turn_index: Sequential index of this turn in the session
        goal: Goal for this agent turn
        content: Content produced during this turn
    """

    event_type: EventType = EventType.AGENT_TURN
    agent_id: str = ""
    speaker: str = ""
    turn_index: int = 0
    goal: str = ""
    content: str = ""


@dataclass(kw_only=True)
class BehaviorAlertEvent(TraceEvent):
    """Event representing detected suspicious or unstable behavior.

    Attributes:
        event_type: Always EventType.BEHAVIOR_ALERT
        alert_type: Category of the behavior alert
        severity: Severity level of the alert
        signal: Description of the detected signal
        related_event_ids: IDs of events related to this alert
    """

    event_type: EventType = EventType.BEHAVIOR_ALERT
    alert_type: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM
    signal: str = ""
    related_event_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.severity = RiskLevel(self.severity)
