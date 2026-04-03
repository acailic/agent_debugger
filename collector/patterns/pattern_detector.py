"""Pattern detection module for cross-session analysis.

This module provides the PatternDetector class for detecting patterns across
multiple sessions including error rate trends, tool failure frequency changes,
decision confidence drops, and new failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_debugger_sdk.core.events import Session


@dataclass
class Pattern:
    """Represents a detected pattern across sessions.

    Attributes:
        pattern_type: Type of pattern (error_trend, tool_failure, confidence_drop, new_failure_mode)
        agent_name: Name of the agent affected
        severity: Severity level (warning, critical)
        description: Human-readable description
        affected_sessions: List of session IDs affected by this pattern
        detected_at: When the pattern was detected
        baseline_value: Baseline metric value
        current_value: Current metric value
        threshold: Threshold that was exceeded
        change_percent: Percentage change from baseline
        metadata: Additional pattern-specific data
    """

    pattern_type: str
    agent_name: str
    severity: str
    description: str
    affected_sessions: list[str]
    detected_at: datetime
    baseline_value: float | None = None
    current_value: float | None = None
    threshold: float | None = None
    change_percent: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize pattern to dictionary."""
        return {
            "pattern_type": self.pattern_type,
            "agent_name": self.agent_name,
            "severity": self.severity,
            "description": self.description,
            "affected_sessions": self.affected_sessions,
            "detected_at": self.detected_at.isoformat(),
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "change_percent": self.change_percent,
            "metadata": self.metadata,
        }


