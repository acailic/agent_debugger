"""Data access layer for sessions, events, and checkpoints.

This module provides the TraceRepository class with async methods for CRUD operations
on session management, event queries, checkpoint management, and search functionality.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint
from agent_debugger_sdk.core.events import AgentTurnEvent
from agent_debugger_sdk.core.events import BehaviorAlertEvent
from agent_debugger_sdk.core.events import DecisionEvent
from agent_debugger_sdk.core.events import ErrorEvent
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import LLMRequestEvent
from agent_debugger_sdk.core.events import LLMResponseEvent
from agent_debugger_sdk.core.events import PolicyViolationEvent
from agent_debugger_sdk.core.events import PromptPolicyEvent
from agent_debugger_sdk.core.events import RefusalEvent
from agent_debugger_sdk.core.events import SafetyCheckEvent
from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events import ToolCallEvent
from agent_debugger_sdk.core.events import ToolResultEvent
from agent_debugger_sdk.core.events import TraceEvent
from sqlalchemy import JSON
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class SessionModel(Base):
    """SQLAlchemy ORM model for Session dataclass."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(255))
    framework: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    total_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_calls: Mapped[int] = mapped_column(default=0)
    llm_calls: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    events: Mapped[list[EventModel]] = relationship(back_populates="session", cascade="all, delete-orphan")
    checkpoints: Mapped[list[CheckpointModel]] = relationship(back_populates="session", cascade="all, delete-orphan")


