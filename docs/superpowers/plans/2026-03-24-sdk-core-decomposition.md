# SDK Core File Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose three large SDK core files (events.py, context.py, decorators.py) into domain-focused packages while preserving backward compatibility via `__init__.py` re-exports

**Architecture:** Convert single files to packages with domain-focused modules. events.py → events/ (11 modules), context.py → context/ (3 modules), decorators.py → decorators/ (4 modules including shared utils). All existing imports continue to work unchanged.

**Tech Stack:** Python 3.10+, dataclasses, contextvars, TYPE_CHECKING for circular import avoidance

---

## File Structure Overview

```
agent_debugger_sdk/core/
├── events/
│   ├── __init__.py          # Re-exports everything
│   ├── base.py              # Enums, TraceEvent, serialization helpers
│   ├── tools.py             # ToolCallEvent, ToolResultEvent
│   ├── llm.py               # LLMRequestEvent, LLMResponseEvent
│   ├── decisions.py         # DecisionEvent
│   ├── safety.py            # Safety-related events
│   ├── agent.py             # AgentTurnEvent, BehaviorAlertEvent
│   ├── errors.py            # ErrorEvent
│   ├── session.py           # Session dataclass
│   ├── checkpoint.py        # Checkpoint dataclass
│   └── registry.py          # EVENT_TYPE_REGISTRY
├── context/
│   ├── __init__.py          # Re-exports everything
│   ├── vars.py              # ContextVar declarations
│   ├── pipeline.py          # configure_event_pipeline
│   └── trace_context.py     # TraceContext class
└── decorators/
    ├── __init__.py          # Re-exports everything
    ├── _utils.py            # Shared helper functions
    ├── agent.py             # trace_agent decorator
    ├── tool.py              # trace_tool decorator
    └── llm.py               # trace_llm decorator
```

---

## Task 1: Create events/base.py
**Files:**
- Create: `agent_debugger_sdk/core/events/base.py`

- [ ] **Step 1: Create events/ directory**
```bash
mkdir -p agent_debugger_sdk/core/events
```

- [ ] **Step 2: Create events/base.py with complete content**

Extract from `agent_debugger_sdk/core/events.py`:
- StrEnum compatibility shim
- EventType, SessionStatus, RiskLevel, SafetyOutcome enums
- BASE_EVENT_FIELDS constant
- _serialize_field_value function
- TraceEvent class with all methods

```python
# events/base.py
"""Base event types and serialization for agent tracing."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_debugger_sdk.pricing import calculate_cost

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:

    class StrEnum(str, Enum):
        """Compatibility shim for StrEnum in Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


class EventType(StrEnum):
    """Enumeration of all trace event types."""

    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    DECISION = "decision"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    SAFETY_CHECK = "safety_check"
    REFUSAL = "refusal"
    POLICY_VIOLATION = "policy_violation"
    PROMPT_POLICY = "prompt_policy"
    AGENT_TURN = "agent_turn"
    BEHAVIOR_ALERT = "behavior_alert"


class SessionStatus(StrEnum):
    """Session lifecycle status values."""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class RiskLevel(StrEnum):
    """Shared risk/severity labels across domain events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyOutcome(StrEnum):
    """Explicit outcome labels for safety checks."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    BLOCK = "block"


BASE_EVENT_FIELDS = {
    "id",
    "session_id",
    "parent_id",
    "event_type",
    "timestamp",
    "name",
    "data",
    "metadata",
    "importance",
    "upstream_event_ids",
}


def _serialize_field_value(value: Any) -> Any:
    """Convert dataclass field values into JSON-serializable payloads."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value)
    if isinstance(value, list):
        return [_serialize_field_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_field_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _serialize_field_value(item)
            for key, item in value.items()
        }
    return value


@dataclass(kw_only=True)
class TraceEvent:
    """Base dataclass for all trace events."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    parent_id: str | None = None
    event_type: EventType = EventType.AGENT_START
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    upstream_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a dictionary."""
        return {
            field_info.name: _serialize_field_value(getattr(self, field_info.name))
            for field_info in fields(self)
        }

    @classmethod
    def _typed_field_names(cls) -> set[str]:
        """Return event-specific dataclass fields beyond the shared base payload."""
        return {
            field_info.name
            for field_info in fields(cls)
            if field_info.name not in BASE_EVENT_FIELDS
        }

    def to_storage_data(self) -> dict[str, Any]:
        """Merge event-specific fields into the storage payload."""
        payload = dict(self.data)
        for field_name in self._typed_field_names():
            payload[field_name] = getattr(self, field_name)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceEvent:
        """Deserialize a dictionary to a TraceEvent."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if isinstance(data.get("event_type"), str):
            data["event_type"] = EventType(data["event_type"])
        return cls(**data)

    @classmethod
    def from_data(
        cls,
        event_type: EventType,
        base_kwargs: dict[str, Any],
        data: dict[str, Any],
    ) -> TraceEvent:
        """Build the typed event instance for the given event_type."""
        # Import locally to avoid circular import
        from .registry import EVENT_TYPE_REGISTRY
        event_cls = EVENT_TYPE_REGISTRY.get(event_type, cls)
        typed_field_names = event_cls._typed_field_names()
        typed_kwargs = {
            field_name: data[field_name]
            for field_name in typed_field_names
            if field_name in data
        }
        payload = {
            key: value
            for key, value in data.items()
            if key not in typed_field_names
        }
        return event_cls(
            **base_kwargs,
            event_type=event_type,
            data=payload,
            **typed_kwargs,
        )
```

