"""PydanticAI adapter for agent execution tracing.

This module provides the PydanticAIAdapter class that wraps PydanticAI agents
and captures execution traces for debugging and visualization.

PydanticAI has built-in OpenTelemetry instrumentation. This adapter hooks into
that system to capture events and forward them to our trace collector.

This module re-exports from the pydantic_ai package for backward compatibility.
"""

# Re-export from the pydantic_ai package
from agent_debugger_sdk.adapters.pydantic_ai import (
    PYDANTIC_AI_AVAILABLE,
    Agent,
    AgentRunResult,
    Model,
    PydanticAIAdapter,
    PydanticAIInstrumentor,
    _pydantic_run_context,
)

__all__ = [
    "PydanticAIAdapter",
    "PydanticAIInstrumentor",
    "PYDANTIC_AI_AVAILABLE",
    "_pydantic_run_context",
    "Agent",
    "AgentRunResult",
    "Model",
]
