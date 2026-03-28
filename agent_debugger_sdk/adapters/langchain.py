"""LangChain adapter for agent execution tracing.

This module provides the LangChainTracingHandler callback handler that hooks
into LangChain's callback system to capture execution traces for debugging
and visualization.

This module re-exports from the langchain package for backward compatibility.
"""

# Re-export from the langchain package
from agent_debugger_sdk.adapters.langchain import (
    AsyncCallbackHandler,
    LANGCHAIN_AVAILABLE,
    LLMResult,
    LangChainAdapter,
    LangChainTracingHandler,
    register_auto_patch,
)

__all__ = [
    "LangChainTracingHandler",
    "LangChainAdapter",
    "register_auto_patch",
    "LANGCHAIN_AVAILABLE",
    "AsyncCallbackHandler",
    "LLMResult",
]
