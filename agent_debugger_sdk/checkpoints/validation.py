"""Validation and serialization helpers for checkpoint states."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .schemas import (
    BaseCheckpointState,
    CustomCheckpointState,
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

    # Store extra fields in the appropriate container
    # (CustomCheckpointState uses 'data', others use 'metadata')
    if extra:
        if schema_class is CustomCheckpointState:
            # CustomCheckpointState has a 'data' field for arbitrary fields
            existing_data = kwargs.get("data", {})
            kwargs["data"] = {**existing_data, **extra}
        elif "metadata" in known_fields:
            # Known schemas like LangChainCheckpointState have a 'metadata' field
            existing_metadata = kwargs.get("metadata", {})
            kwargs["metadata"] = {**existing_metadata, "_extra": extra}

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