- [ ] **Step 3: Verify base.py imports work**
```bash
python3 -c "from agent_debugger_sdk.core.events.base import EventType, TraceEvent, _serialize_field_value; print('base.py OK')"
```
Expected: "base.py OK"

- [ ] **Step 4: Commit**
```bash
git add agent_debugger_sdk/core/events/base.py
git commit -m "refactor(events): create base.py with enums and TraceEvent

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Create events domain files
**Files:**
- Create: `agent_debugger_sdk/core/events/tools.py`
- Create: `agent_debugger_sdk/core/events/llm.py`
- Create: `agent_debugger_sdk/core/events/decisions.py`
- Create: `agent_debugger_sdk/core/events/safety.py`
- Create: `agent_debugger_sdk/core/events/agent.py`
- Create: `agent_debugger_sdk/core/events/errors.py`

- [ ] **Step 1: Create events/tools.py**
```python
# events/tools.py
"""Tool call and result events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, TraceEvent


@dataclass(kw_only=True)
class ToolCallEvent(TraceEvent):
    """Event representing a tool/function call by the agent."""

    event_type: EventType = EventType.TOOL_CALL
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class ToolResultEvent(TraceEvent):
    """Event representing the result of a tool call."""

    event_type: EventType = EventType.TOOL_RESULT
    tool_name: str = ""
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
```

- [ ] **Step 2: Create events/llm.py**
```python
# events/llm.py
"""LLM request and response events."""

from dataclasses import dataclass, field
from typing import Any

from agent_debugger_sdk.pricing import calculate_cost

from .base import EventType, TraceEvent


@dataclass(kw_only=True)
class LLMRequestEvent(TraceEvent):
    """Event representing an LLM API request."""

    event_type: EventType = EventType.LLM_REQUEST
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class LLMResponseEvent(TraceEvent):
    """Event representing an LLM API response."""

    event_type: EventType = EventType.LLM_RESPONSE
    model: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    cost_usd: float = 0.0
    duration_ms: float = 0.0

    def __post_init__(self):
        """Auto-calculate cost if not explicitly set and tokens available."""
        if self.cost_usd == 0.0:
            input_tokens = self.usage.get("input_tokens", 0)
            output_tokens = self.usage.get("output_tokens", 0)
            if input_tokens or output_tokens:
                calculated = calculate_cost(self.model, input_tokens, output_tokens)
                if calculated is not None:
                    object.__setattr__(self, "cost_usd", calculated)
```

- [ ] **Step 3: Create events/decisions.py**
```python
# events/decisions.py
"""Decision event for agent reasoning."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, TraceEvent


@dataclass(kw_only=True)
class DecisionEvent(TraceEvent):
    """Event representing an agent decision point."""

    event_type: EventType = EventType.DECISION
    reasoning: str = ""
    confidence: float = 0.5
    evidence: list[dict[str, Any]] = field(default_factory=list)
    evidence_event_ids: list[str] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    chosen_action: str = ""
```

- [ ] **Step 4: Create events/safety.py**
```python
# events/safety.py
"""Safety-related events for policy and guardrails."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, RiskLevel, SafetyOutcome, TraceEvent


@dataclass(kw_only=True)
class SafetyCheckEvent(TraceEvent):
    """Event representing an explicit guard or safety evaluation."""

    event_type: EventType = EventType.SAFETY_CHECK
    policy_name: str = ""
    outcome: SafetyOutcome = SafetyOutcome.PASS
    risk_level: RiskLevel = RiskLevel.LOW
    rationale: str = ""
    blocked_action: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.outcome = SafetyOutcome(self.outcome)
        self.risk_level = RiskLevel(self.risk_level)


@dataclass(kw_only=True)
class RefusalEvent(TraceEvent):
    """Event representing an intentional refusal."""

    event_type: EventType = EventType.REFUSAL
    reason: str = ""
    policy_name: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    blocked_action: str | None = None
    safe_alternative: str | None = None

    def __post_init__(self) -> None:
        self.risk_level = RiskLevel(self.risk_level)


@dataclass(kw_only=True)
class PolicyViolationEvent(TraceEvent):
    """Event representing a policy violation or prompt injection signal."""

    event_type: EventType = EventType.POLICY_VIOLATION
    policy_name: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM
    violation_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.severity = RiskLevel(self.severity)


@dataclass(kw_only=True)
class PromptPolicyEvent(TraceEvent):
    """Event describing prompt policy or prompt-as-action state."""

    event_type: EventType = EventType.PROMPT_POLICY
    template_id: str = ""
    policy_parameters: dict[str, Any] = field(default_factory=dict)
    speaker: str = ""
    state_summary: str = ""
    goal: str = ""
```

- [ ] **Step 5: Create events/agent.py**
```python
# events/agent.py
"""Agent turn and behavior events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, RiskLevel, TraceEvent


