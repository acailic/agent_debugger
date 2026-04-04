"""SQLAlchemy ORM models for sessions, events, and checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from agent_debugger_sdk.core.events import SessionStatus


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class SessionModel(Base):
    """SQLAlchemy ORM model for Session dataclass."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    agent_name: Mapped[str] = mapped_column(String(255))
    framework: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[SessionStatus] = mapped_column(String(32), default=SessionStatus.RUNNING)
    total_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_calls: Mapped[int] = mapped_column(default=0)
    llm_calls: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    replay_value: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    fix_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Retention and clustering columns for research features
    retention_tier: Mapped[str] = mapped_column(String(16), default="downsampled", index=True)
    failure_fingerprint_primary: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    cluster_representative: Mapped[bool] = mapped_column(default=False, index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    events: Mapped[list[EventModel]] = relationship(back_populates="session", cascade="all, delete-orphan")
    checkpoints: Mapped[list[CheckpointModel]] = relationship(back_populates="session", cascade="all, delete-orphan")


class EventModel(Base):
    """SQLAlchemy ORM model for TraceEvent dataclass."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    name: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    importance: Mapped[float] = mapped_column(Float, default=0.5)

    session: Mapped[SessionModel] = relationship(back_populates="events")

    __table_args__ = (Index("ix_events_tenant_session", "tenant_id", "session_id"),)


class CheckpointModel(Base):
    """SQLAlchemy ORM model for Checkpoint dataclass."""

    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"))
    sequence: Mapped[int] = mapped_column(default=0)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    importance: Mapped[float] = mapped_column(Float, default=0.5)

    session: Mapped[SessionModel] = relationship(back_populates="checkpoints")
    event: Mapped[EventModel | None] = relationship()


class AnomalyAlertModel(Base):
    """SQLAlchemy ORM model for anomaly alerts."""

    __tablename__ = "anomaly_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[float] = mapped_column(Float)
    signal: Mapped[str] = mapped_column(Text)
    event_ids: Mapped[list] = mapped_column(JSON)
    detection_source: Mapped[str] = mapped_column(String(32))
    detection_config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    # Lifecycle fields
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FailureClusterModel(Base):
    """SQLAlchemy ORM model for failure clusters."""

    __tablename__ = "failure_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    first_seen: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    session_count: Mapped[int] = mapped_column(default=1)
    event_count: Mapped[int] = mapped_column(default=0)
    representative_session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)
    representative_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sample_failure_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_symptom: Mapped[str | None] = mapped_column(String(512), nullable=True)
    avg_severity: Mapped[float] = mapped_column(Float, default=0.0)


class PatternModel(Base):
    """SQLAlchemy ORM model for detected patterns across sessions."""

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    pattern_type: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )  # error_trend, tool_failure, confidence_drop, new_failure_mode
    agent_name: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # warning, critical
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, resolved, dismissed
    detected_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    description: Mapped[str] = mapped_column(Text)
    affected_sessions: Mapped[list[str]] = mapped_column(JSON, default=list)  # List of session IDs
    session_count: Mapped[int] = mapped_column(default=0)
    pattern_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Pattern-specific data
    # Pattern trend fields
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Resolution tracking
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_patterns_tenant_type", "tenant_id", "pattern_type"),
        Index("ix_patterns_tenant_agent", "tenant_id", "agent_name"),
        Index("ix_patterns_tenant_severity", "tenant_id", "severity"),
        Index("ix_patterns_tenant_status", "tenant_id", "status"),
    )


class AlertPolicyModel(Base):
    """SQLAlchemy ORM model for configurable alert policies."""

    __tablename__ = "alert_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # null = global policy
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    severity_threshold: Mapped[str | None] = mapped_column(String(16), nullable=True)  # warning, critical, etc.
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_alert_policies_tenant_agent", "tenant_id", "agent_name"),
        Index("ix_alert_policies_tenant_type", "tenant_id", "alert_type"),
        Index("ix_alert_policies_tenant_agent_type", "tenant_id", "agent_name", "alert_type"),
    )
