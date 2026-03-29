"""Decorators for instrumenting agent code with trace collection.

This module provides decorators that wrap agent functions, tool calls,
and LLM interactions to automatically collect execution traces.

This module re-exports from the decorators package for backward compatibility.

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

# Re-export from the decorators package
from agent_debugger_sdk.core.decorators._utils import (
    _sanitize_arguments,
    _sanitize_result,
    _truncate_value,
)
from agent_debugger_sdk.core.decorators.agent import trace_agent
from agent_debugger_sdk.core.decorators.llm import (
    _extract_llm_response,
    _extract_messages,
    _extract_settings,
    _extract_tools,
    trace_llm,
)
from agent_debugger_sdk.core.decorators.tool import trace_tool

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
