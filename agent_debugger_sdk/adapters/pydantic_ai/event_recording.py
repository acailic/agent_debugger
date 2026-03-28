"""Event recording helpers for PydanticAI adapter.

This module provides methods for manually recording trace events.
"""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent


class EventRecorder:
    """Helper class for recording trace events.

    This class provides methods for recording LLM requests, responses,
    and tool calls with proper context tracking.
    """

    def __init__(
        self,
        session_id: str,
        context: Any,
    ):
        """Initialize the event recorder.

        Args:
            session_id: The current session ID.
            context: The TraceContext instance for emitting events.
        """
        self.session_id = session_id
        self._context = context

    async def record_llm_request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> str:
        """Record an LLM request event.

        Args:
            model: The model identifier.
            messages: The messages being sent to the LLM.
            tools: Available tools for the LLM.
            settings: Model settings (temperature, etc.).

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=model,
            messages=messages,
            tools=tools or [],
            settings=settings or {},
            name=f"llm_request_{model}",
            importance=0.3,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_llm_response(
        self,
        model: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float = 0.0,
        duration_ms: float = 0.0,
    ) -> str:
        """Record an LLM response event.

        Args:
            model: The model that generated the response.
            content: The text content of the response.
            tool_calls: Tool calls requested by the LLM.
            usage: Token usage statistics.
            cost_usd: Estimated cost in USD.
            duration_ms: Duration of the API call.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=model,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage or {"input_tokens": 0, "output_tokens": 0},
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            name=f"llm_response_{model}",
            importance=0.5,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Record a tool call event.

        Args:
            tool_name: Name of the tool being called.
            arguments: Arguments passed to the tool.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            tool_name=tool_name,
            arguments=arguments,
            name=f"tool_call_{tool_name}",
            importance=0.4,
        )

        await self._context._emit_event(event)

        return event.id

    async def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> str:
        """Record a tool result event.

        Args:
            tool_name: Name of the tool that was called.
            result: The return value from the tool.
            error: Error message if the call failed.
            duration_ms: Execution time in milliseconds.

        Returns:
            The event ID.
        """
        if not self._context:
            return ""

        return await self._context.record_tool_result(
            tool_name=tool_name,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )
