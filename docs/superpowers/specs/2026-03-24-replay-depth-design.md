# Replay Depth L1 + L2 Design

> **Spec for:** Standardized checkpoint schemas + manual restore API
>
> **Date:** 2026-03-24

---

## Overview

Enable execution restoration from checkpoints by:
1. **L1:** Standardizing checkpoint state schemas per framework
2. **L2:** Providing a manual restore API to load checkpoint state into a new TraceContext

**Not included (future phases):**
- Auto-replay of events after checkpoint
- Divergence detection between original and restored execution
- Cached response deterministic replay

---

## 1. Checkpoint Schemas

### 1.1 Base Schema

All checkpoints share a common base with framework-specific extensions.

```python
# agent_debugger_sdk/checkpoints/schemas.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class BaseCheckpointState:
    """Common fields all checkpoints must have."""
    framework: str  # "langchain" | "custom"
    label: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

### 1.2 LangChain Schema

```python
@dataclass
class LangChainCheckpointState(BaseCheckpointState):
    """Checkpoint for LangChain agents/runnables.

    Captures the essential state needed to restore a LangChain agent:
    - messages: Full conversation history
    - intermediate_steps: Agent's tool call scratchpad
    - run metadata: For tracing back to original execution
    """
    framework: str = "langchain"
    messages: list[dict] = field(default_factory=list)
    intermediate_steps: list[dict] = field(default_factory=list)
    run_name: str = ""
    run_id: str = ""
    metadata: dict = field(default_factory=dict)
```

### 1.3 Custom Schema

```python
@dataclass
class CustomCheckpointState(BaseCheckpointState):
    """User-defined checkpoint with minimal validation.

    For agents that don't fit a framework schema, users can store
    arbitrary state. The SDK validates only the base fields.
    """
    framework: str = "custom"
    data: dict = field(default_factory=dict)
```

### 1.4 Validation Rules

- **Known fields:** Validated against schema (type checking, required fields)
- **Unknown fields:** Stored in `state["_extra"]` and passed through unchanged
- **Framework detection:** Auto-detect from `state.get("framework", "custom")`
- **Backward compatibility:** Existing checkpoints without `framework` field default to `"custom"`

---

## 2. SDK API

### 2.1 TraceContext.restore()

```python
class TraceContext:
    @classmethod
    async def restore(
        cls,
        checkpoint_id: str,
        *,
        session_id: str | None = None,
        server_url: str | None = None,
        label: str = "",
    ) -> "TraceContext":
        """Restore execution from a checkpoint.

        Creates a new TraceContext pre-populated with checkpoint state.
        The restored session references the original in metadata.

        Args:
            checkpoint_id: ID of checkpoint to restore from
            session_id: Optional session ID for restored session (new if None)
            server_url: Server URL (uses default if None)
            label: Label for the restored session

        Returns:
            TraceContext with restored state accessible via ctx.restored_state

        Example:
            async with TraceContext.restore("cp-abc123") as ctx:
                state = ctx.restored_state  # LangChainCheckpointState
                messages = state.messages   # Pre-populated history
                # Continue agent execution...
        """
```

### 2.2 TraceContext.restored_state Property

```python
@property
def restored_state(self) -> BaseCheckpointState | None:
    """The checkpoint state this context was restored from, if any."""
    return self._restored_state
```

### 2.3 Enhanced create_checkpoint()

```python
async def create_checkpoint(
    self,
    state: BaseCheckpointState | dict,
    memory: dict | None = None,
    importance: float = 0.5,
) -> str:
    """Create checkpoint with validated state schema.

    Args:
        state: Checkpoint state (dataclass or dict). If dict, validated
               against the appropriate schema based on framework field.
        memory: Optional memory/context snapshot
        importance: Relative importance (0.0-1.0)

    Returns:
        Checkpoint ID

    Raises:
        ValidationError: If state doesn't match schema

    Example:
        state = LangChainCheckpointState(
            label="after_tool_call",
            messages=[{"role": "user", "content": "..."}],
            intermediate_steps=[{"tool": "search", "result": "..."}],
        )
        await ctx.create_checkpoint(state, importance=0.9)
    """