@dataclass(kw_only=True)
class AgentTurnEvent(TraceEvent):
    """Event representing a single turn in a multi-agent session."""

    event_type: EventType = EventType.AGENT_TURN
    agent_id: str = ""
    speaker: str = ""
    turn_index: int = 0
    goal: str = ""
    content: str = ""


@dataclass(kw_only=True)
class BehaviorAlertEvent(TraceEvent):
    """Event representing detected suspicious or unstable behavior."""

    event_type: EventType = EventType.BEHAVIOR_ALERT
    alert_type: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM
    signal: str = ""
    related_event_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.severity = RiskLevel(self.severity)
```

- [ ] **Step 6: Create events/errors.py**
```python
# events/errors.py
"""Error event for exception capture."""

from .base import EventType, TraceEvent


class ErrorEvent(TraceEvent):
    """Event representing an error during agent execution."""

    event_type: EventType = EventType.ERROR
    error_type: str = ""
    error_message: str = ""
    stack_trace: str | None = None
```

- [ ] **Step 7: Verify domain files import correctly**
```bash
python3 -c "
from agent_debugger_sdk.core.events.tools import ToolCallEvent, ToolResultEvent
from agent_debugger_sdk.core.events.llm import LLMRequestEvent, LLMResponseEvent
from agent_debugger_sdk.core.events.decisions import DecisionEvent
from agent_debugger_sdk.core.events.safety import SafetyCheckEvent, RefusalEvent
from agent_debugger_sdk.core.events.agent import AgentTurnEvent, BehaviorAlertEvent
from agent_debugger_sdk.core.events.errors import ErrorEvent
print('Domain files OK')
"
```
Expected: "Domain files OK"

- [ ] **Step 8: Commit domain files**
```bash
git add agent_debugger_sdk/core/events/tools.py agent_debugger_sdk/core/events/llm.py agent_debugger_sdk/core/events/decisions.py agent_debugger_sdk/core/events/safety.py agent_debugger_sdk/core/events/agent.py agent_debugger_sdk/core/events/errors.py
git commit -m "refactor(events): create domain event modules

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Create events metadata and registry
**Files:**
- Create: `agent_debugger_sdk/core/events/session.py`
- Create: `agent_debugger_sdk/core/events/checkpoint.py`
- Create: `agent_debugger_sdk/core/events/registry.py`

- [ ] **Step 1: Create events/session.py**
```python
# events/session.py
"""Session metadata for agent execution traces."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .base import SessionStatus


@dataclass(kw_only=True)
class Session:
    """Dataclass representing a complete agent execution session."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    framework: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    status: SessionStatus = SessionStatus.RUNNING
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0
    replay_value: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = SessionStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a dictionary."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "framework": self.framework,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": str(self.status),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
            "replay_value": self.replay_value,
            "config": self.config,
            "tags": self.tags,
        }
```

- [ ] **Step 2: Create events/checkpoint.py**
```python
# events/checkpoint.py
"""Checkpoint for time-travel debugging."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(kw_only=True)
class Checkpoint:
    """Dataclass representing a state snapshot for time-travel debugging."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""
    sequence: int = 0
    state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    importance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize the checkpoint to a dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "state": self.state,
            "memory": self.memory,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
        }
```

- [ ] **Step 3: Create events/registry.py**
```python
# events/registry.py
"""Event type registry for deserialization."""

from .base import EventType, TraceEvent
from .tools import ToolCallEvent, ToolResultEvent
from .llm import LLMRequestEvent, LLMResponseEvent
from .decisions import DecisionEvent
from .safety import SafetyCheckEvent, RefusalEvent, PolicyViolationEvent, PromptPolicyEvent
from .agent import AgentTurnEvent, BehaviorAlertEvent
from .errors import ErrorEvent

EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = {
    EventType.TOOL_CALL: ToolCallEvent,
    EventType.TOOL_RESULT: ToolResultEvent,
    EventType.LLM_REQUEST: LLMRequestEvent,
    EventType.LLM_RESPONSE: LLMResponseEvent,
    EventType.DECISION: DecisionEvent,
    EventType.SAFETY_CHECK: SafetyCheckEvent,
    EventType.REFUSAL: RefusalEvent,
    EventType.POLICY_VIOLATION: PolicyViolationEvent,
    EventType.PROMPT_POLICY: PromptPolicyEvent,
    EventType.AGENT_TURN: AgentTurnEvent,
    EventType.BEHAVIOR_ALERT: BehaviorAlertEvent,
    EventType.ERROR: ErrorEvent,
}
```

- [ ] **Step 4: Commit metadata and registry**
```bash
git add agent_debugger_sdk/core/events/session.py agent_debugger_sdk/core/events/checkpoint.py agent_debugger_sdk/core/events/registry.py
git commit -m "refactor(events): create session, checkpoint, and registry modules

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Complete events/ package
**Files:**
- Create: `agent_debugger_sdk/core/events/__init__.py`
- Delete: `agent_debugger_sdk/core/events.py`

- [ ] **Step 1: Create events/__init__.py with all re-exports**
```python
# events/__init__.py
"""SDK Core events package - re-exports for backward compatibility."""

