"""PydanticAI adapter for agent execution tracing.

This package provides the PydanticAIAdapter class that wraps PydanticAI agents
and captures execution traces for debugging and visualization.

PydanticAI has built-in OpenTelemetry instrumentation. This adapter hooks into
that system to capture events and forward them to our trace collector.

Example:
    >>> from pydantic_ai import Agent
    >>> from agent_debugger_sdk.adapters import PydanticAIAdapter
    >>>
    >>> agent = Agent('openai:gpt-4o')
    >>> adapter = PydanticAIAdapter(agent)
    >>>
    >>> async with adapter.trace_session(agent_name="my_agent") as session_id:
    ...     result = await agent.run("Hello")
"""

# Import main classes for backward compatibility
from .adapter import (
    PydanticAIAdapter,
    PYDANTIC_AI_AVAILABLE,
    _pydantic_run_context,
)

# Import types for backward compatibility with tests
try:
    from pydantic_ai import Agent, AgentRunResult
    from pydantic_ai.models import Model
except ImportError:
    Agent = object  # type: ignore
    AgentRunResult = object  # type: ignore
    Model = object  # type: ignore

from .instrumentor import PydanticAIInstrumentor

# Re-export at package level
__all__ = [
    "PydanticAIAdapter",
    "PydanticAIInstrumentor",
    "PYDANTIC_AI_AVAILABLE",
    "_pydantic_run_context",
    "Agent",
    "AgentRunResult",
    "Model",
]