```

---

## 3. REST API

### 3.1 Restore Endpoint

```
POST /api/checkpoints/{checkpoint_id}/restore
```

**Request:**
```json
{
  "session_id": null,
  "label": "restored from checkpoint abc"
}
```

**Response:**
```json
{
  "checkpoint_id": "cp-abc123",
  "original_session_id": "sess-old",
  "new_session_id": "sess-new",
  "restored_at": "2026-03-24T12:00:00Z",
  "state": {
    "framework": "langchain",
    "messages": [...],
    "intermediate_steps": [...]
  },
  "restore_token": "restore_xyz"
}
```

**Fields:**
- `session_id`: Target session (null = create new)
- `restore_token`: Token for SDK to pick up restored state

### 3.2 Get Checkpoint Endpoint (New)

```
GET /api/checkpoints/{checkpoint_id}
```

**Response:**
```json
{
  "id": "cp-abc123",
  "session_id": "sess-old",
  "event_id": "evt-123",
  "sequence": 1,
  "state": { ... },
  "memory": { ... },
  "timestamp": "2026-03-24T11:00:00Z",
  "importance": 0.9
}
```

---

## 4. Data Model Changes

### 4.1 Checkpoint Model

No schema changes. The `state` column already stores JSON. The new validation happens at the SDK layer, not the database layer.

### 4.2 Session Metadata

Restored sessions include metadata linking to original:

```json
{
  "restored_from_checkpoint": "cp-abc123",
  "original_session_id": "sess-old",
  "restore_token": "restore_xyz"
}
```

---

## 5. Error Handling

| Error | HTTP Status | Condition |
|-------|-------------|-----------|
| `CheckpointNotFound` | 404 | Checkpoint ID doesn't exist |
| `SessionNotFound` | 404 | Target session doesn't exist |
| `InvalidCheckpointState` | 400 | State validation failed |
| `RestoreFailed` | 500 | Internal restore error |

---

## 6. Implementation Order

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| **1. Schemas** | Create `checkpoints/` module with schemas | 1h |
| **2. Validation** | Add validation to `create_checkpoint()` | 1h |
| **3. Repository** | Add `get_checkpoint()` method | 30m |
| **4. REST API** | Add GET/POST checkpoint endpoints | 1h |
| **5. SDK Restore** | Implement `TraceContext.restore()` | 1.5h |
| **6. Tests** | Unit + integration tests | 1h |

**Total:** ~6 hours

---

## 7. Files Changed

| File | Action | Changes |
|------|--------|---------|
| `agent_debugger_sdk/checkpoints/__init__.py` | CREATE | Module exports |
| `agent_debugger_sdk/checkpoints/schemas.py` | CREATE | `BaseCheckpointState`, `LangChainCheckpointState`, `CustomCheckpointState` |
| `agent_debugger_sdk/core/context.py` | MODIFY | Add `restore()`, `restored_state` property, validate in `create_checkpoint()` |
| `agent_debugger_sdk/__init__.py` | MODIFY | Export checkpoint classes |
| `api/replay_routes.py` | MODIFY | Add `GET /checkpoints/{id}`, `POST /checkpoints/{id}/restore` |
| `api/schemas.py` | MODIFY | Add `CheckpointResponse`, `RestoreRequest`, `RestoreResponse` |
| `storage/repository.py` | MODIFY | Add `get_checkpoint()` method |
| `tests/test_checkpoint_restore.py` | CREATE | Unit + integration tests |

---

## 8. Future Considerations

Not in scope but designed to support:

1. **PydanticAI/CrewAI schemas** - Add new dataclasses following the same pattern
2. **Auto-replay** - `restore(replay_events=True)` option
3. **Divergence detection** - Compare restored execution vs original events
4. **Cached responses** - Store LLM responses in checkpoint for deterministic replay