# Python 3.10 compatibility: StrEnum shim lives in base.py
from .base import (
    EventType,
    SessionStatus,
    RiskLevel,
    SafetyOutcome,
    TraceEvent,
    BASE_EVENT_FIELDS,
    _serialize_field_value,
)
from .tools import ToolCallEvent, ToolResultEvent
from .llm import LLMRequestEvent, LLMResponseEvent
from .decisions import DecisionEvent
from .safety import (
    SafetyCheckEvent,
    RefusalEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
)
from .agent import AgentTurnEvent, BehaviorAlertEvent
from .errors import ErrorEvent
from .session import Session
from .checkpoint import Checkpoint
from .registry import EVENT_TYPE_REGISTRY

__all__ = [
    "EventType",
    "SessionStatus",
    "RiskLevel",
    "SafetyOutcome",
    "TraceEvent",
    "BASE_EVENT_FIELDS",
    "_serialize_field_value",
    "ToolCallEvent",
    "ToolResultEvent",
    "LLMRequestEvent",
    "LLMResponseEvent",
    "DecisionEvent",
    "SafetyCheckEvent",
    "RefusalEvent",
    "PolicyViolationEvent",
    "PromptPolicyEvent",
    "AgentTurnEvent",
    "BehaviorAlertEvent",
    "ErrorEvent",
    "Session",
    "Checkpoint",
    "EVENT_TYPE_REGISTRY",
]
```

- [ ] **Step 2: Verify events/ imports work before deletion**
```bash
python3 -c "
from agent_debugger_sdk.core.events import (
    EventType, TraceEvent, ToolCallEvent, ToolResultEvent,
    LLMRequestEvent, LLMResponseEvent, DecisionEvent,
    SafetyCheckEvent, Session, Checkpoint, EVENT_TYPE_REGISTRY
)
print('events/ package imports OK')
"
```
Expected: "events/ package imports OK"

- [ ] **Step 3: Delete old events.py**
```bash
git rm agent_debugger_sdk/core/events.py
```

- [ ] **Step 4: Run ruff check**
```bash
ruff check agent_debugger_sdk/core/events/
```
Expected: No errors

- [ ] **Step 5: Run tests**
```bash
python3 -m pytest -q
```
Expected: All tests pass

- [ ] **Step 6: Commit events/ package completion**
```bash
git commit -m "refactor(events): complete events/ package, delete events.py

- Split events.py (574 lines) into 11 domain-focused modules
- All existing imports preserved via __init__.py re-exports

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Create context/vars.py
**Files:**
- Create: `agent_debugger_sdk/core/context/vars.py`

- [ ] **Step 1: Create context/ directory**
```bash
mkdir -p agent_debugger_sdk/core/context
```

- [ ] **Step 2: Create context/vars.py with ALL ContextVars**
```python
# context/vars.py
"""ContextVar declarations for async-safe state management."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.emitter import EventBufferLike
    from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent

    from .trace_context import TraceContext

# ContextVar declarations (9 total)
_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_parent_id: ContextVar[str | None] = ContextVar("current_parent_id", default=None)
_event_sequence: ContextVar[int] = ContextVar("event_sequence", default=0)
_current_context: ContextVar[TraceContext | None] = ContextVar("current_context", default=None)
_default_event_buffer: ContextVar[EventBufferLike | None] = ContextVar("default_event_buffer", default=None)
_default_event_persister: ContextVar[None] = ContextVar(  # Type set at runtime
    "default_event_persister",
    default=None,
)
_default_checkpoint_persister: ContextVar[None] = ContextVar(
    "default_checkpoint_persister",
    default=None,
)
_default_session_start_hook: ContextVar[None] = ContextVar(
    "default_session_start_hook",
    default=None,
)
_default_session_update_hook: ContextVar[None] = ContextVar(
    "default_session_update_hook",
    default=None,
)


def get_current_context() -> TraceContext | None:
    """Get the currently active TraceContext."""
    return _current_context.get()


def get_current_session_id() -> str | None:
    """Get the current session ID."""
    return _current_session_id.get()


def get_current_parent_id() -> str | None:
    """Get the current parent event ID."""
    return _current_parent_id.get()
```

