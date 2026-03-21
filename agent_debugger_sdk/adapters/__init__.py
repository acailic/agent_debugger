"""Framework adapters for agent tracing.

This module provides adapters for popular agent frameworks to enable
automatic instrumentation with the Agent Debugger SDK.
"""

from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIAdapter

__all__ = [
    "PydanticAIAdapter",
    "LangChainTracingHandler",
]
