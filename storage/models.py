"""SQLAlchemy ORM models for sessions, events, and checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    status: Mapped[str] = mapped_column(String(32), default="running")
    total_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_calls: Mapped[int] = mapped_column(default=0)
    llm_calls: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    replay_value: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

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

    __table_args__ = (
        Index("ix_events_tenant_session", "tenant_id", "session_id"),
    )


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