- [ ] **Step 3: Commit vars.py**
```bash
git add agent_debugger_sdk/core/context/vars.py
git commit -m "refactor(context): create vars.py with ContextVar declarations

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Create context/pipeline.py
**Files:**
- Create: `agent_debugger_sdk/core/context/pipeline.py`

- [ ] **Step 1: Create context/pipeline.py**
```python
# context/pipeline.py
"""Event pipeline configuration for connecting SDK to collector."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.emitter import EventBufferLike
    from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent

from .vars import (
    _default_event_buffer,
    _default_event_persister,
    _default_checkpoint_persister,
    _default_session_start_hook,
    _default_session_update_hook,
)


def _get_default_event_buffer() -> EventBufferLike | None:
    """Resolve the shared event buffer lazily.

    Importing collector modules at SDK import time creates a package-level cycle.
    Resolve the singleton only when a context is instantiated and only when no
    explicit/default buffer has already been configured.
    """
    configured = _default_event_buffer.get()
    if configured is not None:
        return configured

    try:
        from collector.buffer import get_event_buffer
    except ImportError:
        return None
    return get_event_buffer()


def configure_event_pipeline(
    buffer: EventBufferLike | None,
    *,
    persist_event: Callable[[TraceEvent], Awaitable[None]] | None = None,
    persist_checkpoint: Callable[[Checkpoint], Awaitable[None]] | None = None,
    persist_session_start: Callable[[Session], Awaitable[None]] | None = None,
    persist_session_update: Callable[[Session], Awaitable[None]] | None = None,
) -> None:
    """Configure the default event buffer for the event pipeline.

    This connects the SDK's TraceContext to the collector's EventBuffer,
    enabling real-time event streaming and persistence.

    Args:
        buffer: The EventBuffer to use for publishing events, or None to disconnect.
        persist_event: Optional async callback used to persist each emitted event.
        persist_checkpoint: Optional async callback used to persist each checkpoint.
        persist_session_start: Optional async callback used to create a session.
        persist_session_update: Optional async callback used to update a session.
    """
    _default_event_buffer.set(buffer)
    _default_event_persister.set(persist_event)
    _default_checkpoint_persister.set(persist_checkpoint)
    _default_session_start_hook.set(persist_session_start)
    _default_session_update_hook.set(persist_session_update)
```

- [ ] **Step 2: Commit pipeline.py**
```bash
git add agent_debugger_sdk/core/context/pipeline.py
git commit -m "refactor(context): create pipeline.py with configure_event_pipeline

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Create context/trace_context.py
**Files:**
- Create: `agent_debugger_sdk/core/context/trace_context.py`

- [ ] **Step 1: Create context/trace_context.py with full TraceContext class**

Extract the complete TraceContext class from `agent_debugger_sdk/core/context.py` (lines 99-508). Keep all methods intact, update imports to use relative paths.

```python
# context/trace_context.py
"""TraceContext class for managing async-safe tracing state."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from agent_debugger_sdk.core.emitter import EventBufferLike, EventEmitter
from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from agent_debugger_sdk.core.recorders import RecordingMixin

from .pipeline import _get_default_event_buffer
from .vars import (
    _current_session_id,
    _current_parent_id,
    _event_sequence,
    _current_context,
    _default_event_buffer,
    _default_event_persister,
    _default_checkpoint_persister,
    _default_session_start_hook,
    _default_session_update_hook,
)


class TraceContext(RecordingMixin):
    """Async-safe context manager for tracing agent execution.

    ... (full docstring and implementation from original context.py)
    """

    # Copy entire TraceContext class implementation here
    # Including: __init__, restore, __aenter__, __aexit__,
    # create_checkpoint, set_parent, get_current_parent, clear_parent,
    # get_event_sequence, get_events, drain_events, _check_entered, _emit_event
    # ... (full implementation - see source file)
```

- [ ] **Step 2: Verify trace_context imports**
```bash
python3 -c "from agent_debugger_sdk.core.context.trace_context import TraceContext; print('trace_context.py OK')"
```
Expected: "trace_context.py OK"

- [ ] **Step 3: Commit trace_context.py**
```bash
git add agent_debugger_sdk/core/context/trace_context.py
git commit -m "refactor(context): create trace_context.py with TraceContext class

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Complete context/ package
**Files:**
- Create: `agent_debugger_sdk/core/context/__init__.py`
- Delete: `agent_debugger_sdk/core/context.py`

- [ ] **Step 1: Create context/__init__.py**
```python
# context/__init__.py
"""SDK Core context package - re-exports for backward compatibility."""

from .pipeline import configure_event_pipeline
from .trace_context import TraceContext
from .vars import get_current_context, get_current_parent_id, get_current_session_id

__all__ = [
    "TraceContext",
    "get_current_context",
    "get_current_session_id",
    "get_current_parent_id",
    "configure_event_pipeline",
]
```

- [ ] **Step 2: Verify context/ imports work**
```bash
python3 -c "
from agent_debugger_sdk.core.context import (
    TraceContext, get_current_context, get_current_session_id,
    get_current_parent_id, configure_event_pipeline
)
print('context/ package imports OK')
"
```
Expected: "context/ package imports OK"

- [ ] **Step 3: Delete old context.py**
```bash
git rm agent_debugger_sdk/core/context.py
```

- [ ] **Step 4: Run ruff check**
```bash
ruff check agent_debugger_sdk/core/context/
```
Expected: No errors

- [ ] **Step 5: Run tests**
```bash
python3 -m pytest -q
```
Expected: All tests pass

