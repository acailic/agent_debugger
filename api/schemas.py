"""Shared Pydantic models for the FastAPI application."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_debugger_sdk.core.events import EventType, RiskLevel, SafetyOutcome, SessionStatus


class SessionSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    agent_name: str
    framework: str
    started_at: datetime
    ended_at: datetime | None
    status: SessionStatus
    total_tokens: int
    total_cost_usd: float
    tool_calls: int
    llm_calls: int
    errors: int
    replay_value: float
    config: dict[str, Any]
    tags: list[str]
    fix_note: str | None = None
    retention_tier: str | None = None
    failure_count: int | None = None
    behavior_alert_count: int | None = None
    representative_event_id: str | None = None


class TraceEventSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    session_id: str
    parent_id: str | None
    event_type: EventType
    timestamp: datetime
    name: str
    data: dict[str, Any]
    metadata: dict[str, Any]
    importance: float
    upstream_event_ids: list[str]
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None
    model: str | None = None
    messages: list[dict[str, Any]] | None = None
    tools: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    cost_usd: float | None = None
    reasoning: str | None = None
    confidence: float | None = None
    evidence: list[dict[str, Any]] | None = None
    evidence_event_ids: list[str] | None = None
    alternatives: list[dict[str, Any]] | None = None
    chosen_action: str | None = None
    policy_name: str | None = None
    outcome: SafetyOutcome | None = None
    risk_level: RiskLevel | None = None
    rationale: str | None = None
    blocked_action: str | None = None
    reason: str | None = None
    safe_alternative: str | None = None
    severity: RiskLevel | None = None
    violation_type: str | None = None
    details: dict[str, Any] | None = None
    template_id: str | None = None
    policy_parameters: dict[str, Any] | None = None
    speaker: str | None = None
    state_summary: str | None = None
    goal: str | None = None
    agent_id: str | None = None
    turn_index: int | None = None
    alert_type: str | None = None
    signal: str | None = None
    related_event_ids: list[str] | None = None
    error_type: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None


class CheckpointSchema(BaseModel):
    id: str
    session_id: str
    event_id: str
    sequence: int
    state: dict[str, Any]
    memory: dict[str, Any]
    timestamp: datetime
    importance: float


class SessionListResponse(BaseModel):
    sessions: list[SessionSchema]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseModel):
    session: SessionSchema


class SessionUpdateRequest(BaseModel):
    agent_name: str | None = None
    framework: str | None = None
    ended_at: datetime | None = None
    status: SessionStatus | None = None
    total_tokens: int | None = None
    total_cost_usd: float | None = None
    tool_calls: int | None = None
    llm_calls: int | None = None
    errors: int | None = None
    replay_value: float | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None
    fix_note: str | None = None


class TraceListResponse(BaseModel):
    traces: list[TraceEventSchema]
    session_id: str


class DecisionTreeResponse(BaseModel):
    session_id: str
    events: list[TraceEventSchema]


class CheckpointListResponse(BaseModel):
    checkpoints: list[CheckpointSchema]
    session_id: str


class CheckpointDeltaSchema(BaseModel):
    checkpoint_id: str
    previous_checkpoint_id: str | None
    state_delta: dict[str, Any]
    memory_delta: dict[str, Any]


class CheckpointDeltasResponse(BaseModel):
    deltas: list[CheckpointDeltaSchema]
    session_id: str


class RestoreRequest(BaseModel):
    session_id: str | None = None
    label: str = ""


class RestoreResponse(BaseModel):
    checkpoint_id: str
    original_session_id: str
    new_session_id: str
    restored_at: str
    state: dict[str, Any]
    restore_token: str


class DeleteResponse(BaseModel):
    deleted: bool
    session_id: str


class TraceBundleResponse(BaseModel):
    session: SessionSchema
    events: list[TraceEventSchema]
    checkpoints: list[CheckpointSchema]
    tree: dict[str, Any] | None
    analysis: dict[str, Any]


class ReplayResponse(BaseModel):
    session_id: str
    mode: str
    focus_event_id: str | None
    start_index: int
    events: list[TraceEventSchema]
    checkpoints: list[CheckpointSchema]
    nearest_checkpoint: CheckpointSchema | None
    breakpoints: list[TraceEventSchema]
    failure_event_ids: list[str]
    collapsed_segments: list[CollapsedSegmentSchema] = []
    highlight_indices: list[int] = []
    stopped_at_breakpoint: bool = False
    stopped_at_index: int | None = None


class AnalysisResponse(BaseModel):
    session_id: str
    analysis: dict[str, Any]


class LiveSummaryResponse(BaseModel):
    session_id: str
    live_summary: dict[str, Any]


class TraceSearchResponse(BaseModel):
    query: str
    session_id: str | None
    event_type: str | None
    total: int
    results: list[TraceEventSchema]


class CreateKeyRequest(BaseModel):
    name: str = ""
    environment: str = "live"


class CreateKeyResponse(BaseModel):
    id: str
    key: str
    key_prefix: str
    name: str
    environment: str


class KeyListItem(BaseModel):
    id: str
    key_prefix: str
    name: str
    environment: str
    created_at: str
    last_used_at: str | None


class HighlightSchema(BaseModel):
    event_id: str
    event_type: str
    highlight_type: str
    importance: float
    reason: str
    timestamp: str
    headline: str


class CollapsedSegmentSchema(BaseModel):
    start_index: int
    end_index: int
    event_count: int
    summary: str
    event_types: list[str] = []
    total_duration_ms: float | None = None


class AnomalyAlertSchema(BaseModel):
    """Schema for anomaly alerts persisted from live monitoring."""

    id: str
    session_id: str
    alert_type: str
    severity: float
    signal: str
    event_ids: list[str]
    detection_source: str
    detection_config: dict[str, Any]
    created_at: datetime


class AnomalyAlertListResponse(BaseModel):
    """Response schema for listing anomaly alerts."""

    session_id: str
    alerts: list[AnomalyAlertSchema]
    total: int


class FixNoteRequest(BaseModel):
    """Request schema for adding/updating a fix note."""

    note: str = Field(min_length=1, max_length=2000)


class FixNoteResponse(BaseModel):
    """Response schema for fix note operations."""

    session_id: str
    fix_note: str
