"""Decorators for instrumenting agent code with trace collection.

This package provides decorators that wrap agent functions, tool calls,
and LLM interactions to automatically collect execution traces.

Example:
    from agent_debugger_sdk import trace_agent, trace_tool, trace_llm

    @trace_agent(name="my_agent", framework="pydantic_ai")
    async def my_agent(prompt: str) -> str:
        result = await call_llm([{"role": "user", "content": prompt}])
        return result

    @trace_tool(name="search_web")
    async def search_web(query: str) -> list[str]:
        return ["result1", "result2"]

    @trace_llm(model="gpt-4o")
    async def call_llm(messages: list) -> str:
        return "Hello!"
"""

from .agent import trace_agent
from .llm import trace_llm
from .tool import trace_tool

# Internal utilities (exported for testing)
from ._utils import (
    _sanitize_arguments,
    _truncate_value,
    _sanitize_result,
)
from .llm import (
    _extract_messages,
    _extract_tools,
    _extract_settings,
    _extract_llm_response,
)

__all__ = [
    "trace_agent",
    "trace_tool",
    "trace_llm",
    # internal utilities (exported for testing)
    "_sanitize_arguments",
    "_truncate_value",
    "_sanitize_result",
    "_extract_messages",
    "_extract_tools",
    "_extract_settings",
    "_extract_llm_response",
]
