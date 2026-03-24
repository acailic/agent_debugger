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