- [ ] **Step 6: Commit context/ package completion**
```bash
git commit -m "refactor(context): complete context/ package, delete context.py

- Split context.py (536 lines) into 3 focused modules
- All existing imports preserved via __init__.py re-exports

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Create decorators/_utils.py
**Files:**
- Create: `agent_debugger_sdk/core/decorators/_utils.py`

- [ ] **Step 1: Create decorators/ directory**
```bash
mkdir -p agent_debugger_sdk/core/decorators
```

- [ ] **Step 2: Create decorators/_utils.py with shared helpers**
```python
# decorators/_utils.py
"""Shared helper functions for decorators."""

from __future__ import annotations

from typing import Any


def _sanitize_arguments(args: tuple, kwargs: dict) -> dict[str, Any]:
    """Sanitize function arguments for trace storage."""
    sanitized: dict[str, Any] = {}

    for i, arg in enumerate(args):
        sanitized[f"arg_{i}"] = _truncate_value(arg)

    for key, value in kwargs.items():
        sanitized[key] = _truncate_value(value)

    return sanitized


def _truncate_value(value: Any, max_length: int = 1000) -> Any:
    """Truncate a value if it's too large for trace storage."""
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + "...[truncated]"
        return value

    if isinstance(value, list | tuple):
        if len(value) > 100:
            return [_truncate_value(v, max_length) for v in value[:10]] + [f"...[{len(value) - 10} more items]"]
        return [_truncate_value(v, max_length) for v in value]

    if isinstance(value, dict):
        if len(value) > 50:
            truncated = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= 20:
                    truncated["__truncated__"] = f"{len(value) - 20} more keys"
                    break
                truncated[k] = _truncate_value(v, max_length)
            return truncated
        return {k: _truncate_value(v, max_length) for k, v in value.items()}

    return value


def _sanitize_result(result: Any) -> Any:
    """Sanitize a function result for trace storage."""
    return _truncate_value(result, max_length=5000)


def _extract_messages(args: tuple, kwargs: dict) -> list[dict[str, Any]]:
    """Extract messages from LLM call arguments."""
    if "messages" in kwargs:
        messages = kwargs["messages"]
        if isinstance(messages, list):
            return _truncate_value(messages)
        return [{"role": "unknown", "content": str(messages)}]

    for arg in args:
        if (
            isinstance(arg, list)
            and len(arg) > 0
            and isinstance(arg[0], dict)
            and ("role" in arg[0] or "content" in arg[0])
        ):
            return _truncate_value(arg)

    return []


def _extract_tools(args: tuple, kwargs: dict) -> list[dict[str, Any]]:
    """Extract tool definitions from LLM call arguments."""
    if "tools" in kwargs:
        return _truncate_value(kwargs["tools"])
    return []


def _extract_settings(args: tuple, kwargs: dict) -> dict[str, Any]:
    """Extract model settings from LLM call arguments."""
    settings: dict[str, Any] = {}

    for key in ["temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty"]:
        if key in kwargs:
            settings[key] = kwargs[key]

    return settings


def _extract_llm_response(result: Any) -> tuple[str, dict[str, int], float, list[dict[str, Any]]]:
    """Extract content, usage, cost, and tool_calls from an LLM response.

    Handles various response formats (dict, object with attributes).

    Returns:
        A tuple of (content, usage, cost_usd, tool_calls)
    """
    content = ""
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    cost_usd = 0.0
    tool_calls: list[dict[str, Any]] = []

    if isinstance(result, str):
        content = result
    elif isinstance(result, dict):
        content = result.get("content", "")
        if "usage" in result:
            usage = result["usage"]
        if "cost_usd" in result:
            cost_usd = result["cost_usd"]
        if "tool_calls" in result:
            tool_calls = result["tool_calls"]
    else:
        # Try attribute access
        if hasattr(result, "content"):
            try:
                content = str(result.content)
            except (AttributeError, IndexError, KeyError):
                content = str(result)

        if hasattr(result, "usage"):
            with contextlib.suppress(AttributeError):
                usage = {
                    "input_tokens": getattr(result.usage, "prompt_tokens", 0),
                    "output_tokens": getattr(result.usage, "completion_tokens", 0),
                }

        if hasattr(result, "tool_calls"):
            with contextlib.suppress(AttributeError):
                tool_calls = []
                for tc in result.tool_calls:
                    tool_calls.append(
                        {
                            "id": getattr(tc, "id", ""),
                            "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                            "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else {},
                        }
                    )

    content = _truncate_value(content) if isinstance(content, str) else str(content)
    return content, usage, cost_usd, tool_calls
```

- [ ] **Step 3: Add missing import to _utils.py**
```python
# Add at the top of _utils.py after typing import:
import contextlib
```

- [ ] **Step 4: Commit _utils.py**
```bash
git add agent_debugger_sdk/core/decorators/_utils.py
git commit -m "refactor(decorators): create _utils.py with shared helper functions

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Create decorators/agent.py
**Files:**
- Create: `agent_debugger_sdk/core/decorators/agent.py`

