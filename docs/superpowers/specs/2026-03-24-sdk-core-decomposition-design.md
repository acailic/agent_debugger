# SDK Core File Decomposition Design

**Date:** 2026-03-24
**Status:** Approved
**Author:** acailic

## Goals

- Reduce large files (`events.py` 574 lines, `context.py` 536 lines, `decorators.py` 491 lines) into navigable domain-focused modules
- Preserve all existing imports via `__init__.py` re-exports (zero breaking changes)
- Improve discoverability: find "safety events" in `safety.py`, not buried in a 570-line file

## Context

The SDK core has three large files that are difficult to navigate:

- `events.py` - Contains 4 enums, 1 base class, 12 specialized event dataclasses, 2 metadata classes, and a registry
- `context.py` - Contains global ContextVars, pipeline configuration, and a 420-line TraceContext class
- `decorators.py` - Contains 3 independent decorators with sync/async variants

Each file serves multiple concerns that would benefit from domain-based organization.

## Design

### events.py → events/ package

```
agent_debugger_sdk/core/events/
├── __init__.py          # Re-exports all public classes/enums
├── base.py              # EventType, SessionStatus, RiskLevel, SafetyOutcome enums
│                        # StrEnum compatibility shim (Python 3.10)
│                        # TraceEvent base class, BASE_EVENT_FIELDS, _serialize_field_value
├── tools.py             # ToolCallEvent, ToolResultEvent
├── llm.py               # LLMRequestEvent, LLMResponseEvent
├── decisions.py         # DecisionEvent
├── safety.py            # SafetyCheckEvent, RefusalEvent, PolicyViolationEvent, PromptPolicyEvent
├── agent.py             # AgentTurnEvent, BehaviorAlertEvent
├── errors.py            # ErrorEvent
├── session.py           # Session dataclass
├── checkpoint.py        # Checkpoint dataclass
└── registry.py          # EVENT_TYPE_REGISTRY mapping
```

**File responsibilities:**

| File | Contents | ~Lines |
|------|----------|--------|
| base.py | EventType, SessionStatus, RiskLevel, SafetyOutcome enums; StrEnum shim; TraceEvent class; BASE_EVENT_FIELDS, _serialize_field_value | ~200 |
| tools.py | ToolCallEvent, ToolResultEvent | ~40 |
| llm.py | LLMRequestEvent, LLMResponseEvent | ~60 |
| decisions.py | DecisionEvent | ~25 |
| safety.py | SafetyCheckEvent, RefusalEvent, PolicyViolationEvent, PromptPolicyEvent | ~80 |
| agent.py | AgentTurnEvent, BehaviorAlertEvent | ~30 |
| errors.py | ErrorEvent | ~20 |
| session.py | Session dataclass | ~60 |
| checkpoint.py | Checkpoint dataclass | ~40 |
| registry.py | EVENT_TYPE_REGISTRY dict | ~15 |

**__init__.py re-exports:**

```python
# Python 3.10 compatibility: StrEnum shim lives in base.py
from .base import (
    EventType,
    SessionStatus,
    RiskLevel,
    SafetyOutcome,
    TraceEvent,
    BASE_EVENT_FIELDS,      # Export for from_data() usage in domain files
    _serialize_field_value,  # Export for checkpoint serialization
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

**Internal imports (domain files use relative imports):**

```python
# In events/tools.py, events/llm.py, events/decisions.py, etc.
from .base import TraceEvent, EventType

# In events/safety.py
from .base import TraceEvent, EventType, RiskLevel, SafetyOutcome

# In events/registry.py
from .base import EventType, TraceEvent
from .tools import ToolCallEvent, ToolResultEvent
from .llm import LLMRequestEvent, LLMResponseEvent
# ... etc (import each domain file)
```

### context.py → context/ package

```
agent_debugger_sdk/core/context/
├── __init__.py          # Re-exports TraceContext, get_current_context, configure_event_pipeline
├── vars.py              # ContextVar declarations + get_current_session_id, get_current_parent_id
├── pipeline.py          # configure_event_pipeline, _get_default_event_buffer
└── trace_context.py     # TraceContext class (imports from ./vars and ./pipeline)
```

**File responsibilities:**

| File | Contents | ~Lines |
|------|----------|--------|
| vars.py | 6 ContextVar declarations, get_current_context, get_current_session_id, get_current_parent_id | ~50 |
| pipeline.py | _get_default_event_buffer, configure_event_pipeline | ~50 |
| trace_context.py | TraceContext class (kept intact) | ~430 |

**vars.py needs type annotations:**

```python
from __future__ import annotations
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import Session, SessionStatus