class PatternDetector:
    """Detects patterns across multiple sessions.

    Provides methods for detecting various types of patterns:
    - Error rate trends (increasing/decreasing error rates)
    - Tool failure frequency changes
    - Decision confidence drops
    - New failure modes (previously unseen error types)
    """

    # Default thresholds for pattern detection
    DEFAULT_ERROR_RATE_INCREASE_THRESHOLD = 0.5  # 50% increase
    DEFAULT_TOOL_FAILURE_INCREASE_THRESHOLD = 0.5  # 50% increase
    DEFAULT_CONFIDENCE_DROP_THRESHOLD = 0.2  # 20% drop
    DEFAULT_RECENT_WINDOW_DAYS = 1  # Look at last 1 day for recent sessions
    DEFAULT_BASELINE_WINDOW_DAYS = 7  # Use last 7 days for baseline

    def __init__(
        self,
        *,
        error_rate_threshold: float = DEFAULT_ERROR_RATE_INCREASE_THRESHOLD,
        tool_failure_threshold: float = DEFAULT_TOOL_FAILURE_INCREASE_THRESHOLD,
        confidence_drop_threshold: float = DEFAULT_CONFIDENCE_DROP_THRESHOLD,
        recent_window_days: int = DEFAULT_RECENT_WINDOW_DAYS,
        baseline_window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
    ):
        """Initialize the pattern detector with configurable thresholds.

        Args:
            error_rate_threshold: Percentage increase in error rate to trigger warning
            tool_failure_threshold: Percentage increase in tool failures to trigger warning
            confidence_drop_threshold: Percentage drop in confidence to trigger warning
            recent_window_days: Days to look back for recent sessions
            baseline_window_days: Days to look back for baseline calculation
        """
        self.error_rate_threshold = error_rate_threshold
        self.tool_failure_threshold = tool_failure_threshold
        self.confidence_drop_threshold = confidence_drop_threshold
        self.recent_window_days = recent_window_days
        self.baseline_window_days = baseline_window_days

    def detect_all_patterns(self, sessions: list[Session]) -> list[Pattern]:
        """Detect all types of patterns across sessions.

        Args:
            sessions: List of sessions to analyze

        Returns:
            List of detected Pattern objects
        """
        patterns: list[Pattern] = []

        # Group sessions by agent name
        sessions_by_agent: dict[str, list[Session]] = {}
        for session in sessions:
            sessions_by_agent.setdefault(session.agent_name, []).append(session)

        # Detect patterns for each agent
        for agent_name, agent_sessions in sessions_by_agent.items():
            patterns.extend(self._detect_patterns_for_agent(agent_name, agent_sessions))

        # Sort by severity (critical first) and then by detected_at
        patterns.sort(key=lambda p: (p.severity != "critical", p.detected_at), reverse=True)
        return patterns

    def _detect_patterns_for_agent(self, agent_name: str, sessions: list[Session]) -> list[Pattern]:
        """Detect all patterns for a specific agent.

        Args:
            agent_name: Name of the agent
            sessions: List of sessions for this agent

        Returns:
            List of detected Pattern objects
        """
        patterns: list[Pattern] = []

        if not sessions:
            return patterns

        # Split into baseline and recent sessions
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=self.recent_window_days)
        baseline_cutoff = now - timedelta(days=self.baseline_window_days)

        recent_sessions = [s for s in sessions if s.started_at >= recent_cutoff]
        baseline_sessions = [s for s in sessions if s.started_at >= baseline_cutoff and s.started_at < recent_cutoff]

        # Need at least some baseline data for meaningful comparison
        if len(baseline_sessions) < 3:
            return patterns

        # Detect error rate trends
        patterns.extend(self.detect_error_rate_trends(agent_name, baseline_sessions, recent_sessions))

        # Detect tool failure frequency changes
        patterns.extend(self.detect_tool_failure_frequency(agent_name, baseline_sessions, recent_sessions))

        # Detect confidence drops (requires event data, placeholder for now)
        # patterns.extend(self.detect_confidence_drops(agent_name, baseline_sessions, recent_sessions))

        # Detect new failure modes
        patterns.extend(self.detect_new_failure_modes(agent_name, baseline_sessions, recent_sessions))

        return patterns

    def detect_error_rate_trends(
        self,
        agent_name: str,
        baseline_sessions: list[Session],
        recent_sessions: list[Session],
    ) -> list[Pattern]:
        """Detect error rate trends comparing recent vs baseline sessions.

        Args:
            agent_name: Name of the agent
            baseline_sessions: Sessions from baseline period
            recent_sessions: Sessions from recent period

        Returns:
            List of Pattern objects for detected error rate trends
        """
        patterns: list[Pattern] = []

        # Calculate average error rate for baseline
        baseline_error_rate = self._calculate_average_error_rate(baseline_sessions)
        recent_error_rate = self._calculate_average_error_rate(recent_sessions)

        # Check if error rate increased significantly
        if baseline_error_rate > 0:  # Avoid division by zero
            change_percent = (recent_error_rate - baseline_error_rate) / baseline_error_rate
        else:
            change_percent = 1.0 if recent_error_rate > 0 else 0.0

        if (change_percent - self.error_rate_threshold) > 1e-9 and recent_error_rate > baseline_error_rate:
            severity = "critical" if change_percent >= self.error_rate_threshold * 2 else "warning"

            pattern = Pattern(
                pattern_type="error_trend",
                agent_name=agent_name,
                severity=severity,
                description=(
                    f"Error rate increased by {change_percent:.1%}: "
                    f"from {baseline_error_rate:.2%} to {recent_error_rate:.2%}"
                ),
                affected_sessions=[s.id for s in recent_sessions if s.errors > 0],
                detected_at=datetime.now(timezone.utc),
                baseline_value=baseline_error_rate,
                current_value=recent_error_rate,
                threshold=self.error_rate_threshold,
                change_percent=change_percent,
                metadata={
                    "baseline_session_count": len(baseline_sessions),
                    "recent_session_count": len(recent_sessions),
                    "baseline_errors": sum(s.errors for s in baseline_sessions),
                    "recent_errors": sum(s.errors for s in recent_sessions),
                },
            )
            patterns.append(pattern)

        return patterns

    def detect_tool_failure_frequency(
        self,
        agent_name: str,
        baseline_sessions: list[Session],
        recent_sessions: list[Session],
    ) -> list[Pattern]:
        """Detect changes in tool failure frequency.

        Uses tool_calls as a proxy for tool activity and errors as failure indicator.

        Args:
            agent_name: Name of the agent
            baseline_sessions: Sessions from baseline period
            recent_sessions: Sessions from recent period

        Returns:
            List of Pattern objects for detected tool failure patterns
        """
        patterns: list[Pattern] = []

        # Calculate tool failure rate (errors / tool_calls)
        baseline_failure_rate = self._calculate_tool_failure_rate(baseline_sessions)
        recent_failure_rate = self._calculate_tool_failure_rate(recent_sessions)

        # Check if failure rate increased significantly
        if baseline_failure_rate > 0:
            change_percent = (recent_failure_rate - baseline_failure_rate) / baseline_failure_rate
        else:
            change_percent = 1.0 if recent_failure_rate > 0 else 0.0

        if change_percent > self.tool_failure_threshold and recent_failure_rate > baseline_failure_rate:
            severity = "critical" if change_percent >= self.tool_failure_threshold * 2 else "warning"

            pattern = Pattern(
                pattern_type="tool_failure",
                agent_name=agent_name,
                severity=severity,
                description=(
                    f"Tool failure rate increased by {change_percent:.1%}: "
                    f"from {baseline_failure_rate:.2%} to {recent_failure_rate:.2%}"
                ),
                affected_sessions=[s.id for s in recent_sessions if s.errors > 0 and s.tool_calls > 0],
                detected_at=datetime.now(timezone.utc),
                baseline_value=baseline_failure_rate,
                current_value=recent_failure_rate,
                threshold=self.tool_failure_threshold,
                change_percent=change_percent,
                metadata={
                    "baseline_session_count": len(baseline_sessions),
                    "recent_session_count": len(recent_sessions),
                    "baseline_tool_calls": sum(s.tool_calls for s in baseline_sessions),
                    "recent_tool_calls": sum(s.tool_calls for s in recent_sessions),
                },
            )
            patterns.append(pattern)

        return patterns

    def detect_confidence_drops(
        self,
        agent_name: str,
        baseline_sessions: list[Session],
        recent_sessions: list[Session],
    ) -> list[Pattern]:
        """Detect drops in decision confidence.

        Note: This requires event-level confidence data. Currently a placeholder
        that can be enhanced when confidence tracking is available.

        Args:
            agent_name: Name of the agent
            baseline_sessions: Sessions from baseline period
            recent_sessions: Sessions from recent period

        Returns:
            List of Pattern objects for detected confidence drops
        """
        patterns: list[Pattern] = []

        # Placeholder: This would require event-level confidence data
        # For now, we can use replay_value as a proxy (lower replay_value might indicate issues)

        baseline_avg_replay = sum(s.replay_value for s in baseline_sessions) / len(baseline_sessions)
        recent_avg_replay = sum(s.replay_value for s in recent_sessions) / len(recent_sessions)

        if baseline_avg_replay > 0:
            change_percent = (recent_avg_replay - baseline_avg_replay) / baseline_avg_replay
        else:
            change_percent = 0.0

        # Significant drop in replay value might indicate issues
        if change_percent <= -self.confidence_drop_threshold:
            severity = "critical" if change_percent <= -self.confidence_drop_threshold * 2 else "warning"

            pattern = Pattern(
                pattern_type="confidence_drop",
                agent_name=agent_name,
                severity=severity,
                description=(
                    f"Session replay value dropped by {abs(change_percent):.1%}: "
                    f"from {baseline_avg_replay:.2f} to {recent_avg_replay:.2f}"
                ),
                affected_sessions=[s.id for s in recent_sessions if s.replay_value < baseline_avg_replay * 0.8],
                detected_at=datetime.now(timezone.utc),
                baseline_value=baseline_avg_replay,
                current_value=recent_avg_replay,
                threshold=self.confidence_drop_threshold,
                change_percent=change_percent,
                metadata={
                    "baseline_session_count": len(baseline_sessions),
                    "recent_session_count": len(recent_sessions),
                    "metric_used": "replay_value",  # Placeholder for actual confidence
                },
            )
            patterns.append(pattern)

        return patterns

    def detect_new_failure_modes(
        self,
        agent_name: str,
        baseline_sessions: list[Session],
        recent_sessions: list[Session],
    ) -> list[Pattern]:
        """Detect new failure modes that weren't present in baseline.

        Identifies error patterns in recent sessions that weren't seen during baseline.

        Args:
            agent_name: Name of the agent
            baseline_sessions: Sessions from baseline period
            recent_sessions: Sessions from recent period

        Returns:
            List of Pattern objects for detected new failure modes
        """
        patterns: list[Pattern] = []

        # For now, use session status and error counts as indicators
        # A full implementation would analyze error types from events

        baseline_error_sessions = len([s for s in baseline_sessions if s.errors > 0])
        recent_error_sessions = len([s for s in recent_sessions if s.errors > 0])

        # If recent sessions have significantly more error sessions
        if recent_error_sessions > baseline_error_sessions * 2:
            severity = "critical" if recent_error_sessions > baseline_error_sessions * 3 else "warning"

            pattern = Pattern(
                pattern_type="new_failure_mode",
                agent_name=agent_name,
                severity=severity,
                description=(
                    f"New failure pattern detected: "
                    f"{recent_error_sessions} recent sessions with errors vs "
                    f"{baseline_error_sessions} baseline sessions"
                ),
                affected_sessions=[s.id for s in recent_sessions if s.errors > 0],
                detected_at=datetime.now(timezone.utc),
                baseline_value=float(baseline_error_sessions),
                current_value=float(recent_error_sessions),
                threshold=2.0,  # 2x increase
                change_percent=(
                    (recent_error_sessions - baseline_error_sessions) / baseline_error_sessions
                    if baseline_error_sessions > 0
                    else 1.0
                ),
                metadata={
                    "baseline_session_count": len(baseline_sessions),
                    "recent_session_count": len(recent_sessions),
                    "baseline_error_sessions": baseline_error_sessions,
                    "recent_error_sessions": recent_error_sessions,
                },
            )
            patterns.append(pattern)

        return patterns

    def _calculate_average_error_rate(self, sessions: list[Session]) -> float:
        """Calculate average error rate across sessions.

        Error rate = sessions with errors / total sessions

        Args:
            sessions: List of sessions to analyze

        Returns:
            Average error rate (0.0 to 1.0)
        """
        if not sessions:
            return 0.0

        error_sessions = len([s for s in sessions if s.errors > 0])
        return error_sessions / len(sessions)

    def _calculate_tool_failure_rate(self, sessions: list[Session]) -> float:
        """Calculate tool failure rate across sessions.

        Tool failure rate = errors / tool_calls (across all sessions)

        Args:
            sessions: List of sessions to analyze

        Returns:
            Tool failure rate (0.0 to 1.0)
        """
        if not sessions:
            return 0.0

        total_errors = sum(s.errors for s in sessions)
        total_tool_calls = sum(s.tool_calls for s in sessions)

        if total_tool_calls == 0:
            return 0.0

        return total_errors / total_tool_calls
