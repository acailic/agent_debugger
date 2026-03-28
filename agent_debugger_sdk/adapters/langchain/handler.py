"""LangChain callback handler for agent execution tracing.

This module provides the LangChainTracingHandler callback handler that hooks
into LangChain's callback system to capture execution traces for debugging
and visualization.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent_debugger_sdk.adapters.langchain_utils import (
    extract_invocation_settings,
    extract_response_content_and_tool_calls,
    normalize_tool_calls,
)
from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import EventType, LLMRequestEvent, LLMResponseEvent, ToolCallEvent, TraceEvent

logger = logging.getLogger("agent_debugger")

try:
    from langchain_core.callbacks import AsyncCallbackHandler
    from langchain_core.outputs import LLMResult

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    AsyncCallbackHandler = object
    LLMResult = Any


# Private aliases for backward compatibility
_normalize_tool_calls = normalize_tool_calls
_extract_response_content_and_tool_calls = extract_response_content_and_tool_calls
_extract_invocation_settings = extract_invocation_settings


class LangChainTracingHandler(AsyncCallbackHandler):
    """Async callback handler for LangChain tracing.

    Hooks into LangChain's callback system to capture:
    - LLM requests and responses
    - Tool calls and results
    - Chain executions
    - Agent actions

    Example:
        >>> from langchain_openai import ChatOpenAI
        >>> from agent_debugger_sdk.adapters import LangChainTracingHandler
        >>>
        >>> handler = LangChainTracingHandler(session_id="my-session")
        >>> llm = ChatOpenAI(callbacks=[handler])
        >>> await llm.ainvoke("Hello")
    """

    def __init__(
        self,
        session_id: str,
        agent_name: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Initialize the tracing handler.

        Args:
            session_id: Unique identifier for this tracing session.
            agent_name: Human-readable name for the agent.
            tags: Optional tags for categorizing this session.
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain is not installed. Install it with: pip install langchain-core")

        super().__init__()
        self.session_id = session_id
        self.agent_name = agent_name
        self.tags = tags or []
        self._context: TraceContext | None = None
        self._run_map: dict[str, str] = {}
        self._start_times: dict[str, float] = {}

    def set_context(self, context: TraceContext) -> None:
        """Set the trace context for event emission.

        Args:
            context: The TraceContext to use for event emission.
        """
        self._context = context

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM start event.

        Args:
            serialized: Serialized LLM configuration.
            prompts: Input prompts for the LLM.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            metadata: Additional metadata.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            self._start_times[run_id_str] = time.time()

            invocation_params = kwargs.get("invocation_params", {})
            model = invocation_params.get("model", invocation_params.get("model_name", "unknown"))

            messages = [{"role": "user", "content": prompt} for prompt in prompts]

            event = LLMRequestEvent(
                session_id=self.session_id,
                parent_id=self._run_map.get(str(parent_run_id)) if parent_run_id else None,
                model=model,
                messages=messages,
                tools=kwargs.get("tools", []),
                settings=_extract_invocation_settings(invocation_params),
                name=f"llm_start_{model}",
                importance=0.3,
            )

            await self._context._emit_event(event)
            self._run_map[run_id_str] = event.id
        except Exception:
            logger.warning("LangChain callback on_llm_start failed", exc_info=True)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM end event.

        Args:
            response: The LLM response result.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            start_time = self._start_times.pop(run_id_str, time.time())
            duration_ms = (time.time() - start_time) * 1000

            parent_id = self._run_map.get(run_id_str)

            content, tool_calls = _extract_response_content_and_tool_calls(response)

            usage = {}
            cost_usd = 0.0
            if response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})
                usage = {
                    "input_tokens": token_usage.get("prompt_tokens", 0),
                    "output_tokens": token_usage.get("completion_tokens", 0),
                }

            invocation_params = kwargs.get("invocation_params", {})
            model = invocation_params.get("model", invocation_params.get("model_name", "unknown"))

            event = LLMResponseEvent(
                session_id=self.session_id,
                parent_id=parent_id,
                model=model,
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                name=f"llm_end_{model}",
                importance=0.5,
            )

            await self._context._emit_event(event)
        except Exception:
            logger.warning("LangChain callback on_llm_end failed", exc_info=True)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM error event.

        Args:
            error: The exception that occurred.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            self._start_times.pop(run_id_str, None)
            self._run_map.pop(run_id_str, None)

            await self._context.record_error(
                error_type=type(error).__name__,
                error_message=str(error),
                name=f"llm_error_{run_id_str[:8]}",
            )
        except Exception:
            logger.warning("LangChain callback on_llm_error failed", exc_info=True)

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str | dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool start event.

        Args:
            serialized: Serialized tool configuration.
            input_str: Input string or dict for the tool.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            metadata: Additional metadata.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            self._start_times[run_id_str] = time.time()

            tool_name = serialized.get("name", kwargs.get("name", "unknown"))

            arguments = {"input": input_str}
            if isinstance(input_str, dict):
                arguments = input_str

            event = ToolCallEvent(
                session_id=self.session_id,
                parent_id=self._run_map.get(str(parent_run_id)) if parent_run_id else None,
                tool_name=tool_name,
                arguments=arguments,
                name=f"tool_start_{tool_name}",
                importance=0.4,
            )

            await self._context._emit_event(event)
            self._run_map[run_id_str] = event.id
        except Exception:
            logger.warning("LangChain callback on_tool_start failed", exc_info=True)

    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool end event.

        Args:
            output: The tool output.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            start_time = self._start_times.pop(run_id_str, time.time())
            self._run_map.pop(run_id_str, None)
            duration_ms = (time.time() - start_time) * 1000

            tool_name = kwargs.get("name", "unknown")

            result = output
            if not isinstance(output, str | dict | list | None):
                result = str(output)

            await self._context.record_tool_result(
                tool_name=tool_name,
                result=result,
                duration_ms=duration_ms,
                name=f"tool_end_{tool_name}",
            )
        except Exception:
            logger.warning("LangChain callback on_tool_end failed", exc_info=True)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool error event.

        Args:
            error: The exception that occurred.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            start_time = self._start_times.pop(run_id_str, time.time())
            duration_ms = (time.time() - start_time) * 1000

            tool_name = kwargs.get("name", "unknown")

            await self._context.record_tool_result(
                tool_name=tool_name,
                result=None,
                error=str(error),
                duration_ms=duration_ms,
                name=f"tool_error_{tool_name}",
            )
        except Exception:
            logger.warning("LangChain callback on_tool_error failed", exc_info=True)

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain start event.

        Args:
            serialized: Serialized chain configuration.
            inputs: Input data for the chain.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            metadata: Additional metadata.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            self._start_times[run_id_str] = time.time()

            chain_name = serialized.get("name", kwargs.get("name", "chain"))

            event = TraceEvent(
                session_id=self.session_id,
                parent_id=self._run_map.get(str(parent_run_id)) if parent_run_id else None,
                event_type=EventType.AGENT_START,
                name=f"chain_start_{chain_name}",
                data={"inputs": inputs, "chain_type": serialized.get("id", ["unknown"])[-1]},
                importance=0.3,
            )

            await self._context._emit_event(event)
            self._run_map[run_id_str] = event.id
        except Exception:
            logger.warning("LangChain callback on_chain_start failed", exc_info=True)

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain end event.

        Args:
            outputs: Output data from the chain.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            start_time = self._start_times.pop(run_id_str, time.time())
            duration_ms = (time.time() - start_time) * 1000

            parent_id = self._run_map.pop(run_id_str, None)

            event = TraceEvent(
                session_id=self.session_id,
                parent_id=parent_id,
                event_type=EventType.AGENT_END,
                name="chain_end",
                data={"outputs": outputs, "duration_ms": duration_ms},
                importance=0.3,
            )

            await self._context._emit_event(event)
        except Exception:
            logger.warning("LangChain callback on_chain_end failed", exc_info=True)

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain error event.

        Args:
            error: The exception that occurred.
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID if this is a nested run.
            tags: Tags associated with this run.
            **kwargs: Additional keyword arguments.
        """
        try:
            if not self._context:
                return

            run_id_str = str(run_id)
            self._start_times.pop(run_id_str, None)
            self._run_map.pop(run_id_str, None)

            await self._context.record_error(
                error_type=type(error).__name__,
                error_message=str(error),
                name=f"chain_error_{run_id_str[:8]}",
            )
        except Exception:
            logger.warning("LangChain callback on_chain_error failed", exc_info=True)
