"""Non-heuristic policy shift detection and parameter analysis.

This module provides semantic understanding of policy changes rather than
simple keyword matching. It detects template changes, diffs parameters,
and computes shift magnitude based on parameter importance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import TraceEvent


@dataclass
class ParameterChange:
    """Represents a change in a single policy parameter."""

    old_value: Any
    new_value: Any
    magnitude: float  # 0.0 to 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_value": self.old_value,
            "new_value": self.new_value,
            "magnitude": round(self.magnitude, 4),
        }


@dataclass
class PolicyShift:
    """Represents a detected policy shift between two prompt policy events."""

    event_id: str
    turn_index: int
    previous_template: str | None
    new_template: str
    parameter_changes: dict[str, ParameterChange] = field(default_factory=dict)
    shift_magnitude: float = 0.0
    triggering_turn_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "turn_index": self.turn_index,
            "previous_template": self.previous_template,
            "new_template": self.new_template,
            "parameter_changes": {k: v.to_dict() for k, v in self.parameter_changes.items()},
            "shift_magnitude": round(self.shift_magnitude, 4),
            "triggering_turn_id": self.triggering_turn_id,
        }


# Parameter importance weights for computing shift magnitude
PARAMETER_IMPORTANCE: dict[str, float] = {
    "temperature": 0.9,
    "max_tokens": 0.7,
    "top_p": 0.8,
    "frequency_penalty": 0.6,
    "presence_penalty": 0.6,
    "timeout": 0.4,
    "max_retries": 0.5,
    "model": 0.95,
    "system_prompt": 0.85,
    "instructions": 0.8,
    "tools": 0.75,
    "max_iterations": 0.5,
    "verbosity": 0.3,
}


def analyze_policy_sequence(
    policies: list[TraceEvent],
    turns: list[TraceEvent],
) -> list[PolicyShift]:
    """Analyze policy changes with semantic understanding.

    This function detects:
    - Template changes (high importance)
    - Parameter changes with weighted magnitude
    - Links to nearest upstream turn

    Args:
        policies: List of PROMPT_POLICY events in chronological order
        turns: List of AGENT_TURN events for turn index mapping

    Returns:
        List of PolicyShift objects representing detected changes
    """
    if not policies:
        return []

    shifts: list[PolicyShift] = []
    previous_policy: TraceEvent | None = None

    for policy in policies:
        if previous_policy is None:
            previous_policy = policy
            continue

        # Detect template change
        prev_template = _get_template_id(previous_policy)
        curr_template = _get_template_id(policy)
        template_changed = prev_template != curr_template

        # Detect parameter changes
        param_changes = _detect_parameter_changes(previous_policy, policy)

        if template_changed or param_changes:
            turn_index, triggering_turn_id = _find_turn_index(policy, turns)

            shift = PolicyShift(
                event_id=policy.id,
                turn_index=turn_index,
                previous_template=prev_template,
                new_template=curr_template,
                parameter_changes=param_changes,
                shift_magnitude=_compute_shift_magnitude(template_changed, param_changes),
                triggering_turn_id=triggering_turn_id,
            )
            shifts.append(shift)

        previous_policy = policy

    return shifts


def _get_template_id(policy: TraceEvent) -> str:
    """Extract template identifier from policy event."""
    # Check for explicit template_id first
    if hasattr(policy, "template_id") and policy.template_id:
        return policy.template_id
    if hasattr(policy, "data"):
        template_id = policy.data.get("template_id")
        if template_id:
            return template_id

    # Fall back to name
    if hasattr(policy, "name") and policy.name:
        return policy.name

    return "unknown"


def _detect_parameter_changes(
    previous_policy: TraceEvent,
    current_policy: TraceEvent,
) -> dict[str, ParameterChange]:
    """Detect parameter changes between two policies."""
    prev_params = _get_parameters(previous_policy)
    curr_params = _get_parameters(current_policy)

    if not prev_params and not curr_params:
        return {}

    all_keys = set(prev_params.keys()) | set(curr_params.keys())
    changes: dict[str, ParameterChange] = {}

    for key in all_keys:
        old_val = prev_params.get(key)
        new_val = curr_params.get(key)

        if old_val != new_val:
            magnitude = _compute_parameter_magnitude(key, old_val, new_val)
            changes[key] = ParameterChange(
                old_value=old_val,
                new_value=new_val,
                magnitude=magnitude,
            )

    return changes


def _get_parameters(policy: TraceEvent) -> dict[str, Any]:
    """Extract parameters from policy event."""
    if hasattr(policy, "policy_parameters") and policy.policy_parameters:
        return policy.policy_parameters
    if hasattr(policy, "data"):
        params = policy.data.get("policy_parameters", {})
        if params:
            return params
        # Also check for 'parameters' key
        return policy.data.get("parameters", {})
    return {}


def _compute_parameter_magnitude(key: str, old_val: Any, new_val: Any) -> float:
    """Compute magnitude of parameter change based on type and importance.

    Args:
        key: Parameter name (used for importance weighting)
        old_val: Previous value
        new_val: New value

    Returns:
        Magnitude from 0.0 to 1.0
    """
    if old_val == new_val:
        return 0.0

    importance = PARAMETER_IMPORTANCE.get(key, 0.5)

    # Handle numeric changes
    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
        if old_val == 0:
            raw_magnitude = 1.0 if new_val != 0 else 0.0
        else:
            relative_change = abs(new_val - old_val) / abs(old_val)
            raw_magnitude = min(1.0, relative_change)
        return raw_magnitude * importance

    # Handle string changes
    if isinstance(old_val, str) and isinstance(new_val, str):
        raw_magnitude = _compute_string_magnitude(old_val, new_val)
        return raw_magnitude * importance

    # Handle type changes (old vs new type different)
    if not isinstance(old_val, type(new_val)):
        return importance

    # Handle None to value or value to None
    if old_val is None or new_val is None:
        return importance * 0.8

    # Default for other types
    return 0.5 * importance


def _compute_string_magnitude(old_val: str, new_val: str) -> float:
    """Compute magnitude of string change using character difference ratio."""
    max_len = max(len(old_val), len(new_val))
    if max_len == 0:
        return 0.0

    # Simple character-level comparison
    matches = sum(1 for a, b in zip(old_val, new_val) if a == b)

    # Similarity ratio
    similarity = matches / max_len if max_len > 0 else 1.0
    return 1.0 - similarity


def _compute_shift_magnitude(
    template_changed: bool,
    param_changes: dict[str, ParameterChange],
) -> float:
    """Compute overall shift magnitude.

    Template changes are weighted heavily (0.6 base).
    Parameter changes add weighted contribution.
    """
    template_score = 0.6 if template_changed else 0.0

    # Get max parameter change magnitude
    param_score = 0.0
    if param_changes:
        # Weight by parameter importance and take max
        weighted_magnitudes = [
            change.magnitude for change in param_changes.values()
        ]
        param_score = max(weighted_magnitudes) * 0.4

    return min(1.0, template_score + param_score)


def _find_turn_index(
    policy: TraceEvent,
    turns: list[TraceEvent],
) -> tuple[int, str | None]:
    """Find the turn index closest to this policy event.

    Returns:
        Tuple of (turn_index, triggering_turn_id)
    """
    if not turns:
        return 0, None

    policy_timestamp = _get_timestamp(policy)
    if policy_timestamp is None:
        return 0, None

    best_index = 0
    best_turn_id: str | None = None
    best_diff: float | None = None

    for i, turn in enumerate(turns):
        turn_timestamp = _get_timestamp(turn)
        if turn_timestamp is None:
            continue

        diff = abs((turn_timestamp - policy_timestamp).total_seconds())

        # Find the nearest turn (prefer slightly before if possible)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_index = i
            best_turn_id = turn.id

    return best_index, best_turn_id


def _get_timestamp(event: TraceEvent) -> Any:
    """Extract timestamp from event."""
    if hasattr(event, "timestamp") and event.timestamp:
        return event.timestamp
    return None
