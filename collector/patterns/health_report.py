"""Agent health report generation for pattern analysis.

This module provides the generate_health_report function which creates
comprehensive health reports for agents based on detected patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from collector.patterns.pattern_detector import Pattern


@dataclass
class HealthReport:
    """Comprehensive health report for agent analysis.

    Attributes:
        generated_at: When the report was generated
        overall_health_score: Overall health score (0-100, 100 = healthy)
        agent_summary: Summary of agent health status
        total_patterns: Total number of active patterns
        patterns_by_severity: Breakdown of patterns by severity
        patterns_by_type: Breakdown of patterns by type
        critical_patterns: List of critical patterns requiring attention
        top_issues: Top 5 issues requiring immediate attention
        recommendations: Actionable recommendations based on detected patterns
        affected_agents: List of agents with detected patterns
        trend_metrics: Summary of trending metrics
    """

    generated_at: datetime
    overall_health_score: float
    agent_summary: str
    total_patterns: int
    patterns_by_severity: dict[str, int]
    patterns_by_type: dict[str, int]
    critical_patterns: list[dict[str, Any]]
    top_issues: list[dict[str, Any]]
    recommendations: list[str]
    affected_agents: list[str]
    trend_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize health report to dictionary."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall_health_score": round(self.overall_health_score, 1),
            "agent_summary": self.agent_summary,
            "total_patterns": self.total_patterns,
            "patterns_by_severity": self.patterns_by_severity,
            "patterns_by_type": self.patterns_by_type,
            "critical_patterns": self.critical_patterns,
            "top_issues": self.top_issues,
            "recommendations": self.recommendations,
            "affected_agents": self.affected_agents,
            "trend_metrics": self.trend_metrics,
        }


def generate_health_report(
    patterns: list[Pattern],
    *,
    total_sessions: int = 0,
    total_agents: int = 0,
    baseline_metrics: dict[str, Any] | None = None,
) -> HealthReport:
    """Generate a comprehensive health report from detected patterns.

    Args:
        patterns: List of detected Pattern objects
        total_sessions: Total number of sessions analyzed
        total_agents: Total number of agents analyzed
        baseline_metrics: Optional baseline metrics for comparison

    Returns:
        HealthReport object with comprehensive analysis
    """
    # Calculate overall health score (starts at 100, decreases for each pattern)
    health_score = 100.0

    # Count patterns by severity and type
    patterns_by_severity: dict[str, int] = {"critical": 0, "warning": 0}
    patterns_by_type: dict[str, int] = {
        "error_trend": 0,
        "tool_failure": 0,
        "confidence_drop": 0,
        "new_failure_mode": 0,
    }

    for pattern in patterns:
        patterns_by_severity[pattern.severity] += 1
        patterns_by_type[pattern.pattern_type] += 1

        # Decrease health score based on severity
        if pattern.severity == "critical":
            health_score -= 15
        elif pattern.severity == "warning":
            health_score -= 5

    # Ensure health score doesn't go below 0
    health_score = max(0.0, health_score)

    # Generate agent summary
    affected_agents = list(set(p.agent_name for p in patterns))
    critical_count = patterns_by_severity["critical"]
    warning_count = patterns_by_severity["warning"]

    if critical_count > 3:
        agent_summary = f"CRITICAL: {critical_count} critical patterns detected across {len(affected_agents)} agents"
    elif critical_count > 0:
        agent_summary = f"WARNING: {critical_count} critical and {warning_count} warning patterns detected"
    elif warning_count > 5:
        agent_summary = f"CAUTION: {warning_count} warning patterns detected across {len(affected_agents)} agents"
    elif warning_count > 0:
        agent_summary = f"STABLE: {warning_count} minor issues detected"
    else:
        agent_summary = "HEALTHY: No significant patterns detected"

    # Extract critical patterns
    critical_patterns = [
        {
            "pattern_type": p.pattern_type,
            "agent_name": p.agent_name,
            "description": p.description,
            "affected_session_count": len(p.affected_sessions),
            "change_percent": p.change_percent,
            "detected_at": p.detected_at.isoformat(),
        }
        for p in patterns
        if p.severity == "critical"
    ]

    # Generate top issues (prioritized by severity and impact)
    # Critical patterns should come first, then by highest change_percent
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    all_patterns_sorted = sorted(
        patterns,
        key=lambda p: (
            severity_order.get(p.severity, 1),
            -(p.change_percent or 0),
            len(p.affected_sessions),
        ),
        reverse=False,
    )

    top_issues = [
        {
            "rank": i + 1,
            "pattern_type": p.pattern_type,
            "agent_name": p.agent_name,
            "severity": p.severity,
            "description": p.description,
            "affected_session_count": len(p.affected_sessions),
            "recommendation": _generate_recommendation_for_pattern(p),
        }
        for i, p in enumerate(all_patterns_sorted[:5])
    ]

    # Generate actionable recommendations
    recommendations = _generate_recommendations(
        patterns,
        patterns_by_severity,
        patterns_by_type,
        health_score,
    )

    # Calculate trend metrics
    trend_metrics = _calculate_trend_metrics(patterns, baseline_metrics)

    return HealthReport(
        generated_at=datetime.now(timezone.utc),
        overall_health_score=health_score,
        agent_summary=agent_summary,
        total_patterns=len(patterns),
        patterns_by_severity=patterns_by_severity,
        patterns_by_type=patterns_by_type,
        critical_patterns=critical_patterns,
        top_issues=top_issues,
        recommendations=recommendations,
        affected_agents=affected_agents,
        trend_metrics=trend_metrics,
    )


def _generate_recommendation_for_pattern(pattern: Pattern) -> str:
    """Generate a specific recommendation for a given pattern.

    Args:
        pattern: Pattern to generate recommendation for

    Returns:
        Actionable recommendation string
    """
    if pattern.pattern_type == "error_trend":
        return (
            f"Investigate recent sessions for {pattern.agent_name}: "
            f"error rate increased by {(pattern.change_percent or 0):.1%}. "
            f"Review error handling and retry logic."
        )
    elif pattern.pattern_type == "tool_failure":
        return (
            f"Review tool integration for {pattern.agent_name}: "
            f"tool failure rate increased by {(pattern.change_percent or 0):.1%}. "
            f"Check tool API availability and error handling."
        )
    elif pattern.pattern_type == "confidence_drop":
        return (
            f"Analyze decision quality for {pattern.agent_name}: "
            f"confidence dropped by {abs(pattern.change_percent or 0):.1%}. "
            f"Review prompt engineering and context provision."
        )
    elif pattern.pattern_type == "new_failure_mode":
        return (
            f"New failure mode detected for {pattern.agent_name}: "
            f"analyze affected sessions to identify root cause and add test coverage."
        )
    else:
        return "Investigate the detected pattern and implement appropriate fixes."


def _generate_recommendations(
    patterns: list[Pattern],
    patterns_by_severity: dict[str, int],
    patterns_by_type: dict[str, int],
    health_score: float,
) -> list[str]:
    """Generate actionable recommendations based on detected patterns.

    Args:
        patterns: List of detected patterns
        patterns_by_severity: Breakdown of patterns by severity
        patterns_by_type: Breakdown of patterns by type
        health_score: Overall health score

    Returns:
        List of recommendation strings
    """
    recommendations: list[str] = []

    # Critical issues first
    if patterns_by_severity["critical"] > 0:
        recommendations.append(
            f"URGENT: Address {patterns_by_severity['critical']} critical pattern(s) immediately"
        )

    # Pattern-specific recommendations
    if patterns_by_type["error_trend"] > 0:
        if patterns_by_type["error_trend"] > 2:
            recommendations.append(
                "Multiple agents showing error rate increases - review shared infrastructure"
            )
        else:
            recommendations.append(
                "Error rate increasing - investigate affected sessions and review error handling"
            )

    if patterns_by_type["tool_failure"] > 0:
        if patterns_by_type["tool_failure"] > 2:
            recommendations.append(
                "Widespread tool failures detected - check external service dependencies"
            )
        else:
            recommendations.append(
                "Tool failures detected - review tool integration and error handling"
            )

    if patterns_by_type["confidence_drop"] > 0:
        recommendations.append(
            "Decision confidence dropping - review LLM prompts and context windows"
        )

    if patterns_by_type["new_failure_mode"] > 0:
        recommendations.append(
            "New failure modes detected - update test suite to cover these scenarios"
        )

    # Health-based recommendations
    if health_score < 50:
        recommendations.append(
            "Overall health is critical - consider temporarily reducing traffic while investigating"
        )
    elif health_score < 75:
        recommendations.append(
            "Overall health is degraded - monitor closely and address issues systematically"
        )

    # Generic recommendation if no patterns
    if not patterns:
        recommendations.append("All systems healthy - continue regular monitoring")

    return recommendations


def _calculate_trend_metrics(
    patterns: list[Pattern],
    baseline_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calculate summary trend metrics from patterns.

    Args:
        patterns: List of detected patterns
        baseline_metrics: Optional baseline metrics for comparison

    Returns:
        Dictionary of trend metrics
    """
    metrics: dict[str, Any] = {}

    if not patterns:
        return {
            "avg_error_rate_change": 0.0,
            "avg_tool_failure_change": 0.0,
            "agents_with_issues": 0,
            "total_affected_sessions": 0,
        }

    # Calculate average changes
    error_trends = [p.change_percent for p in patterns if p.pattern_type == "error_trend" and p.change_percent]
    tool_failures = [p.change_percent for p in patterns if p.pattern_type == "tool_failure" and p.change_percent]

    metrics["avg_error_rate_change"] = sum(error_trends) / len(error_trends) if error_trends else 0.0
    metrics["avg_tool_failure_change"] = sum(tool_failures) / len(tool_failures) if tool_failures else 0.0
    metrics["agents_with_issues"] = len(set(p.agent_name for p in patterns))
    metrics["total_affected_sessions"] = sum(len(p.affected_sessions) for p in patterns)

    return metrics