class EventModel(Base):
    """SQLAlchemy ORM model for TraceEvent dataclass."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)
    name: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    importance: Mapped[float] = mapped_column(Float, default=0.5)

    session: Mapped[SessionModel] = relationship(back_populates="events")


class CheckpointModel(Base):
    """SQLAlchemy ORM model for Checkpoint dataclass."""

    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"))
    sequence: Mapped[int] = mapped_column(default=0)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    importance: Mapped[float] = mapped_column(Float, default=0.5)

    session: Mapped[SessionModel] = relationship(back_populates="checkpoints")
    event: Mapped[EventModel | None] = relationship()


class TraceRepository:
    """Data access layer for sessions, events, and checkpoints.

    Provides async methods for CRUD operations using SQLAlchemy async session.
    """

    def __init__(self, session: AsyncSession):
        """Initialize the repository with an async session.

        Args:
            session: SQLAlchemy AsyncSession instance
        """
        self.session = session

    async def create_session(self, session: Session) -> Session:
        """Create a new session record.

        Args:
            session: Session dataclass instance to persist

        Returns:
            The created Session instance
        """
        db_session = SessionModel(
            id=session.id,
            agent_name=session.agent_name,
            framework=session.framework,
            started_at=session.started_at,
            ended_at=session.ended_at,
            status=session.status,
            total_tokens=session.total_tokens,
            total_cost_usd=session.total_cost_usd,
            tool_calls=session.tool_calls,
            llm_calls=session.llm_calls,
            errors=session.errors,
            config=session.config,
            tags=session.tags,
        )
        self.session.add(db_session)
        await self.session.commit()
        return self._orm_to_session(db_session)

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            Session if found, None otherwise
        """
        result = await self.session.execute(select(SessionModel).where(SessionModel.id == session_id))
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return None
        return self._orm_to_session(db_session)

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[Session]:
        """List sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of Session instances
        """
        result = await self.session.execute(
            select(SessionModel).order_by(SessionModel.started_at.desc()).offset(offset).limit(limit)
        )
        return [self._orm_to_session(db) for db in result.scalars()]

    async def count_sessions(self) -> int:
        """Count total number of sessions.

        Returns:
            Total count of sessions in the database
        """
        result = await self.session.execute(select(func.count()).select_from(SessionModel))
        return result.scalar_one()

    async def update_session(self, session_id: str, **updates: Any) -> Session | None:
        """Update a session with the given field values.

        Args:
            session_id: Unique identifier of the session
            **updates: Field names and values to update

        Returns:
            Updated Session if found, None otherwise
        """
        valid_fields = {
            "agent_name",
            "framework",
            "ended_at",
            "status",
            "total_tokens",
            "total_cost_usd",
            "tool_calls",
            "llm_calls",
            "errors",
            "config",
            "tags",
        }
        filtered_updates = {k: v for k, v in updates.items() if k in valid_fields}
        if not filtered_updates:
            return await self.get_session(session_id)

        result = await self.session.execute(select(SessionModel).where(SessionModel.id == session_id))
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return None

        for field, value in filtered_updates.items():
            setattr(db_session, field, value)
        await self.session.commit()
        return self._orm_to_session(db_session)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: Unique identifier of the session

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(select(SessionModel).where(SessionModel.id == session_id))
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return False

        await self.session.delete(db_session)
        await self.session.commit()
        return True

    async def add_event(self, event: TraceEvent) -> TraceEvent:
        """Add a new event to the database.

        Args:
            event: TraceEvent instance to persist

        Returns:
            The created TraceEvent instance
        """
        db_event = self._event_to_orm(event)
        self.session.add(db_event)
        await self.session.commit()
        return self._orm_to_event(db_event)

    async def add_events_batch(self, events: list[TraceEvent]) -> list[TraceEvent]:
        """Add multiple events to the database in a single transaction.

        Args:
            events: List of TraceEvent instances to persist

        Returns:
            List of created TraceEvent instances
        """
        db_events = [self._event_to_orm(event) for event in events]
        self.session.add_all(db_events)
        await self.session.commit()
        return [self._orm_to_event(db) for db in db_events]

    async def get_event(self, event_id: str) -> TraceEvent | None:
        """Retrieve an event by ID.

        Args:
            event_id: Unique identifier of the event

        Returns:
            TraceEvent if found, None otherwise
        """
        result = await self.session.execute(select(EventModel).where(EventModel.id == event_id))
        db_event = result.scalar_one_or_none()
        if db_event is None:
            return None
        return self._orm_to_event(db_event)

    async def list_events(self, session_id: str, limit: int = 100) -> list[TraceEvent]:
        """List events for a session with pagination.

        Args:
            session_id: Session ID to filter events by
            limit: Maximum number of events to return

        Returns:
            List of TraceEvent instances
        """
        result = await self.session.execute(
            select(EventModel).where(EventModel.session_id == session_id).order_by(EventModel.timestamp).limit(limit)
        )
        return [self._orm_to_event(db) for db in result.scalars()]

    async def get_event_tree(self, session_id: str) -> list[TraceEvent]:
        """Get all events for a session in hierarchical order.

        Events are returned in timestamp order for tree reconstruction.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent instances ordered by timestamp
        """
        result = await self.session.execute(
            select(EventModel).where(EventModel.session_id == session_id).order_by(EventModel.timestamp)
        )
        return [self._orm_to_event(db) for db in result.scalars()]

    async def create_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Create a new checkpoint record.

        Args:
            checkpoint: Checkpoint dataclass instance to persist

        Returns:
            The created Checkpoint instance
        """
        db_checkpoint = CheckpointModel(
            id=checkpoint.id,
            session_id=checkpoint.session_id,
            event_id=checkpoint.event_id,
            sequence=checkpoint.sequence,
            state=checkpoint.state,
            memory=checkpoint.memory,
            timestamp=checkpoint.timestamp,
            importance=checkpoint.importance,
        )
        self.session.add(db_checkpoint)
        await self.session.commit()
        await self.session.refresh(db_checkpoint)
        return self._orm_to_checkpoint(db_checkpoint)

    async def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Retrieve a checkpoint by ID.

        Args:
            checkpoint_id: Unique identifier of the checkpoint

        Returns:
            Checkpoint if found, None otherwise
        """
        result = await self.session.execute(
            select(CheckpointModel)
            .options(selectinload(CheckpointModel.event))
            .where(CheckpointModel.id == checkpoint_id)
        )
        db_checkpoint = result.scalar_one_or_none()
        if db_checkpoint is None:
            return None
        return self._orm_to_checkpoint(db_checkpoint)

    async def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """List all checkpoints for a session.

        Args:
            session_id: Session ID to filter checkpoints by

        Returns:
            List of Checkpoint instances ordered by timestamp
        """
        result = await self.session.execute(
            select(CheckpointModel)
            .options(selectinload(CheckpointModel.event))
            .where(CheckpointModel.session_id == session_id)
            .order_by(CheckpointModel.timestamp)
        )
        return [self._orm_to_checkpoint(db) for db in result.scalars()]

    async def get_high_importance_checkpoints(self, session_id: str, limit: int = 10) -> list[Checkpoint]:
        """Get checkpoints with high importance scores.

        Args:
            session_id: Session ID to filter checkpoints by
            limit: Maximum number of checkpoints to return

        Returns:
            List of high-importance Checkpoint instances
        """
        result = await self.session.execute(
            select(CheckpointModel)
            .options(selectinload(CheckpointModel.event))
            .where(CheckpointModel.session_id == session_id)
            .where(CheckpointModel.importance >= 0.8)
            .order_by(CheckpointModel.importance.desc())
            .limit(limit)
        )
        return [self._orm_to_checkpoint(db) for db in result.scalars()]

    async def search_events(
        self,
        query: str,
        session_id: str | None = None,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[TraceEvent]:
        """Search events by name or data content.

        Args:
            query: Search string to match against event name
            session_id: Optional session ID to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching TraceEvent instances
        """
        search_term = f"%{query}%"
        stmt = (
            select(EventModel)
            .where(
                or_(
                    EventModel.name.ilike(search_term),
                    EventModel.event_type.ilike(search_term),
                    cast(EventModel.data, String).ilike(search_term),
                    cast(EventModel.event_metadata, String).ilike(search_term),
                )
            )
            .order_by(EventModel.timestamp.desc())
            .limit(limit)
        )

        if session_id:
            stmt = stmt.where(EventModel.session_id == session_id)
        if event_type:
            stmt = stmt.where(EventModel.event_type == event_type)

        result = await self.session.execute(stmt)
        return [self._orm_to_event(db) for db in result.scalars()]

    def _event_to_orm(self, event: TraceEvent) -> EventModel:
        """Convert a TraceEvent dataclass to an EventModel ORM instance.

        Args:
            event: TraceEvent instance to convert

        Returns:
            EventModel instance
        """
        data = dict(event.data)
        if isinstance(event, ToolCallEvent):
            data["tool_name"] = event.tool_name
            data["arguments"] = event.arguments
        elif isinstance(event, ToolResultEvent):
            data["tool_name"] = event.tool_name
            data["result"] = event.result
            data["error"] = event.error
            data["duration_ms"] = event.duration_ms
        elif isinstance(event, LLMRequestEvent):
            data["model"] = event.model
            data["messages"] = event.messages
            data["tools"] = event.tools
            data["settings"] = event.settings
        elif isinstance(event, LLMResponseEvent):
            data["model"] = event.model
            data["content"] = event.content
            data["tool_calls"] = event.tool_calls
            data["usage"] = event.usage
            data["cost_usd"] = event.cost_usd
            data["duration_ms"] = event.duration_ms
        elif isinstance(event, DecisionEvent):
            data["reasoning"] = event.reasoning
            data["confidence"] = event.confidence
            data["evidence"] = event.evidence
            data["evidence_event_ids"] = event.evidence_event_ids
            data["alternatives"] = event.alternatives
            data["chosen_action"] = event.chosen_action
        elif isinstance(event, SafetyCheckEvent):
            data["policy_name"] = event.policy_name
            data["outcome"] = event.outcome
            data["risk_level"] = event.risk_level
            data["rationale"] = event.rationale
            data["blocked_action"] = event.blocked_action
            data["evidence"] = event.evidence
        elif isinstance(event, RefusalEvent):
            data["reason"] = event.reason
            data["policy_name"] = event.policy_name
            data["risk_level"] = event.risk_level
            data["blocked_action"] = event.blocked_action
            data["safe_alternative"] = event.safe_alternative
        elif isinstance(event, PolicyViolationEvent):
            data["policy_name"] = event.policy_name
            data["severity"] = event.severity
            data["violation_type"] = event.violation_type
            data["details"] = event.details
        elif isinstance(event, PromptPolicyEvent):
            data["template_id"] = event.template_id
            data["policy_parameters"] = event.policy_parameters
            data["speaker"] = event.speaker
            data["state_summary"] = event.state_summary
            data["goal"] = event.goal
        elif isinstance(event, AgentTurnEvent):
            data["agent_id"] = event.agent_id
            data["speaker"] = event.speaker
            data["turn_index"] = event.turn_index
            data["goal"] = event.goal
            data["content"] = event.content
        elif isinstance(event, BehaviorAlertEvent):
            data["alert_type"] = event.alert_type
            data["severity"] = event.severity
            data["signal"] = event.signal
            data["related_event_ids"] = event.related_event_ids
        elif isinstance(event, ErrorEvent):
            data["error_type"] = event.error_type
            data["error_message"] = event.error_message
            data["stack_trace"] = event.stack_trace

        event_metadata = dict(event.metadata)
        event_metadata["upstream_event_ids"] = list(event.upstream_event_ids)

        return EventModel(
            id=event.id,
            session_id=event.session_id,
            parent_id=event.parent_id,
            event_type=str(event.event_type),
            timestamp=event.timestamp,
            name=event.name,
            data=data,
            event_metadata=event_metadata,
            importance=event.importance,
        )

    def _orm_to_event(self, db_event: EventModel) -> TraceEvent:
        """Convert an EventModel ORM instance to the appropriate TraceEvent subclass.

        Args:
            db_event: EventModel instance to convert

        Returns:
            Appropriate TraceEvent subclass instance
        """
        data = dict(db_event.data)  # Make a copy to avoid modifying original
        event_type = EventType(db_event.event_type) if db_event.event_type else EventType.AGENT_START

        # Fields to strip from data for each event type to avoid duplication
        system_fields_by_type: dict[EventType, list[str]] = {
            EventType.TOOL_CALL: ["tool_name", "arguments"],
            EventType.TOOL_RESULT: ["tool_name", "result", "error", "duration_ms"],
            EventType.LLM_REQUEST: ["model", "messages", "tools", "settings"],
            EventType.LLM_RESPONSE: ["model", "content", "tool_calls", "usage", "cost_usd", "duration_ms"],
            EventType.DECISION: [
                "reasoning",
                "confidence",
                "evidence",
                "evidence_event_ids",
                "alternatives",
                "chosen_action",
            ],
            EventType.SAFETY_CHECK: [
                "policy_name",
                "outcome",
                "risk_level",
                "rationale",
                "blocked_action",
                "evidence",
            ],
            EventType.REFUSAL: [
                "reason",
                "policy_name",
                "risk_level",
                "blocked_action",
                "safe_alternative",
            ],
            EventType.POLICY_VIOLATION: ["policy_name", "severity", "violation_type", "details"],
            EventType.PROMPT_POLICY: ["template_id", "policy_parameters", "speaker", "state_summary", "goal"],
            EventType.AGENT_TURN: ["agent_id", "speaker", "turn_index", "goal", "content"],
            EventType.BEHAVIOR_ALERT: ["alert_type", "severity", "signal", "related_event_ids"],
            EventType.ERROR: ["error_type", "error_message", "stack_trace"],
        }

        # Strip system fields from data to prevent duplication
        cleaned_data = {k: v for k, v in data.items() if k not in system_fields_by_type.get(event_type, [])}

        base_kwargs = {
            "id": db_event.id,
            "session_id": db_event.session_id,
            "parent_id": db_event.parent_id,
            "event_type": event_type,
            "timestamp": db_event.timestamp,
            "name": db_event.name,
            "data": cleaned_data,
            "metadata": db_event.event_metadata,
            "importance": db_event.importance,
            "upstream_event_ids": db_event.event_metadata.get("upstream_event_ids", []),
        }

        if event_type == EventType.TOOL_CALL:
            return ToolCallEvent(
                **base_kwargs,
                tool_name=data.get("tool_name", ""),
                arguments=data.get("arguments", {}),
            )
        if event_type == EventType.TOOL_RESULT:
            return ToolResultEvent(
                **base_kwargs,
                tool_name=data.get("tool_name", ""),
                result=data.get("result"),
                error=data.get("error"),
                duration_ms=data.get("duration_ms", 0.0),
            )
        if event_type == EventType.LLM_REQUEST:
            return LLMRequestEvent(
                **base_kwargs,
                model=data.get("model", ""),
                messages=data.get("messages", []),
                tools=data.get("tools", []),
                settings=data.get("settings", {}),
            )
        if event_type == EventType.LLM_RESPONSE:
            return LLMResponseEvent(
                **base_kwargs,
                model=data.get("model", ""),
                content=data.get("content", ""),
                tool_calls=data.get("tool_calls", []),
                usage=data.get("usage", {"input_tokens": 0, "output_tokens": 0}),
                cost_usd=data.get("cost_usd", 0.0),
                duration_ms=data.get("duration_ms", 0.0),
            )
        if event_type == EventType.DECISION:
            return DecisionEvent(
                **base_kwargs,
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 0.5),
                evidence=data.get("evidence", []),
                evidence_event_ids=data.get("evidence_event_ids", []),
                alternatives=data.get("alternatives", []),
                chosen_action=data.get("chosen_action", ""),
            )
        if event_type == EventType.SAFETY_CHECK:
            return SafetyCheckEvent(
                **base_kwargs,
                policy_name=data.get("policy_name", ""),
                outcome=data.get("outcome", "pass"),
                risk_level=data.get("risk_level", "low"),
                rationale=data.get("rationale", ""),
                blocked_action=data.get("blocked_action"),
                evidence=data.get("evidence", []),
            )
        if event_type == EventType.REFUSAL:
            return RefusalEvent(
                **base_kwargs,
                reason=data.get("reason", ""),
                policy_name=data.get("policy_name", ""),
                risk_level=data.get("risk_level", "medium"),
                blocked_action=data.get("blocked_action"),
                safe_alternative=data.get("safe_alternative"),
            )
        if event_type == EventType.POLICY_VIOLATION:
            return PolicyViolationEvent(
                **base_kwargs,
                policy_name=data.get("policy_name", ""),
                severity=data.get("severity", "medium"),
                violation_type=data.get("violation_type", ""),
                details=data.get("details", {}),
            )
        if event_type == EventType.PROMPT_POLICY:
            return PromptPolicyEvent(
                **base_kwargs,
                template_id=data.get("template_id", ""),
                policy_parameters=data.get("policy_parameters", {}),
                speaker=data.get("speaker", ""),
                state_summary=data.get("state_summary", ""),
                goal=data.get("goal", ""),
            )
        if event_type == EventType.AGENT_TURN:
            return AgentTurnEvent(
                **base_kwargs,
                agent_id=data.get("agent_id", ""),
                speaker=data.get("speaker", ""),
                turn_index=data.get("turn_index", 0),
                goal=data.get("goal", ""),
                content=data.get("content", ""),
            )
        if event_type == EventType.BEHAVIOR_ALERT:
            return BehaviorAlertEvent(
                **base_kwargs,
                alert_type=data.get("alert_type", ""),
                severity=data.get("severity", "medium"),
                signal=data.get("signal", ""),
                related_event_ids=data.get("related_event_ids", []),
            )
        if event_type == EventType.ERROR:
            return ErrorEvent(
                **base_kwargs,
                error_type=data.get("error_type", ""),
                error_message=data.get("error_message", ""),
                stack_trace=data.get("stack_trace"),
            )
        return TraceEvent(**base_kwargs)

    def _orm_to_session(self, db_session: SessionModel) -> Session:
        """Convert a SessionModel ORM instance to a Session dataclass.

        Args:
            db_session: SessionModel instance to convert

        Returns:
            Session dataclass instance
        """
        return Session(
            id=db_session.id,
            agent_name=db_session.agent_name,
            framework=db_session.framework,
            started_at=db_session.started_at,
            ended_at=db_session.ended_at,
            status=db_session.status,
            total_tokens=db_session.total_tokens,
            total_cost_usd=db_session.total_cost_usd,
            tool_calls=db_session.tool_calls,
            llm_calls=db_session.llm_calls,
            errors=db_session.errors,
            config=db_session.config,
            tags=db_session.tags,
        )

    def _orm_to_checkpoint(self, db_checkpoint: CheckpointModel) -> Checkpoint:
        """Convert a CheckpointModel ORM instance to a Checkpoint dataclass.

        Args:
            db_checkpoint: CheckpointModel instance to convert

        Returns:
            Checkpoint dataclass instance
        """
        return Checkpoint(
            id=db_checkpoint.id,
            session_id=db_checkpoint.session_id,
            event_id=db_checkpoint.event_id,
            sequence=db_checkpoint.sequence,
            state=db_checkpoint.state,
            memory=db_checkpoint.memory,
            timestamp=db_checkpoint.timestamp,
            importance=db_checkpoint.importance,
        )
