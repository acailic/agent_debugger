"""Shared Pydantic models for the FastAPI application."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionListResponse(BaseModel):
    sessions: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseModel):
    session: dict[str, Any]


class SessionUpdateRequest(BaseModel):
    agent_name: str | None = None
    framework: str | None = None
    ended_at: datetime | None = None
    status: str | None = None
    total_tokens: int | None = None
    total_cost_usd: float | None = None
    tool_calls: int | None = None
    llm_calls: int | None = None
    errors: int | None = None
    replay_value: float | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None


class TraceListResponse(BaseModel):
    traces: list[dict[str, Any]]
    session_id: str


class DecisionTreeResponse(BaseModel):
    session_id: str
    events: list[dict[str, Any]]


class CheckpointListResponse(BaseModel):
    checkpoints: list[dict[str, Any]]
    session_id: str


class DeleteResponse(BaseModel):
    deleted: bool
    session_id: str


class TraceBundleResponse(BaseModel):
    session: dict[str, Any]
    events: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    tree: dict[str, Any] | None
    analysis: dict[str, Any]


class ReplayResponse(BaseModel):
    session_id: str
    mode: str
    focus_event_id: str | None
    start_index: int
    events: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    nearest_checkpoint: dict[str, Any] | None
    breakpoints: list[dict[str, Any]]
    failure_event_ids: list[str]


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
    results: list[dict[str, Any]]


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
