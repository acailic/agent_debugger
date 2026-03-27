"""Data models for collector module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class RollingWindow:
    """Rolling window metrics for real-time monitoring."""

    window_start: datetime
    window_end: datetime
    event_count: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    decisions: int = 0
    errors: int = 0
    refusals: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    unique_tools: set[str] = field(default_factory=set)
    unique_agents: set[str] = field(default_factory=set)
    avg_confidence: float = 0.0
    state_progression: list[str] = field(default_factory=list)


@dataclass
class RollingSummary:
    """Human-readable rolling summary with structured metrics."""

    text: str
    metrics: dict[str, Any]
    window_type: Literal["time", "event_count"]
    window_size: int  # seconds or event count
    computed_at: datetime


@dataclass
class OscillationAlert:
    """Alert for detected oscillation patterns in agent behavior."""

    pattern: str  # e.g., "A->B->A->B"
    event_type: str
    repeat_count: int
    severity: float
    event_ids: list[str] = field(default_factory=list)


@dataclass
class CheckpointDelta:
    """Delta information between checkpoints."""

    checkpoint_id: str
    event_id: str
    sequence: int
    time_since_previous: float  # seconds
    events_since_previous: int
    importance_delta: float
    restore_value: float
    state_keys_changed: list[str] = field(default_factory=list)