- [ ] **Step 1: Create decorators/agent.py**
```python
# decorators/agent.py
"""trace_agent decorator for instrumenting agent functions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from agent_debugger_sdk.core.context import TraceContext

P = ParamSpec("P")
T = TypeVar("T")


def trace_agent(
    name: str,
    framework: str = "unknown",
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace an async agent function.

    Creates a new trace session on entry, records AGENT_START and AGENT_END
    events, and captures any exceptions as ERROR events.

    Args:
        name: Human-readable name for the agent.
        framework: The agent framework being used (pydantic_ai, langchain, autogen).

    Returns:
        A decorator function that wraps async agent functions.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ctx = TraceContext(
                agent_name=name,
                framework=framework,
            )

            async with ctx:
                # Use the session start event's ID as the parent for child events
                if ctx._session_start_event:
                    ctx.set_parent(ctx._session_start_event.id)

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception:
                    # Error is already recorded by TraceContext.__aexit__
                    raise

        return async_wrapper

    return decorator
```

- [ ] **Step 2: Commit agent.py**
```bash
git add agent_debugger_sdk/core/decorators/agent.py
git commit -m "refactor(decorators): create agent.py with trace_agent decorator

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Create decorators/tool.py
**Files:**
- Create: `agent_debugger_sdk/core/decorators/tool.py`

- [ ] **Step 1: Create decorators/tool.py**
```python
# decorators/tool.py
"""trace_tool decorator for instrumenting tool functions."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.events import EventType, ToolCallEvent, ToolResultEvent

from ._utils import _sanitize_arguments, _sanitize_result

P = ParamSpec("P")
T = TypeVar("T")


def trace_tool(
    name: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace a tool function.

    Records TOOL_CALL before execution and TOOL_RESULT after execution,
    including duration and any errors.

    Args:
        name: Human-readable name for the tool.

    Returns:
        A decorator function that wraps async tool functions.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ctx = get_current_context()
            own_context = ctx is None

            if own_context:
                ctx = TraceContext(
                    agent_name="tool_runner",
                    framework="unknown",
                )
                await ctx.__aenter__()

            if ctx is None:
                raise RuntimeError("TraceContext is None - this should not happen")

            tool_call_event = ToolCallEvent(
                session_id=ctx.session_id,
                parent_id=ctx.get_current_parent(),
                event_type=EventType.TOOL_CALL,
                name=f"{name}_call",
                tool_name=name,
                arguments=_sanitize_arguments(args, kwargs),
                importance=0.4,
            )
            await ctx._emit_event(tool_call_event)

            start_time = time.perf_counter()
            error: Exception | None = None
            result: T | None = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = e
                raise
            finally:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000

                tool_result_event = ToolResultEvent(
                    session_id=ctx.session_id,
                    parent_id=tool_call_event.id,
                    event_type=EventType.TOOL_RESULT,
                    name=f"{name}_result",
                    tool_name=name,
                    result=_sanitize_result(result) if error is None else None,
                    error=str(error) if error else None,
                    duration_ms=duration_ms,
                    importance=0.9 if error else 0.5,
                )
                await ctx._emit_event(tool_result_event)

                if own_context:
                    if error is not None:
                        await ctx.__aexit__(type(error), error, error.__traceback__)
                    else:
                        await ctx.__aexit__(None, None, None)

        return async_wrapper

    return decorator
```

- [ ] **Step 2: Commit tool.py**
```bash
git add agent_debugger_sdk/core/decorators/tool.py
git commit -m "refactor(decorators): create tool.py with trace_tool decorator

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Create decorators/llm.py
**Files:**
- Create: `agent_debugger_sdk/core/decorators/llm.py`

- [ ] **Step 1: Create decorators/llm.py**
```python
# decorators/llm.py
"""trace_llm decorator for instrumenting LLM calls."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.events import EventType, LLMRequestEvent, LLMResponseEvent

from ._utils import _extract_llm_response, _extract_messages, _extract_settings, _extract_tools

P = ParamSpec("P")
T = TypeVar("T")


