"""Divergence detection primitives for comparing agent execution traces.

Based on divergence analysis research for multi-agent systems, this module provides
tools for detecting behavioral, temporal, and structural divergences between sessions
and execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent_debugger_sdk.core._compat import StrEnum
from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "DivergenceType",
    "DivergenceSeverity",
    "DivergencePoint",
    "SessionComparison",
    "detect_divergences",
    "compare_session_structures",
    "analyze_temporal_divergence",
    "analyze_behavioral_divergence",
]


class DivergenceType(StrEnum):
    """Types of divergences between sessions or execution paths."""

    STRUCTURAL = "structural"  # Differences in event tree structure
    TEMPORAL = "temporal"  # Differences in timing and sequence
    BEHAVIORAL = "behavioral"  # Differences in agent decisions and actions
    STATE = "state"  # Differences in checkpoint states
    ERROR = "error"  # One session diverged due to errors
    PERFORMANCE = "performance"  # Differences in resource usage


class DivergenceSeverity(StrEnum):
    """Severity levels for detected divergences."""

    CRITICAL = "critical"  # Fundamental divergence affecting outcome
    HIGH = "high"  # Significant deviation from expected path
    MEDIUM = "medium"  # Moderate difference worth investigation
    LOW = "low"  # Minor difference with minimal impact


@dataclass(kw_only=True)
class DivergencePoint:
    """A specific point where two sessions or paths diverge."""

    divergence_type: DivergenceType
    severity: DivergenceSeverity
    primary_event_id: str | None = None
    secondary_event_id: str | None = None
    description: str = ""
    timestamp: datetime | None = None
    divergence_score: float = 0.0  # 0.0 to 1.0, higher = more divergent
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "divergence_type": str(self.divergence_type),
            "severity": str(self.severity),
            "primary_event_id": self.primary_event_id,
            "secondary_event_id": self.secondary_event_id,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "divergence_score": self.divergence_score,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class SessionComparison:
    """Result of comparing two sessions for divergences."""

    primary_session_id: str
    secondary_session_id: str
    divergence_points: list[DivergencePoint] = field(default_factory=list)
    overall_divergence_score: float = 0.0
    structural_similarity: float = 1.0
    temporal_similarity: float = 1.0
    behavioral_similarity: float = 1.0
    comparison_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "primary_session_id": self.primary_session_id,
            "secondary_session_id": self.secondary_session_id,
            "divergence_points": [dp.to_dict() for dp in self.divergence_points],
            "overall_divergence_score": self.overall_divergence_score,
            "structural_similarity": self.structural_similarity,
            "temporal_similarity": self.temporal_similarity,
            "behavioral_similarity": self.behavioral_similarity,
            "comparison_summary": dict(self.comparison_summary),
        }


def detect_divergences(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
    primary_checkpoints: list[Any] | None = None,
    secondary_checkpoints: list[Any] | None = None,
) -> SessionComparison:
    """Detect divergences between two session execution traces.

    Args:
        primary_events: Event trace from the primary session
        secondary_events: Event trace from the secondary session
        primary_checkpoints: Optional checkpoints from primary session
        secondary_checkpoints: Optional checkpoints from secondary session

    Returns:
        SessionComparison with detected divergences and similarity scores
    """
    if not primary_events and not secondary_events:
        return SessionComparison(
            primary_session_id="",
            secondary_session_id="",
            overall_divergence_score=0.0,
            structural_similarity=1.0,
            temporal_similarity=1.0,
            behavioral_similarity=1.0,
        )

    # Get session IDs from events if available
    primary_id = primary_events[0].session_id if primary_events else ""
    secondary_id = secondary_events[0].session_id if secondary_events else ""

    comparison = SessionComparison(
        primary_session_id=primary_id,
        secondary_session_id=secondary_id,
    )

    # Analyze structural divergence
    structural_div = _analyze_structural_divergence(primary_events, secondary_events)
    comparison.structural_similarity = 1.0 - structural_div["divergence_score"]
    comparison.divergence_points.extend(structural_div["divergence_points"])

    # Analyze temporal divergence
    temporal_div = _analyze_temporal_divergence(primary_events, secondary_events)
    comparison.temporal_similarity = 1.0 - temporal_div["divergence_score"]
    comparison.divergence_points.extend(temporal_div["divergence_points"])

    # Analyze behavioral divergence
    behavioral_div = _analyze_behavioral_divergence(primary_events, secondary_events)
    comparison.behavioral_similarity = 1.0 - behavioral_div["divergence_score"]
    comparison.divergence_points.extend(behavioral_div["divergence_points"])

    # Analyze state divergence if checkpoints provided
    if primary_checkpoints and secondary_checkpoints:
        state_div = _analyze_state_divergence(primary_checkpoints, secondary_checkpoints)
        comparison.divergence_points.extend(state_div["divergence_points"])

    # Calculate overall divergence score
    comparison.overall_divergence_score = (
        structural_div["divergence_score"] * 0.4 +
        temporal_div["divergence_score"] * 0.3 +
        behavioral_div["divergence_score"] * 0.3
    )

    # Build summary
    comparison.comparison_summary = {
        "primary_event_count": len(primary_events),
        "secondary_event_count": len(secondary_events),
        "total_divergences": len(comparison.divergence_points),
        "critical_divergences": len([
            d for d in comparison.divergence_points
            if d.severity == DivergenceSeverity.CRITICAL
        ]),
        "divergence_by_type": _count_divergences_by_type(comparison.divergence_points),
    }

    return comparison


def compare_session_structures(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Compare the structural properties of two sessions.

    Args:
        primary_events: Event trace from primary session
        secondary_events: Event trace from secondary session

    Returns:
        Dictionary with structural comparison metrics
    """
    primary_tree = _build_event_tree(primary_events)
    secondary_tree = _build_event_tree(secondary_events)

    return {
        "primary_depth": _max_tree_depth(primary_tree),
        "secondary_depth": _max_tree_depth(secondary_tree),
        "primary_branching_factor": _avg_branching_factor(primary_tree),
        "secondary_branching_factor": _avg_branching_factor(secondary_tree),
        "event_type_distribution_primary": _get_event_distribution(primary_events),
        "event_type_distribution_secondary": _get_event_distribution(secondary_events),
        "structural_similarity": _calculate_structural_similarity(primary_tree, secondary_tree),
    }


