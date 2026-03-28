"""LangChain adapter for agent execution tracing.

This package provides the LangChainTracingHandler callback handler and
LangChainAdapter class that hook into LangChain's callback system to
capture execution traces for debugging and visualization.

Example:
    >>> from langchain_openai import ChatOpenAI
    >>> from agent_debugger_sdk.adapters import LangChainTracingHandler
    >>>
    >>> handler = LangChainTracingHandler(session_id="my-session")
    >>> llm = ChatOpenAI(callbacks=[handler])
    >>> await llm.ainvoke("Hello")
"""

# Import main classes for backward compatibility
from .adapter import LangChainAdapter
from .auto_patch import register_auto_patch
from .handler import LANGCHAIN_AVAILABLE, LangChainTracingHandler

# Import types for backward compatibility with tests
try:
    from langchain_core.callbacks import AsyncCallbackHandler
    from langchain_core.outputs import LLMResult
except ImportError:
    AsyncCallbackHandler = object  # type: ignore
    LLMResult = object  # type: ignore

# Re-export at package level
__all__ = [
    "LangChainTracingHandler",
    "LangChainAdapter",
    "register_auto_patch",
    "LANGCHAIN_AVAILABLE",
    "AsyncCallbackHandler",
    "LLMResult",
]
