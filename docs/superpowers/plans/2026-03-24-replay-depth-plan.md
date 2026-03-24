# Replay Depth L1 + L2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement standardized checkpoint schemas and manual restore API for execution restoration from checkpoints.

**Architecture:** Create typed checkpoint dataclasses (BaseCheckpointState, LangChainCheckpointState, CustomCheckpointState) with validation. Add TraceContext.restore() classmethod to fetch checkpoint from server and create new context with restored state. Add REST endpoints for checkpoint GET and restore operations.

**Tech Stack:** Python dataclasses, Pydantic (existing), FastAPI (existing), SQLite (existing)

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `agent_debugger_sdk/checkpoints/__init__.py` | CREATE | Module entry point, exports |
| `agent_debugger_sdk/checkpoints/schemas.py` | CREATE | BaseCheckpointState, LangChainCheckpointState, CustomCheckpointState dataclasses |
| `agent_debugger_sdk/checkpoints/validation.py` | CREATE | validate_checkpoint_state(), serialize_state() helpers |
| `agent_debugger_sdk/core/context.py` | MODIFY | Add restore() classmethod, restored_state property, validation in create_checkpoint() |
| `agent_debugger_sdk/__init__.py` | MODIFY | Export checkpoint classes |
| `api/replay_routes.py` | MODIFY | Add GET /api/checkpoints/{id}, POST /api/checkpoints/{id}/restore |
| `api/schemas.py` | MODIFY | Add CheckpointResponse, RestoreRequest, RestoreResponse |
| `tests/test_checkpoint_restore.py` | CREATE | Unit tests for schemas + integration tests for restore flow |

---

## Task 1: Create Checkpoint Schemas Module

**Files:**
- Create: `agent_debugger_sdk/checkpoints/__init__.py`
- Create: `agent_debugger_sdk/checkpoints/schemas.py`
- Test: `tests/test_checkpoint_restore.py`

- [ ] **Step 1: Write failing test for BaseCheckpointState**

```python
# tests/test_checkpoint_restore.py
"""Tests for checkpoint schemas and restore functionality."""

from datetime import datetime

import pytest


class TestBaseCheckpointState:
    def test_base_checkpoint_state_defaults(self):
        """BaseCheckpointState should auto-populate created_at."""
        from agent_debugger_sdk.checkpoints import BaseCheckpointState

        state = BaseCheckpointState(framework="custom")
        assert state.framework == "custom"
        assert state.label == ""
        assert state.created_at  # Should be auto-populated

    def test_base_checkpoint_state_with_label(self):
        """BaseCheckpointState should accept optional label."""
        from agent_debugger_sdk.checkpoints import BaseCheckpointState

        state = BaseCheckpointState(framework="langchain", label="after_tool")
        assert state.label == "after_tool"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestBaseCheckpointState -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agent_debugger_sdk.checkpoints'"

- [ ] **Step 3: Create checkpoints module directory**

Run: `mkdir -p /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/agent_debugger_sdk/checkpoints`

- [ ] **Step 4: Create schemas.py with dataclasses**

```python
# agent_debugger_sdk/checkpoints/schemas.py
"""Typed checkpoint state schemas for framework-specific restoration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    """Return current UTC time as ISO format string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BaseCheckpointState:
    """Common fields all checkpoints must have.

    All framework-specific checkpoint schemas inherit from this base.
    The 'framework' field determines which schema to use for validation.

    Attributes:
        framework: Framework identifier ("langchain", "custom", etc.)
        label: Human-readable label for this checkpoint
        created_at: ISO timestamp when checkpoint was created
    """

    framework: str
    label: str = ""
    created_at: str = field(default_factory=_utcnow_iso)


@dataclass
class LangChainCheckpointState(BaseCheckpointState):
    """Checkpoint state for LangChain agents and runnables.

    Captures the essential state needed to restore a LangChain agent:
    - messages: Full conversation history
    - intermediate_steps: Agent's tool call scratchpad
    - run metadata: For tracing back to original execution
    """

    framework: str = "langchain"
    messages: list[dict[str, Any]] = field(default_factory=list)
    intermediate_steps: list[dict[str, Any]] = field(default_factory=list)
    run_name: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomCheckpointState(BaseCheckpointState):
    """User-defined checkpoint with minimal validation.

    For agents that don't fit a framework schema, users can store
    arbitrary state. The SDK validates only the base fields.
    """

    framework: str = "custom"
    data: dict[str, Any] = field(default_factory=dict)


