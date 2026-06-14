"""Alert, anomaly, policy, and fix-note Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    status: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    resolution_note: str | None = None


class AnomalyAlertListResponse(BaseModel):
    """Response schema for listing anomaly alerts."""

    session_id: str
    alerts: list[AnomalyAlertSchema]
    total: int


# ------------------------------------------------------------------
# Alert Lifecycle Schemas
# ------------------------------------------------------------------


class AlertStatusUpdate(BaseModel):
    """Request schema for updating a single alert's status."""

    status: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=2000)


class AlertBulkUpdate(BaseModel):
    """Request schema for bulk updating alert statuses."""

    alert_ids: list[str] = Field(min_length=1)
    status: str = Field(min_length=1, max_length=32)


class AlertFilters(BaseModel):
    """Query parameters for filtering alerts."""

    agent_name: str | None = None
    severity: float | None = Field(default=None, ge=0.0, le=1.0)
    alert_type: str | None = None
    status: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)


class AlertSeverityCount(BaseModel):
    """Count of alerts by severity level."""

    critical: int
    high: int
    medium: int
    low: int


class AlertSummarySchema(BaseModel):
    """Alert summary statistics."""

    by_status: dict[str, int]
    by_type: dict[str, int]
    by_severity: AlertSeverityCount
    total: int


class AlertTrendingPointSchema(BaseModel):
    """Single data point for alert trending."""

    date: str
    count: int


class AlertTrendingSchema(BaseModel):
    """Alert volume over time."""

    trending: list[AlertTrendingPointSchema]
    days: int


class AlertListFilteredResponse(BaseModel):
    """Response schema for filtered alert listing."""

    alerts: list[AnomalyAlertSchema]
    total: int
    filters: AlertFilters


class FixNoteRequest(BaseModel):
    """Request schema for adding/updating a fix note."""

    note: str = Field(min_length=1, max_length=2000)


class FixNoteResponse(BaseModel):
    """Response schema for fix note operations."""

    session_id: str
    fix_note: str


# ------------------------------------------------------------------
# Alert policy schemas
# ------------------------------------------------------------------


class AlertPolicyCreate(BaseModel):
    """Request schema for creating an alert policy."""

    agent_name: str | None = Field(default=None, max_length=255)
    alert_type: str = Field(min_length=1, max_length=64)
    threshold_value: float = Field(ge=0.0)
    severity_threshold: str | None = Field(default=None, max_length=16)
    enabled: bool = Field(default=True)


class AlertPolicyUpdate(BaseModel):
    """Request schema for updating an alert policy."""

    agent_name: str | None = Field(default=None, max_length=255)
    alert_type: str | None = Field(default=None, min_length=1, max_length=64)
    threshold_value: float | None = Field(default=None, ge=0.0)
    severity_threshold: str | None = Field(default=None, max_length=16)
    enabled: bool | None = None


class AlertPolicySchema(BaseModel):
    """Response schema for alert policies."""

    id: str
    agent_name: str | None
    alert_type: str
    threshold_value: float
    severity_threshold: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AlertPolicyListResponse(BaseModel):
    """Response schema for listing alert policies."""

    policies: list[AlertPolicySchema]
    total: int