_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_parent_id: ContextVar[str | None] = ContextVar("current_parent_id", default=None)
# ... etc
```

**__init__.py re-exports:**

```python
from .vars import get_current_context, get_current_session_id, get_current_parent_id
from .pipeline import configure_event_pipeline
from .trace_context import TraceContext

__all__ = [
    "TraceContext",
    "get_current_context",
    "get_current_session_id",
    "get_current_parent_id",
    "configure_event_pipeline",
]
```

### decorators.py → decorators/ package

```
agent_debugger_sdk/core/decorators/
├── __init__.py          # Re-exports trace_agent, trace_tool, trace_llm
├── agent.py             # trace_agent decorator
├── tool.py              # trace_tool decorator
└── llm.py               # trace_llm decorator
```

**File responsibilities:**

| File | Contents | ~Lines |
|------|----------|--------|
| agent.py | trace_agent decorator + ParamSpec/TypeVar setup | ~90 |
| tool.py | trace_tool decorator | ~170 |
| llm.py | trace_llm decorator | ~170 |

**__init__.py re-exports:**

```python
from .agent import trace_agent
from .tool import trace_tool
from .llm import trace_llm

__all__ = ["trace_agent", "trace_tool", "trace_llm"]
```

## Implementation Order

1. **Create events/ package first** - No internal dependencies, safest to start with
2. **Create context/ package second** - Depends on events, needs careful handling of circular imports
3. **Create decorators/ package last** - Depends on context and events

## Import Compatibility

### External imports (unchanged)

```python
# These continue to work exactly as before
from agent_debugger_sdk.core.events import ToolCallEvent, TraceEvent
from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.decorators import trace_agent, trace_tool
```

### Internal imports (use relative)

Within packages, use relative imports:

```python
# In events/tools.py
from .base import TraceEvent, EventType

# In context/trace_context.py
from .vars import _current_session_id, _current_parent_id
from .pipeline import _get_default_event_buffer
```

## Files Requiring Import Verification

After decomposition, verify these key consumers:

- `agent_debugger_sdk/core/__init__.py`
- `agent_debugger_sdk/adapters/langchain.py`
- `agent_debugger_sdk/adapters/pydantic_ai.py`
- `agent_debugger_sdk/auto_patch/_transport.py`
- `agent_debugger_sdk/auto_patch/registry.py`
- `api/schemas.py`
- `api/services.py`
- `tests/` (all test files)

## Testing Strategy

1. Run `ruff check .` after each package migration
2. Run `python3 -m pytest -q` after each package migration
3. Verify import paths work with a quick smoke test:
   ```bash
   python3 -c "from agent_debugger_sdk.core.events import ToolCallEvent, TraceEvent, EVENT_TYPE_REGISTRY; from agent_debugger_sdk.core.context import TraceContext, get_current_context; from agent_debugger_sdk.core.decorators import trace_agent, trace_tool, trace_llm; print('All imports successful')"
   ```

## Expected Outcome

| Original File | Lines | Largest New Module | Lines |
|---------------|-------|-------------------|-------|
| events.py | 574 | base.py | ~200 |
| context.py | 536 | trace_context.py | ~430 |
| decorators.py | 491 | tool.py or llm.py | ~170 |

**Total reduction in largest file:** 574 → 430 lines (25% reduction)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Circular imports | Careful ordering; use `from . import` not `from package import`; TYPE_CHECKING for type hints |
| Missed import updates | Run full test suite after each package; smoke test command |
| Type checking breaks | Verify pyright/mypy after changes (future task) |

## Out of Scope

- `recorders.py` (372 lines) - Deferred to future work
- `api/schemas.py` (225 lines) - Different concern, not SDK core
- Any behavior changes - This is purely structural refactoring