# Registry mapping framework name to schema class
SCHEMA_REGISTRY: dict[str, type[BaseCheckpointState]] = {
    "langchain": LangChainCheckpointState,
    "custom": CustomCheckpointState,
}
```

- [ ] **Step 5: Create __init__.py with exports**

```python
# agent_debugger_sdk/checkpoints/__init__.py
"""Checkpoint schemas for execution restoration."""

from .schemas import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
    SCHEMA_REGISTRY,
)

__all__ = [
    "BaseCheckpointState",
    "CustomCheckpointState",
    "LangChainCheckpointState",
    "SCHEMA_REGISTRY",
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestBaseCheckpointState -v`
Expected: PASS

- [ ] **Step 7: Write failing test for LangChainCheckpointState**

```python
# Add to tests/test_checkpoint_restore.py

class TestLangChainCheckpointState:
    def test_langchain_checkpoint_state_defaults(self):
        """LangChainCheckpointState should have framework preset."""
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        state = LangChainCheckpointState()
        assert state.framework == "langchain"
        assert state.messages == []
        assert state.intermediate_steps == []

    def test_langchain_checkpoint_state_with_messages(self):
        """LangChainCheckpointState should accept messages."""
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        messages = [{"role": "user", "content": "Hello"}]
        state = LangChainCheckpointState(
            label="greeting",
            messages=messages,
            run_name="test_agent",
        )
        assert state.messages == messages
        assert state.run_name == "test_agent"
```

- [ ] **Step 8: Run test to verify it passes**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestLangChainCheckpointState -v`
Expected: PASS

- [ ] **Step 9: Write test for CustomCheckpointState**

```python
# Add to tests/test_checkpoint_restore.py

class TestCustomCheckpointState:
    def test_custom_checkpoint_state_defaults(self):
        """CustomCheckpointState should have framework preset."""
        from agent_debugger_sdk.checkpoints import CustomCheckpointState

        state = CustomCheckpointState()
        assert state.framework == "custom"
        assert state.data == {}

    def test_custom_checkpoint_state_with_data(self):
        """CustomCheckpointState should accept arbitrary data."""
        from agent_debugger_sdk.checkpoints import CustomCheckpointState

        state = CustomCheckpointState(
            label="custom_state",
            data={"step": 5, "payload": {"x": 1}},
        )
        assert state.data["step"] == 5
        assert state.data["payload"]["x"] == 1
```

- [ ] **Step 10: Run all schema tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py -v`
Expected: All PASS

- [ ] **Step 11: Commit schemas module**

```bash
git add agent_debugger_sdk/checkpoints/ tests/test_checkpoint_restore.py
git commit -m "$(cat <<'EOF'
feat: add checkpoint schemas module (L1)

Add typed checkpoint dataclasses for framework-specific restoration:
- BaseCheckpointState: common fields (framework, label, created_at)
- LangChainCheckpointState: messages, intermediate_steps, run metadata
- CustomCheckpointState: arbitrary user data

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Validation Helpers

**Files:**
- Create: `agent_debugger_sdk/checkpoints/validation.py`
- Modify: `agent_debugger_sdk/checkpoints/__init__.py`
- Test: `tests/test_checkpoint_restore.py`

- [ ] **Step 1: Write failing test for validate_checkpoint_state**

```python
# Add to tests/test_checkpoint_restore.py

class TestCheckpointValidation:
    def test_validate_dict_with_langchain_framework(self):
        """Should validate dict and return LangChainCheckpointState."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {
            "framework": "langchain",
            "label": "test",
            "messages": [{"role": "user", "content": "hi"}],
        }
        result = validate_checkpoint_state(state_dict)
        assert isinstance(result, object)
        assert result.framework == "langchain"
        assert result.label == "test"

    def test_validate_dict_with_unknown_framework_returns_custom(self):
        """Unknown framework should fall back to CustomCheckpointState."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {
            "framework": "unknown_framework",
            "label": "test",
            "data": {"foo": "bar"},
        }
        result = validate_checkpoint_state(state_dict)
        # Should preserve the unknown framework string
        assert result.framework == "unknown_framework"

    def test_validate_dict_without_framework_defaults_to_custom(self):
        """Missing framework should default to custom."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {"data": {"step": 1}}
        result = validate_checkpoint_state(state_dict)
        assert result.framework == "custom"

    def test_validate_dataclass_passthrough(self):
        """Already-typed state should pass through unchanged."""
        from agent_debugger_sdk.checkpoints import (
            LangChainCheckpointState,
            validate_checkpoint_state,
        )

        state = LangChainCheckpointState(label="test")
        result = validate_checkpoint_state(state)
        assert result is state

    def test_serialize_state_to_dict(self):
        """Should serialize dataclass to dict with extra fields preserved."""
        from agent_debugger_sdk.checkpoints import (
            LangChainCheckpointState,
            serialize_checkpoint_state,
        )

        state = LangChainCheckpointState(
            label="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        result = serialize_checkpoint_state(state)
        assert result["framework"] == "langchain"
        assert result["label"] == "test"
        assert result["messages"] == [{"role": "user", "content": "hi"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestCheckpointValidation -v`
Expected: FAIL with "cannot import name 'validate_checkpoint_state'"

- [ ] **Step 3: Create validation.py**

```python
# agent_debugger_sdk/checkpoints/validation.py
"""Validation and serialization helpers for checkpoint states."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .schemas import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
    SCHEMA_REGISTRY,
)


def validate_checkpoint_state(state: BaseCheckpointState | dict[str, Any]) -> BaseCheckpointState:
    """Validate and normalize checkpoint state.

    Args:
        state: Either a dataclass instance or a dict. If dict, validated
               against the appropriate schema based on framework field.

    Returns:
        A validated checkpoint state dataclass instance.

    - Dataclasses pass through unchanged
    - Dicts are converted to the appropriate schema class
    - Unknown frameworks fall back to CustomCheckpointState
    - Missing framework defaults to "custom"
    """
    if is_dataclass(state) and isinstance(state, BaseCheckpointState):
        return state

    if not isinstance(state, dict):
        raise TypeError(f"state must be dict or BaseCheckpointState, got {type(state)}")

    # Determine framework
    framework = state.get("framework", "custom")

    # Look up schema class, fall back to CustomCheckpointState
    schema_class = SCHEMA_REGISTRY.get(framework, CustomCheckpointState)

    # Extract known fields from schema
    if hasattr(schema_class, "__dataclass_fields__"):
        known_fields = set(schema_class.__dataclass_fields__.keys())
    else:
        known_fields = set()

    # Build kwargs for schema instantiation
    kwargs: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for key, value in state.items():
        if key in known_fields:
            kwargs[key] = value
        else:
            extra[key] = value

    # Store extra fields in _extra if schema supports it
    # (CustomCheckpointState uses 'data' for this)
    if extra and schema_class is CustomCheckpointState:
        existing_data = kwargs.get("data", {})
        kwargs["data"] = {**existing_data, **extra}
    elif extra:
        # For other schemas, preserve extra in metadata or similar
        kwargs["_extra"] = extra

    return schema_class(**kwargs)


def serialize_checkpoint_state(state: BaseCheckpointState) -> dict[str, Any]:
    """Serialize checkpoint state to dict for storage.

    Args:
        state: A checkpoint state dataclass instance.

    Returns:
        Dict representation suitable for JSON serialization.
    """
    if is_dataclass(state):
        result = asdict(state)
    elif isinstance(state, dict):
        result = dict(state)
    else:
        raise TypeError(f"state must be dataclass or dict, got {type(state)}")

    return result
```

- [ ] **Step 4: Update __init__.py to export validation functions**

```python
# agent_debugger_sdk/checkpoints/__init__.py
"""Checkpoint schemas for execution restoration."""

from .schemas import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
    SCHEMA_REGISTRY,
)
from .validation import serialize_checkpoint_state, validate_checkpoint_state

__all__ = [
    "BaseCheckpointState",
    "CustomCheckpointState",
    "LangChainCheckpointState",
    "SCHEMA_REGISTRY",
    "validate_checkpoint_state",
    "serialize_checkpoint_state",
]
```

- [ ] **Step 5: Run validation tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestCheckpointValidation -v`
Expected: All PASS

- [ ] **Step 6: Commit validation module**

```bash
git add agent_debugger_sdk/checkpoints/ tests/test_checkpoint_restore.py
git commit -m "$(cat <<'EOF'
feat: add checkpoint validation helpers

Add validate_checkpoint_state() for dict-to-schema conversion and
serialize_checkpoint_state() for dataclass-to-dict serialization.
Unknown frameworks fall back to CustomCheckpointState.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Restore Support to TraceContext

**Files:**
- Modify: `agent_debugger_sdk/core/context.py` (lines 114-187 for __init__, add restore after)
- Modify: `agent_debugger_sdk/__init__.py`
- Test: `tests/test_checkpoint_restore.py`

- [ ] **Step 1: Write failing test for TraceContext.restore()**

```python
# Add to tests/test_checkpoint_restore.py

import asyncio


class TestTraceContextRestore:
    def test_restore_classmethod_exists(self):
        """TraceContext.restore should be a classmethod."""
        from agent_debugger_sdk import TraceContext

        assert hasattr(TraceContext, "restore")
        assert callable(getattr(TraceContext, "restore"))

    @pytest.mark.asyncio
    async def test_restore_creates_context_with_restored_state(self):
        """TraceContext.restore should create context with restored state."""
        from unittest.mock import AsyncMock, patch

        from agent_debugger_sdk import TraceContext
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        # Mock the HTTP call to fetch checkpoint
        mock_checkpoint_data = {
            "id": "cp-test-123",
            "session_id": "sess-original",
            "event_id": "evt-1",
            "sequence": 1,
            "state": {
                "framework": "langchain",
                "label": "test_checkpoint",
                "messages": [{"role": "user", "content": "hello"}],
            },
            "memory": {},
            "timestamp": "2026-03-24T12:00:00Z",
            "importance": 0.9,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_checkpoint_data
            mock_response.raise_for_status = lambda: None
            mock_get.return_value.__aenter__.return_value = mock_response

            ctx = await TraceContext.restore(
                checkpoint_id="cp-test-123",
                server_url="http://localhost:8000",
            )

            assert ctx is not None
            assert ctx.restored_state is not None
            assert ctx.restored_state.framework == "langchain"

    @pytest.mark.asyncio
    async def test_restored_context_can_be_used_as_context_manager(self):
        """Restored context should work as async context manager."""
        from unittest.mock import AsyncMock, patch

        from agent_debugger_sdk import TraceContext

        mock_checkpoint_data = {
            "id": "cp-test-456",
            "session_id": "sess-original",
            "event_id": "evt-1",
            "sequence": 1,
            "state": {"framework": "custom", "data": {"step": 5}},
            "memory": {},
            "timestamp": "2026-03-24T12:00:00Z",
            "importance": 0.5,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_checkpoint_data
            mock_response.raise_for_status = lambda: None
            mock_get.return_value.__aenter__.return_value = mock_response

            async with await TraceContext.restore(
                checkpoint_id="cp-test-456",
                server_url="http://localhost:8000",
            ) as ctx:
                # Should have new session ID
                assert ctx.session_id != "sess-original"
                # Should reference original in metadata
                assert ctx.session.metadata.get("restored_from_checkpoint") == "cp-test-456"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestTraceContextRestore -v`
Expected: FAIL with "'TraceContext' object has no attribute 'restore'"

- [ ] **Step 3: Add restore classmethod to TraceContext**

Add after line 186 in `agent_debugger_sdk/core/context.py`:

```python
    # Add after _session_start_event declaration (around line 186)

    _restored_state: BaseCheckpointState | None = None
    """The checkpoint state this context was restored from, if any."""

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
            checkpoint_id: ID of checkpoint to restore from.
            session_id: Optional session ID for restored session (new if None).
            server_url: Server URL (uses default if None).
            label: Label for the restored session.

        Returns:
            TraceContext with restored state accessible via ctx.restored_state

        Example:
            async with await TraceContext.restore("cp-abc123") as ctx:
                state = ctx.restored_state  # LangChainCheckpointState
                messages = state.messages   # Pre-populated history
        """
        import httpx

        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        # Resolve server URL
        if server_url is None:
            from agent_debugger_sdk.config import get_config
            config = get_config()
            server_url = config.endpoint or "http://localhost:8000"

        # Fetch checkpoint from server
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server_url}/api/checkpoints/{checkpoint_id}")
            response.raise_for_status()
            checkpoint_data = response.json()

        # Validate state
        state_dict = checkpoint_data.get("state", {})
        original_session_id = checkpoint_data.get("session_id", "")

        # Create new context
        new_session_id = session_id or str(uuid.uuid4())
        ctx = cls(
            session_id=new_session_id,
            agent_name=label or f"restored from {checkpoint_id[:8]}",
            framework=state_dict.get("framework", "custom"),
        )

        # Store restored state
        ctx._restored_state = validate_checkpoint_state(state_dict)

        # Link to original in metadata
        ctx.session.metadata = {
            "restored_from_checkpoint": checkpoint_id,
            "original_session_id": original_session_id,
        }

        return ctx

    @property
    def restored_state(self) -> BaseCheckpointState | None:
        """The checkpoint state this context was restored from, if any."""
        return self._restored_state
```

- [ ] **Step 4: Add imports at top of context.py**

Add to imports in `agent_debugger_sdk/core/context.py`:

```python
# Add to imports (around line 17)
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState
```

- [ ] **Step 5: Update __init__.py to export checkpoint classes**

Add to `agent_debugger_sdk/__init__.py`:

```python
# Add imports (around line 27)
from agent_debugger_sdk.checkpoints import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
)

# Add to __all__ list
    # Checkpoints
    "BaseCheckpointState",
    "CustomCheckpointState",
    "LangChainCheckpointState",
```

- [ ] **Step 6: Run restore tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestTraceContextRestore -v`
Expected: All PASS

- [ ] **Step 7: Commit TraceContext.restore()**

```bash
git add agent_debugger_sdk/core/context.py agent_debugger_sdk/__init__.py tests/test_checkpoint_restore.py
git commit -m "$(cat <<'EOF'
feat: add TraceContext.restore() for checkpoint restoration (L2)

Add classmethod to restore execution from a checkpoint:
- Fetches checkpoint state from server
- Creates new TraceContext with restored state
- Links to original session in metadata
- Exposes restored_state property

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add REST API Endpoints

**Files:**
- Modify: `api/replay_routes.py`
- Modify: `api/schemas.py`
- Test: `tests/test_checkpoint_restore.py`

- [ ] **Step 1: Write failing test for GET /api/checkpoints/{id}**

```python
# Add to tests/test_checkpoint_restore.py

import httpx


class TestCheckpointEndpoints:
    @pytest.mark.asyncio
    async def test_get_checkpoint_endpoint(self):
        """GET /api/checkpoints/{id} should return checkpoint data."""
        # This requires a running server or test client
        # Using the test client from existing test patterns
        pass  # Will test via integration test

    @pytest.mark.asyncio
    async def test_restore_checkpoint_endpoint(self):
        """POST /api/checkpoints/{id}/restore should create new session."""
        pass  # Will test via integration test
```

- [ ] **Step 2: Add schemas to api/schemas.py**

Add to `api/schemas.py`:

```python
# Add after CheckpointListResponse (around line 49)

class CheckpointResponse(BaseModel):
    """Response for single checkpoint GET."""
    id: str
    session_id: str
    event_id: str
    sequence: int
    state: dict[str, Any]
    memory: dict[str, Any]
    timestamp: str
    importance: float


class RestoreRequest(BaseModel):
    """Request body for checkpoint restore."""
    session_id: str | None = None
    label: str = ""


class RestoreResponse(BaseModel):
    """Response for checkpoint restore."""
    checkpoint_id: str
    original_session_id: str
    new_session_id: str
    restored_at: str
    state: dict[str, Any]
    restore_token: str
```

- [ ] **Step 3: Add endpoints to api/replay_routes.py**

Add to `api/replay_routes.py`:

```python
# Add imports at top
from datetime import datetime, timezone
import uuid

from api.schemas import CheckpointResponse, RestoreRequest, RestoreResponse

# Add endpoints after existing routes (around line 65)

@router.get("/api/checkpoints/{checkpoint_id}", response_model=CheckpointResponse)
async def get_checkpoint(
    checkpoint_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> CheckpointResponse:
    """Get a single checkpoint by ID."""
    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    return CheckpointResponse(
        id=checkpoint.id,
        session_id=checkpoint.session_id,
        event_id=checkpoint.event_id,
        sequence=checkpoint.sequence,
        state=checkpoint.state,
        memory=checkpoint.memory,
        timestamp=checkpoint.timestamp.isoformat() if checkpoint.timestamp else "",
        importance=checkpoint.importance,
    )


@router.post("/api/checkpoints/{checkpoint_id}/restore", response_model=RestoreResponse)
async def restore_checkpoint(
    checkpoint_id: str,
    request: RestoreRequest,
    repo: TraceRepository = Depends(get_repository),
) -> RestoreResponse:
    """Restore execution from a checkpoint.

    Creates a new session pre-populated with checkpoint state.
    The new session references the original in metadata.
    """
    # Fetch checkpoint
    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    # Generate new session ID
    new_session_id = request.session_id or str(uuid.uuid4())
    restore_token = str(uuid.uuid4())
    restored_at = datetime.now(timezone.utc).isoformat()

    # Create new session with metadata linking to original
    await repo.create_session(
        session_id=new_session_id,
        agent_name=request.label or f"restored from {checkpoint_id[:8]}",
        framework=checkpoint.state.get("framework", "custom"),
        config={
            "restored_from_checkpoint": checkpoint_id,
            "original_session_id": checkpoint.session_id,
            "restore_token": restore_token,
        },
    )

    return RestoreResponse(
        checkpoint_id=checkpoint_id,
        original_session_id=checkpoint.session_id,
        new_session_id=new_session_id,
        restored_at=restored_at,
        state=checkpoint.state,
        restore_token=restore_token,
    )
```

- [ ] **Step 4: Run API tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -c "from api.replay_routes import get_checkpoint, restore_checkpoint; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit REST API endpoints**

```bash
git add api/replay_routes.py api/schemas.py tests/test_checkpoint_restore.py
git commit -m "$(cat <<'EOF'
feat: add checkpoint GET and restore REST endpoints

- GET /api/checkpoints/{id}: fetch checkpoint by ID
- POST /api/checkpoints/{id}/restore: create new session from checkpoint

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Validation to create_checkpoint()

**Files:**
- Modify: `agent_debugger_sdk/core/context.py` (create_checkpoint method)
- Test: `tests/test_checkpoint_restore.py`

- [ ] **Step 1: Write test for validated create_checkpoint()**

```python
# Add to tests/test_checkpoint_restore.py

class TestCreateCheckpointValidation:
    @pytest.mark.asyncio
    async def test_create_checkpoint_with_dataclass_state(self):
        """create_checkpoint should accept typed state dataclass."""
        from agent_debugger_sdk import TraceContext
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        async with TraceContext(agent_name="test") as ctx:
            state = LangChainCheckpointState(
                label="test_state",
                messages=[{"role": "user", "content": "hi"}],
            )
            checkpoint_id = await ctx.create_checkpoint(state, importance=0.9)
            assert checkpoint_id is not None

    @pytest.mark.asyncio
    async def test_create_checkpoint_with_dict_state(self):
        """create_checkpoint should accept dict and validate it."""
        from agent_debugger_sdk import TraceContext

        async with TraceContext(agent_name="test") as ctx:
            state_dict = {
                "framework": "langchain",
                "label": "test_state",
                "messages": [{"role": "user", "content": "hi"}],
            }
            checkpoint_id = await ctx.create_checkpoint(state_dict, importance=0.9)
            assert checkpoint_id is not None
```

- [ ] **Step 2: Modify create_checkpoint to validate state**

Update `create_checkpoint` method in `agent_debugger_sdk/core/context.py`:

```python
# Replace existing create_checkpoint method (around line 725)

    async def create_checkpoint(
        self,
        state: dict[str, Any] | BaseCheckpointState,
        memory: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> str:
        """Create a checkpoint for time-travel debugging.

        Checkpoints capture the complete state of an agent at a specific
        point in execution, enabling state restoration and analysis.

        Args:
            state: The agent's state at this point. Can be a dict or a
                   BaseCheckpointState dataclass. Dicts are validated
                   against the appropriate schema based on framework field.
            memory: Optional memory/context snapshot at this point.
            importance: Relative importance score (0.0-1.0) for selective replay.

        Returns:
            The checkpoint ID.

        Raises:
            TypeError: If state is neither dict nor BaseCheckpointState.

        Example:
            from agent_debugger_sdk.checkpoints import LangChainCheckpointState

            state = LangChainCheckpointState(
                label="after_tool_call",
                messages=[{"role": "user", "content": "..."}],
                intermediate_steps=[{"tool": "search", "result": "..."}],
            )
            checkpoint_id = await ctx.create_checkpoint(state, importance=0.9)
        """
        self._check_entered()

        # Import validation helper (deferred to avoid circular imports)
        from agent_debugger_sdk.checkpoints import (
            serialize_checkpoint_state,
            validate_checkpoint_state,
        )

        # Validate and serialize state
        validated_state = validate_checkpoint_state(state)
        state_dict = serialize_checkpoint_state(validated_state)

        self._checkpoint_sequence += 1
        checkpoint_id = str(uuid.uuid4())

        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=self.session_id,
            event_id=_current_parent_id.get() or "",
            sequence=self._checkpoint_sequence,
            state=state_dict,
            memory=memory or {},
            timestamp=datetime.now(timezone.utc),
            importance=max(0.0, min(1.0, importance)),
        )

        async with self._events_lock:
            self._events.append(checkpoint)
        if self._checkpoint_persister is not None:
            await self._checkpoint_persister(checkpoint)

        event = TraceEvent(
            id=str(uuid.uuid4()),
            session_id=self.session_id,
            parent_id=_current_parent_id.get(),
            event_type=EventType.CHECKPOINT,
            name=f"checkpoint_{self._checkpoint_sequence}",
            data={
                "checkpoint_id": checkpoint_id,
                "sequence": self._checkpoint_sequence,
            },
            importance=checkpoint.importance,
        )
        await self._emit_event(event)

        return checkpoint_id
```

- [ ] **Step 3: Run validation tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py::TestCreateCheckpointValidation -v`
Expected: All PASS

- [ ] **Step 4: Commit create_checkpoint validation**

```bash
git add agent_debugger_sdk/core/context.py tests/test_checkpoint_restore.py
git commit -m "$(cat <<'EOF'
feat: add state validation to create_checkpoint()

validate state against schema before persisting, support both
dict and BaseCheckpointState dataclass inputs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Run Full Test Suite and Final Commit

- [ ] **Step 1: Run all checkpoint restore tests**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/test_checkpoint_restore.py -v`
Expected: All PASS

- [ ] **Step 2: Run full test suite to catch regressions**

Run: `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: No new failures

- [ ] **Step 3: Push all commits**

```bash
git push origin main
```

---

## Summary

**Completed:**
- L1: Standardized checkpoint schemas (BaseCheckpointState, LangChainCheckpointState, CustomCheckpointState)
- L1: Validation helpers (validate_checkpoint_state, serialize_checkpoint_state)
- L2: TraceContext.restore() classmethod for manual restoration
- L2: REST API endpoints (GET /api/checkpoints/{id}, POST /api/checkpoints/{id}/restore)

**Files Created:**
- `agent_debugger_sdk/checkpoints/__init__.py`
- `agent_debugger_sdk/checkpoints/schemas.py`
- `agent_debugger_sdk/checkpoints/validation.py`
- `tests/test_checkpoint_restore.py`

**Files Modified:**
- `agent_debugger_sdk/core/context.py`
- `agent_debugger_sdk/__init__.py`
- `api/replay_routes.py`
- `api/schemas.py`
