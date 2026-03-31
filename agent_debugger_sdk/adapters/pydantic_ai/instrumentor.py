"""Low-level instrumentor for PydanticAI.

This module provides the PydanticAIInstrumentor class for finer-grained
instrumentation by hooking into PydanticAI's internal event system.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

# Use perf_counter for more accurate duration tracking
_perf_counter = time.perf_counter


class PydanticAIInstrumentor:
    """Low-level instrumentor for PydanticAI using OpenTelemetry hooks.

    This provides finer-grained instrumentation by hooking into PydanticAI's
    internal event system. Use this if you need more control over event capture.

    Example:
        >>> from agent_debugger_sdk.core.context import TraceContext
        >>> from agent_debugger_sdk.adapters.pydantic_ai import PydanticAIInstrumentor
        >>>
        >>> async with TraceContext(session_id="...", ...) as ctx:
        ...     instrumentor = PydanticAIInstrumentor(session_id="...")
        ...     instrumentor.set_context(ctx)
        ...     # Use instrumentor.on_model_request, etc.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize the instrumentor.

        Args:
            session_id: The session ID to associate events with.
        """
        self.session_id = session_id
        self._start_times: dict[str, float] = {}
        self._context: TraceContext | None = None

    def set_context(self, context: TraceContext) -> None:
        """Set the trace context.

        Args:
            context: The TraceContext to use for event emission.
        """
        self._context = context

    async def on_model_request(self, data: dict[str, Any]) -> None:
        """Handle model request event.

        Args:
            data: Event data containing model, messages, etc.
        """
        if not self._context:
            return

        request_id = data.get("request_id", str(uuid.uuid4()))
        self._start_times[request_id] = _perf_counter()

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=data.get("model", "unknown"),
            messages=data.get("messages", []),
            tools=data.get("tools", []),
            settings=data.get("settings", {}),
            name=f"llm_request_{data.get('model', 'unknown')}",
            importance=0.3,
        )

        await self._context._emit_event(event)

    async def on_model_response(self, data: dict[str, Any]) -> None:
        """Handle model response event.

        Args:
            data: Event data containing response, usage, etc.
        """
        if not self._context:
            return

        request_id = data.get("request_id", "")
        start_time = self._start_times.pop(request_id, _perf_counter())
        duration_ms = (_perf_counter() - start_time) * 1000

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=data.get("model", "unknown"),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls", []),
            usage=data.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            cost_usd=data.get("cost_usd", 0.0),
            duration_ms=duration_ms,
            name=f"llm_response_{data.get('model', 'unknown')}",
            importance=0.5,
        )

        await self._context._emit_event(event)

    async def on_tool_call(self, data: dict[str, Any]) -> None:
        """Handle tool call event.

        Args:
            data: Event data containing tool name and arguments.
        """
        if not self._context:
            return

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            tool_name=data.get("tool_name", "unknown"),
            arguments=data.get("arguments", {}),
            name=f"tool_call_{data.get('tool_name', 'unknown')}",
            importance=0.4,
        )

        await self._context._emit_event(event)

    async def on_tool_result(self, data: dict[str, Any]) -> None:
        """Handle tool result event.

        Args:
            data: Event data containing tool name and result.
        """
        if not self._context:
            return

        await self._context.record_tool_result(
            tool_name=data.get("tool_name", "unknown"),
            result=data.get("result"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
        )