def analyze_temporal_divergence(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Analyze temporal patterns and timing divergences between sessions.

    Args:
        primary_events: Event trace from primary session
        secondary_events: Event trace from secondary session

    Returns:
        Dictionary with temporal analysis results
    """
    if not primary_events or not secondary_events:
        return {
            "primary_duration_seconds": 0.0,
            "secondary_duration_seconds": 0.0,
            "temporal_divergence_score": 0.0,
            "timing_differences": [],
        }

    primary_duration = _calculate_session_duration(primary_events)
    secondary_duration = _calculate_session_duration(secondary_events)

    timing_diffs = _compare_timing_patterns(primary_events, secondary_events)

    return {
        "primary_duration_seconds": primary_duration,
        "secondary_duration_seconds": secondary_duration,
        "duration_difference_seconds": abs(primary_duration - secondary_duration),
        "temporal_divergence_score": _calculate_temporal_divergence_score(timing_diffs),
        "timing_differences": timing_diffs[:10],  # Limit to 10 most significant
    }


def analyze_behavioral_divergence(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Analyze behavioral differences between agent sessions.

    Args:
        primary_events: Event trace from primary session
        secondary_events: Event trace from secondary session

    Returns:
        Dictionary with behavioral analysis results
    """
    primary_decisions = [e for e in primary_events if e.event_type == EventType.DECISION]
    secondary_decisions = [e for e in secondary_events if e.event_type == EventType.DECISION]

    primary_tools = [e for e in primary_events if e.event_type == EventType.TOOL_CALL]
    secondary_tools = [e for e in secondary_events if e.event_type == EventType.TOOL_CALL]

    decision_divergences = _compare_decision_patterns(primary_decisions, secondary_decisions)
    tool_divergences = _compare_tool_usage(primary_tools, secondary_tools)

    return {
        "primary_decision_count": len(primary_decisions),
        "secondary_decision_count": len(secondary_decisions),
        "primary_tool_call_count": len(primary_tools),
        "secondary_tool_call_count": len(secondary_tools),
        "decision_divergences": decision_divergences[:10],
        "tool_divergences": tool_divergences[:10],
        "behavioral_divergence_score": _calculate_behavioral_divergence_score(
            decision_divergences, tool_divergences
        ),
    }


# ===========================================================================
# Internal helper functions
# ===========================================================================


def _analyze_structural_divergence(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Analyze structural differences between event traces."""
    divergences: list[DivergencePoint] = []
    divergence_score = 0.0

    # Compare event counts
    count_diff = abs(len(primary_events) - len(secondary_events))
    if count_diff > 0:
        severity = _severity_for_count_difference(count_diff)
        divergences.append(DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=severity,
            description=f"Event count differs by {count_diff} events",
            divergence_score=min(count_diff / 10.0, 1.0),
        ))

    # Compare event type distributions
    primary_dist = _get_event_distribution(primary_events)
    secondary_dist = _get_event_distribution(secondary_events)

    for event_type in set(list(primary_dist.keys()) + list(secondary_dist.keys())):
        p_count = primary_dist.get(event_type, 0)
        s_count = secondary_dist.get(event_type, 0)
        if p_count != s_count:
            divergences.append(DivergencePoint(
                divergence_type=DivergenceType.STRUCTURAL,
                severity=DivergenceSeverity.MEDIUM,
                description=f"Event type {event_type} count differs: {p_count} vs {s_count}",
                divergence_score=abs(p_count - s_count) / max(p_count, s_count, 1),
            ))

    # Calculate overall structural divergence score
    divergence_score = min(len(divergences) / 10.0, 1.0)

    return {
        "divergence_score": divergence_score,
        "divergence_points": divergences,
    }


def _analyze_temporal_divergence(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Analyze temporal differences between event traces."""
    divergences: list[DivergencePoint] = []

    timing_diffs = _compare_timing_patterns(primary_events, secondary_events)

    for diff in timing_diffs:
        if diff["time_difference_seconds"] > 5.0:  # More than 5 seconds difference
            divergences.append(DivergencePoint(
                divergence_type=DivergenceType.TEMPORAL,
                severity=_severity_for_timing_difference(diff["time_difference_seconds"]),
                description=diff["description"],
                timestamp=diff.get("timestamp"),
                divergence_score=min(diff["time_difference_seconds"] / 60.0, 1.0),
                metadata=diff,
            ))

    divergence_score = min(len(divergences) / 10.0, 1.0) if divergences else 0.0

    return {
        "divergence_score": divergence_score,
        "divergence_points": divergences,
    }


def _analyze_behavioral_divergence(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> dict[str, Any]:
    """Analyze behavioral differences between event traces."""
    divergences: list[DivergencePoint] = []

    # Compare decision patterns
    primary_decisions = [e for e in primary_events if e.event_type == EventType.DECISION]
    secondary_decisions = [e for e in secondary_events if e.event_type == EventType.DECISION]

    decision_diffs = _compare_decision_patterns(primary_decisions, secondary_decisions)
    for diff in decision_diffs:
        divergences.append(DivergencePoint(
            divergence_type=DivergenceType.BEHAVIORAL,
            severity=DivergenceSeverity.HIGH if diff["confidence_difference"] > 0.5 else DivergenceSeverity.MEDIUM,
            description=diff["description"],
            divergence_score=abs(diff["confidence_difference"]),
            metadata=diff,
        ))

    # Compare tool usage
    primary_tools = [e for e in primary_events if e.event_type == EventType.TOOL_CALL]
    secondary_tools = [e for e in secondary_events if e.event_type == EventType.TOOL_CALL]

    tool_diffs = _compare_tool_usage(primary_tools, secondary_tools)
    for diff in tool_diffs:
        divergences.append(DivergencePoint(
            divergence_type=DivergenceType.BEHAVIORAL,
            severity=DivergenceSeverity.MEDIUM,
            description=diff["description"],
            divergence_score=0.7 if diff["tool_only_in_one"] else 0.3,
            metadata=diff,
        ))

    divergence_score = min(len(divergences) / 10.0, 1.0) if divergences else 0.0

    return {
        "divergence_score": divergence_score,
        "divergence_points": divergences,
    }


def _analyze_state_divergence(
    primary_checkpoints: list[Any],
    secondary_checkpoints: list[Any],
) -> dict[str, Any]:
    """Analyze state differences between checkpoints."""
    divergences: list[DivergencePoint] = []

    # Pair up checkpoints by sequence
    paired = _pair_checkpoints_by_sequence(primary_checkpoints, secondary_checkpoints)

    for primary_cp, secondary_cp in paired:
        if primary_cp and secondary_cp:
            # Compare states
            state_diff = _compare_checkpoint_states(primary_cp, secondary_cp)
            if state_diff["significant_difference"]:
                divergences.append(DivergencePoint(
                    divergence_type=DivergenceType.STATE,
                    severity=DivergenceSeverity.MEDIUM,
                    description=f"State divergence at checkpoint {primary_cp.sequence}",
                    timestamp=primary_cp.timestamp,
                    divergence_score=state_diff["divergence_score"],
                    metadata=state_diff,
                ))

    return {
        "divergence_score": min(len(divergences) / 5.0, 1.0) if divergences else 0.0,
        "divergence_points": divergences,
    }


def _build_event_tree(events: list[TraceEvent]) -> dict[str, list[str]]:
    """Build a tree structure from events based on parent-child relationships."""
    tree: dict[str, list[str]] = {}

    for event in events:
        if event.id not in tree:
            tree[event.id] = []

        if event.parent_id and event.parent_id in tree:
            tree[event.parent_id].append(event.id)

    return tree


def _max_tree_depth(tree: dict[str, list[str]]) -> int:
    """Calculate the maximum depth of an event tree."""
    if not tree:
        return 0

    roots = [node_id for node_id in tree if not any(node_id in children for children in tree.values())]

    max_depth = 0
    for root in roots:
        depth = _calculate_depth(tree, root, 0)
        max_depth = max(max_depth, depth)

    return max_depth


def _calculate_depth(tree: dict[str, list[str]], node_id: str, current_depth: int) -> int:
    """Recursively calculate depth from a node."""
    if node_id not in tree or not tree[node_id]:
        return current_depth

    max_child_depth = current_depth
    for child_id in tree[node_id]:
        child_depth = _calculate_depth(tree, child_id, current_depth + 1)
        max_child_depth = max(max_child_depth, child_depth)

    return max_child_depth


def _avg_branching_factor(tree: dict[str, list[str]]) -> float:
    """Calculate average branching factor of the tree."""
    if not tree:
        return 0.0

    branching_factors = [len(children) for children in tree.values()]
    return sum(branching_factors) / len(branching_factors) if branching_factors else 0.0


def _get_event_distribution(events: list[TraceEvent]) -> dict[str, int]:
    """Get count distribution of event types."""
    distribution: dict[str, int] = {}
    for event in events:
        event_type_str = str(event.event_type)
        distribution[event_type_str] = distribution.get(event_type_str, 0) + 1
    return distribution


def _calculate_structural_similarity(
    primary_tree: dict[str, list[str]],
    secondary_tree: dict[str, list[str]],
) -> float:
    """Calculate structural similarity between two event trees."""
    if not primary_tree and not secondary_tree:
        return 1.0
    if not primary_tree or not secondary_tree:
        return 0.0

    primary_depth = _max_tree_depth(primary_tree)
    secondary_depth = _max_tree_depth(secondary_tree)

    depth_similarity = 1.0 - abs(primary_depth - secondary_depth) / max(primary_depth, secondary_depth, 1)

    primary_branching = _avg_branching_factor(primary_tree)
    secondary_branching = _avg_branching_factor(secondary_tree)

    branching_similarity = (
        1.0
        - abs(primary_branching - secondary_branching)
        / max(primary_branching, secondary_branching, 1)
    )

    return (depth_similarity + branching_similarity) / 2.0


def _calculate_session_duration(events: list[TraceEvent]) -> float:
    """Calculate total duration of a session in seconds."""
    if not events:
        return 0.0

    timestamps = [e.timestamp for e in events if e.timestamp]
    if not timestamps:
        return 0.0

    return (max(timestamps) - min(timestamps)).total_seconds()


def _compare_timing_patterns(
    primary_events: list[TraceEvent],
    secondary_events: list[TraceEvent],
) -> list[dict[str, Any]]:
    """Compare timing patterns between two sessions."""
    timing_diffs: list[dict[str, Any]] = []

    if not primary_events or not secondary_events:
        return timing_diffs

    # Compare session-level timing
    primary_duration = _calculate_session_duration(primary_events)
    secondary_duration = _calculate_session_duration(secondary_events)

    duration_diff = abs(primary_duration - secondary_duration)
    if duration_diff > 1.0:  # More than 1 second difference
        timing_diffs.append({
            "type": "session_duration",
            "time_difference_seconds": duration_diff,
            "description": f"Session duration differs by {duration_diff:.2f}s",
        })

    return timing_diffs


def _calculate_temporal_divergence_score(timing_diffs: list[dict[str, Any]]) -> float:
    """Calculate overall temporal divergence score."""
    if not timing_diffs:
        return 0.0

    total_diff = sum(diff["time_difference_seconds"] for diff in timing_diffs)
    return min(total_diff / 60.0, 1.0)  # Normalize to 0-1 range


def _compare_decision_patterns(
    primary_decisions: list[TraceEvent],
    secondary_decisions: list[TraceEvent],
) -> list[dict[str, Any]]:
    """Compare decision patterns between two sessions."""
    diffs: list[dict[str, Any]] = []

    min_len = min(len(primary_decisions), len(secondary_decisions))

    for i in range(min_len):
        primary_conf = getattr(primary_decisions[i], "confidence", None)
        secondary_conf = getattr(secondary_decisions[i], "confidence", None)

        if primary_conf is not None and secondary_conf is not None:
            conf_diff = abs(primary_conf - secondary_conf)
            if conf_diff > 0.2:  # Significant confidence difference
                diffs.append({
                    "index": i,
                    "primary_confidence": primary_conf,
                    "secondary_confidence": secondary_conf,
                    "confidence_difference": conf_diff,
                    "description": f"Decision {i}: confidence differs by {conf_diff:.2f}",
                })

    return diffs


def _compare_tool_usage(
    primary_tools: list[TraceEvent],
    secondary_tools: list[TraceEvent],
) -> list[dict[str, Any]]:
    """Compare tool usage patterns between two sessions."""
    diffs: list[dict[str, Any]] = []

    # Get tool names from both sessions
    primary_tool_names = set()
    secondary_tool_names = set()

    for event in primary_tools:
        tool_name = getattr(event, "tool_name", None)
        if tool_name:
            primary_tool_names.add(tool_name)

    for event in secondary_tools:
        tool_name = getattr(event, "tool_name", None)
        if tool_name:
            secondary_tool_names.add(tool_name)

    # Find tools only used in one session
    only_in_primary = primary_tool_names - secondary_tool_names
    only_in_secondary = secondary_tool_names - primary_tool_names

    for tool_name in only_in_primary:
        diffs.append({
            "tool_name": tool_name,
            "tool_only_in_one": True,
            "description": f"Tool {tool_name} only used in primary session",
        })

    for tool_name in only_in_secondary:
        diffs.append({
            "tool_name": tool_name,
            "tool_only_in_one": True,
            "description": f"Tool {tool_name} only used in secondary session",
        })

    return diffs


def _calculate_behavioral_divergence_score(
    decision_diffs: list[dict[str, Any]],
    tool_diffs: list[dict[str, Any]],
) -> float:
    """Calculate overall behavioral divergence score."""
    decision_score = min(len(decision_diffs) / 5.0, 1.0)
    tool_score = min(len(tool_diffs) / 5.0, 1.0)

    return (decision_score + tool_score) / 2.0


def _pair_checkpoints_by_sequence(
    primary_checkpoints: list[Any],
    secondary_checkpoints: list[Any],
) -> list[tuple[Any | None, Any | None]]:
    """Pair checkpoints by their sequence number."""
    paired: list[tuple[Any | None, Any | None]] = []

    primary_by_seq = {cp.sequence: cp for cp in primary_checkpoints}
    secondary_by_seq = {cp.sequence: cp for cp in secondary_checkpoints}

    all_sequences = set(list(primary_by_seq.keys()) + list(secondary_by_seq.keys()))

    for seq in sorted(all_sequences):
        paired.append((primary_by_seq.get(seq), secondary_by_seq.get(seq)))

    return paired


def _compare_checkpoint_states(primary_cp: Any, secondary_cp: Any) -> dict[str, Any]:
    """Compare states of two checkpoints."""
    if not primary_cp.state or not secondary_cp.state:
        return {
            "significant_difference": False,
            "divergence_score": 0.0,
        }

    primary_state = primary_cp.state if isinstance(primary_cp.state, dict) else {}
    secondary_state = secondary_cp.state if isinstance(secondary_cp.state, dict) else {}

    # Compare state keys
    all_keys = set(list(primary_state.keys()) + list(secondary_state.keys()))
    differences = 0

    for key in all_keys:
        p_val = primary_state.get(key)
        s_val = secondary_state.get(key)

        if p_val != s_val:
            differences += 1

    divergence_score = differences / max(len(all_keys), 1)

    return {
        "significant_difference": differences > 0,
        "divergence_score": divergence_score,
        "different_keys_count": differences,
        "total_keys": len(all_keys),
    }


def _count_divergences_by_type(divergence_points: list[DivergencePoint]) -> dict[str, int]:
    """Count divergences by their type."""
    counts: dict[str, int] = {}
    for dp in divergence_points:
        dtype = str(dp.divergence_type)
        counts[dtype] = counts.get(dtype, 0) + 1
    return counts


def _severity_for_count_difference(count_diff: int) -> DivergenceSeverity:
    """Determine severity based on count difference."""
    if count_diff > 20:
        return DivergenceSeverity.CRITICAL
    elif count_diff > 10:
        return DivergenceSeverity.HIGH
    elif count_diff > 5:
        return DivergenceSeverity.MEDIUM
    else:
        return DivergenceSeverity.LOW


def _severity_for_timing_difference(time_diff: float) -> DivergenceSeverity:
    """Determine severity based on timing difference."""
    if time_diff > 60.0:  # More than 1 minute
        return DivergenceSeverity.HIGH
    elif time_diff > 30.0:  # More than 30 seconds
        return DivergenceSeverity.MEDIUM
    else:
        return DivergenceSeverity.LOW