def trace_llm(
    model: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace an LLM call function.

    Records LLM_REQUEST before the call and LLM_RESPONSE after, including
    token usage, cost, and duration.

    Args:
        model: The model identifier (e.g., "gpt-4o", "claude-3-opus").

    Returns:
        A decorator function that wraps async LLM call functions.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ctx = get_current_context()
            own_context = ctx is None

            if own_context:
                ctx = TraceContext(
                    agent_name="llm_runner",
                    framework="unknown",
                )
                await ctx.__aenter__()

            if ctx is None:
                raise RuntimeError("TraceContext is None - this should not happen")

            messages = _extract_messages(args, kwargs)

            llm_request_event = LLMRequestEvent(
                session_id=ctx.session_id,
                parent_id=ctx.get_current_parent(),
                event_type=EventType.LLM_REQUEST,
                name=f"llm_call_{model}",
                model=model,
                messages=messages,
                tools=_extract_tools(args, kwargs),
                settings=_extract_settings(args, kwargs),
                importance=0.3,
            )
            await ctx._emit_event(llm_request_event)

            start_time = time.perf_counter()
            error: Exception | None = None
            result: T | None = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = e
                raise
            finally:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000

                content = ""
                usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
                cost_usd = 0.0
                tool_calls: list[dict[str, Any]] = []

                if result is not None and error is None:
                    content, usage, cost_usd, tool_calls = _extract_llm_response(result)

                llm_response_event = LLMResponseEvent(
                    session_id=ctx.session_id,
                    parent_id=llm_request_event.id,
                    event_type=EventType.LLM_RESPONSE,
                    name=f"llm_response_{model}",
                    model=model,
                    content=content,
                    tool_calls=tool_calls,
                    usage=usage,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                    importance=0.9 if error else 0.5,
                )
                await ctx._emit_event(llm_response_event)

                if own_context:
                    if error is not None:
                        await ctx.__aexit__(type(error), error, error.__traceback__)
                    else:
                        await ctx.__aexit__(None, None, None)

        return async_wrapper

    return decorator
```

- [ ] **Step 2: Commit llm.py**
```bash
git add agent_debugger_sdk/core/decorators/llm.py
git commit -m "refactor(decorators): create llm.py with trace_llm decorator

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: Complete decorators/ package
**Files:**
- Create: `agent_debugger_sdk/core/decorators/__init__.py`
- Delete: `agent_debugger_sdk/core/decorators.py`

- [ ] **Step 1: Create decorators/__init__.py**
```python
# decorators/__init__.py
"""SDK Core decorators package - re-exports for backward compatibility."""

from .agent import trace_agent
from .llm import trace_llm
from .tool import trace_tool

__all__ = ["trace_agent", "trace_tool", "trace_llm"]
```

- [ ] **Step 2: Verify decorators/ imports work**
```bash
python3 -c "
from agent_debugger_sdk.core.decorators import trace_agent, trace_tool, trace_llm
print('decorators/ package imports OK')
"
```
Expected: "decorators/ package imports OK"

- [ ] **Step 3: Delete old decorators.py**
```bash
git rm agent_debugger_sdk/core/decorators.py
```

- [ ] **Step 4: Run ruff check**
```bash
ruff check agent_debugger_sdk/core/decorators/
```
Expected: No errors

- [ ] **Step 5: Run tests**
```bash
python3 -m pytest -q
```
Expected: All tests pass

- [ ] **Step 6: Commit decorators/ package completion**
```bash
git commit -m "refactor(decorators): complete decorators/ package, delete decorators.py

- Split decorators.py (491 lines) into 4 focused modules
- _utils.py: shared helper functions
- agent.py, tool.py, llm.py: decorator implementations
- All existing imports preserved via __init__.py re-exports

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 14: Final Verification
**Files:**
- Verify: All package imports work
- Verify: core/__init__.py still works

- [ ] **Step 1: Read core/__init__.py to verify it doesn't need updates**
```bash
cat agent_debugger_sdk/core/__init__.py
```
Expected: Should import from `.events`, `.context`, `.decorators` - these still work because __init__.py re-exports

- [ ] **Step 2: Run comprehensive smoke test**
```bash
python3 -c "
from agent_debugger_sdk.core.events import (
    EventType, TraceEvent, ToolCallEvent, ToolResultEvent,
    LLMRequestEvent, LLMResponseEvent, DecisionEvent,
    SafetyCheckEvent, Session, Checkpoint, EVENT_TYPE_REGISTRY
)
from agent_debugger_sdk.core.context import (
    TraceContext, get_current_context, configure_event_pipeline
)
from agent_debugger_sdk.core.decorators import trace_agent, trace_tool, trace_llm
print('All imports successful')
"
```
Expected: "All imports successful"

- [ ] **Step 3: Run ruff check on entire codebase**
```bash
ruff check .
```
Expected: All checks passed!

- [ ] **Step 4: Run full test suite**
```bash
python3 -m pytest -q
```
Expected: All tests pass

- [ ] **Step 5: Final summary commit**
```bash
git add -A
git commit -m "refactor: complete SDK core decomposition

Summary:
- events.py (574 lines) → events/ package with 11 domain modules
- context.py (536 lines) → context/ package with 3 modules
- decorators.py (491 lines) → decorators/ package with 4 modules

All existing imports preserved via __init__.py re-exports.
Largest module reduced from 574 to ~430 lines (25% reduction).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Files Created | Commits |
|------|-------------|---------------|---------|
| 1 | Create events/base.py | 1 | 1 |
| 2 | Create events domain files | 6 | 1 |
| 3 | Create events metadata/registry | 3 | 1 |
| 4 | Complete events/ package | 1 (delete 1) | 1 |
| 5 | Create context/vars.py | 1 | 1 |
| 6 | Create context/pipeline.py | 1 | 1 |
| 7 | Create context/trace_context.py | 1 | 1 |
| 8 | Complete context/ package | 1 (delete 1) | 1 |
| 9 | Create decorators/_utils.py | 1 | 1 |
| 10 | Create decorators/agent.py | 1 | 1 |
| 11 | Create decorators/tool.py | 1 | 1 |
| 12 | Create decorators/llm.py | 1 | 1 |
| 13 | Complete decorators/ package | 1 (delete 1) | 1 |
| 14 | Final verification | 0 | 1 |

**Total:** 20 new files, 3 deleted files, 15 commits
