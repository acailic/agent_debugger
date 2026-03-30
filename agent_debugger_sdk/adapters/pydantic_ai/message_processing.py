"""Message processing utilities for PydanticAI adapter.

This module contains logic for processing PydanticAI messages and converting them
into trace events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

from .utils import request_messages_from_parts, usage_from_message
from .utils import response_duration_ms as calc_duration_ms

try:
    from pydantic_ai.messages import (
        ModelMessage,
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
    )
    from pydantic_ai.models import Model

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False
    ModelMessage = Any
    ModelRequest = Any
    ModelResponse = Any
    ToolReturnPart = Any
    ToolCallPart = Any
    TextPart = Any
    Model = Any


class MessageProcessor:
    """Handles conversion of PydanticAI messages to trace events."""

    def __init__(
        self,
        session_id: str,
        context: Any,
    ):
        """Initialize the message processor.

        Args:
            session_id: The current session ID.
            context: The TraceContext instance for emitting events.
        """
        self.session_id = session_id
        self._context = context
        self._agent = None

    async def process_messages(
        self,
        messages: list[ModelMessage],
        *,
        requested_model: Model | str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Process and emit events for a list of messages.

        Args:
            messages: List of ModelMessage objects from the run.
            requested_model: The model that was requested.
            duration_ms: Total run duration for the final response.
        """
        if not self._context:
            return

        resolved_model = self._resolve_model_name(requested_model)
        tool_call_parent_ids: dict[str, str] = {}
        prior_request_timestamp: datetime | None = None

        for index, msg in enumerate(messages):
            if isinstance(msg, ModelRequest):
                prior_request_timestamp = msg.timestamp
            response_parent_id = await self._emit_message_event(
                msg,
                model_name=resolved_model,
                response_duration_ms=(duration_ms if index == len(messages) - 1 else 0.0),
                request_timestamp=prior_request_timestamp,
                tool_call_parent_ids=tool_call_parent_ids,
            )
            if isinstance(msg, ModelResponse) and response_parent_id:
                prior_request_timestamp = None

    async def _emit_message_event(
        self,
        message: ModelMessage,
        *,
        model_name: str,
        response_duration_ms: float = 0.0,
        request_timestamp: datetime | None = None,
        tool_call_parent_ids: dict[str, str] | None = None,
    ) -> str | None:
        """Emit appropriate events for a message.

        Args:
            message: A ModelMessage from the conversation.
            model_name: Name of the model being used.
            response_duration_ms: Duration for the final response.
            request_timestamp: When the request was made.
            tool_call_parent_ids: Mapping of tool call IDs to parent event IDs.

        Returns:
            The ID of the emitted event, if any.
        """
        if not self._context:
            return None

        if isinstance(message, ModelRequest):
            return await self._emit_request_event(message, model_name, tool_call_parent_ids)

        if not isinstance(message, ModelResponse):
            return None

        return await self._emit_response_event(
            message,
            model_name,
            response_duration_ms,
            request_timestamp,
            tool_call_parent_ids,
        )

    async def _emit_request_event(
        self,
        message: ModelRequest,
        model_name: str,
        tool_call_parent_ids: dict[str, str] | None,
    ) -> str:
        """Emit a request event.

        Args:
            message: The ModelRequest message.
            model_name: Name of the model.
            tool_call_parent_ids: Mapping of tool call IDs to parent event IDs.

        Returns:
            The event ID.
        """
        request_event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=model_name,
            messages=request_messages_from_parts(message.parts),
            tools=[],
            settings={},
            name=f"llm_request_{model_name}",
            importance=0.3,
        )
        await self._context._emit_event(request_event)

        if tool_call_parent_ids is not None:
            for part in message.parts:
                if isinstance(part, ToolReturnPart):
                    await self._context.record_tool_result(
                        tool_name=part.tool_name,
                        result=part.content,
                        error=part.model_response_str() if part.outcome != "success" else None,
                        parent_id=tool_call_parent_ids.get(part.tool_call_id),
                    )
        return request_event.id

    async def _emit_response_event(
        self,
        message: ModelResponse,
        model_name: str,
        response_duration_ms: float,
        request_timestamp: datetime | None,
        tool_call_parent_ids: dict[str, str] | None,
    ) -> str:
        """Emit a response event.

        Args:
            message: The ModelResponse message.
            model_name: Name of the model.
            response_duration_ms: Duration of the response.
            request_timestamp: When the request was made.
            tool_call_parent_ids: Mapping of tool call IDs to parent event IDs.

        Returns:
            The event ID.
        """
        tool_calls = [
            {
                "id": part.tool_call_id,
                "name": part.tool_name,
                "arguments": part.args_as_dict(),
            }
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        response_model = message.model_name or model_name
        response_event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=self._context.get_current_parent(),
            model=response_model,
            content="".join(part.content for part in message.parts if isinstance(part, TextPart)),
            tool_calls=tool_calls,
            usage=usage_from_message(message),
            duration_ms=calc_duration_ms(
                request_timestamp=request_timestamp,
                response_timestamp=message.timestamp,
                fallback_ms=response_duration_ms,
            ),
            name=f"llm_response_{response_model}",
            importance=0.5,
        )
        await self._context._emit_event(response_event)

        if tool_call_parent_ids is not None:
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    tool_call_event = ToolCallEvent(
                        session_id=self.session_id,
                        parent_id=response_event.id,
                        tool_name=part.tool_name,
                        arguments=part.args_as_dict(),
                        name=f"tool_call_{part.tool_name}",
                        importance=0.4,
                    )
                    await self._context._emit_event(tool_call_event)
                    tool_call_parent_ids[part.tool_call_id] = tool_call_event.id

        return response_event.id

    def _resolve_model_name(self, requested_model: Model | str | None) -> str:
        """Resolve the model name using the agent if available."""
        from .utils import resolve_model_name

        if self._agent:
            return resolve_model_name(self._agent, requested_model)

        # Fallback to basic resolution without agent
        if isinstance(requested_model, str):
            return requested_model
        if requested_model is not None:
            name = getattr(requested_model, "model_name", None) or getattr(requested_model, "name", None)
            if name:
                return str(name)
        return "unknown"
