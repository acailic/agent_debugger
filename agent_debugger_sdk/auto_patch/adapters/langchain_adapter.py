"""Auto-patch adapter for LangChain.

Tier 2 strategy: installs a lightweight callback handler into LangChain's
global callback manager so that every LLM and tool call emits trace events
without any changes to user code.

Unlike the manual ``LangChainTracingHandler`` (which uses an async
``TraceContext``), this handler sends events directly via :class:`SyncTransport`
to stay compatible with the synchronous auto-patch infrastructure.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session
from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

logger = logging.getLogger("agent_debugger.auto_patch")

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import get_buffer_string
except ImportError:  # pragma: no cover - adapter availability guards runtime use
    BaseCallbackHandler = object

    def get_buffer_string(messages: Any) -> str:
        return str(messages)


def _normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    """Return a stable tool-call payload from LangChain response objects."""
    normalized: list[dict[str, Any]] = []

    if not isinstance(raw_tool_calls, (list, tuple)):
        raw_tool_calls = []

    for tool_call in raw_tool_calls:
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or {}
            name = tool_call.get("name") or function.get("name", "")
            arguments = tool_call.get("args")
            if arguments is None:
                arguments = tool_call.get("arguments", function.get("arguments", {}))
            normalized.append(
                {
                    "id": tool_call.get("id", ""),
                    "name": name,
                    "arguments": arguments if arguments is not None else {},
                }
            )
            continue

        function = getattr(tool_call, "function", None)
        arguments = getattr(tool_call, "args", None)
        if arguments is None and function is not None:
            arguments = getattr(function, "arguments", None)
        if arguments is None:
            arguments = getattr(tool_call, "arguments", {})

        normalized.append(
            {
                "id": getattr(tool_call, "id", ""),
                "name": getattr(function, "name", "") if function is not None else getattr(tool_call, "name", ""),
                "arguments": arguments if arguments is not None else {},
            }
        )

    return normalized


def _extract_response_content_and_tool_calls(
    response: Any,
    capture_content: bool,
) -> tuple[str, list[dict[str, Any]]]:
    """Extract content and tool calls from a LangChain response object."""
    content = ""
    tool_calls: list[dict[str, Any]] = []

    if not hasattr(response, "generations") or not response.generations:
        return content, tool_calls

    first = response.generations[0]
    if not first:
        return content, tool_calls

    generation = first[0]
    message = getattr(generation, "message", None)

    if capture_content:
        content = getattr(generation, "text", "")
        if not content and message is not None:
            message_content = getattr(message, "content", "")
            content = message_content if isinstance(message_content, str) else str(message_content)

    if message is not None:
        tool_calls = _normalize_tool_calls(getattr(message, "tool_calls", []))
    if not tool_calls:
        tool_calls = _normalize_tool_calls(getattr(generation, "tool_calls", []))

    return content, tool_calls


def _extract_invocation_settings(invocation_params: dict[str, Any]) -> dict[str, Any]:
    """Normalize LangChain invocation settings into stable trace fields."""
    max_tokens = invocation_params.get("max_tokens", invocation_params.get("max_completion_tokens"))
    return {
        k: v
        for k, v in {
            "temperature": invocation_params.get("temperature"),
            "max_tokens": max_tokens,
        }.items()
        if v is not None
    }


class _SyncTracingCallbackHandler(BaseCallbackHandler):
    """Minimal LangChain callback handler that routes events via SyncTransport.

    This handler is compatible with LangChain's ``BaseCallbackHandler`` interface.
    It is installed globally into LangChain's callback manager by
    :class:`LangChainAdapter`.

    Args:
        session_id: The session ID to tag events with.
        transport: The :class:`SyncTransport` to send events through.
        capture_content: Whether to capture full prompt/response text.
    """

    raise_error = False  # LangChain checks this attribute
    run_inline = False

    def __init__(self, session_id: str, transport: SyncTransport, capture_content: bool = False) -> None:
        self._session_id = session_id
        self._transport = transport
        self._capture_content = capture_content
        self._start_times: dict[str, float] = {}
        self._model_names: dict[str, str] = {}
        self._request_event_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # LLM callbacks
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        """Emit an LLMRequestEvent when an LLM call begins."""
        try:
            run_id_str = str(run_id)
            self._start_times[run_id_str] = time.perf_counter()

            invocation_params = kwargs.get("invocation_params") or {}
            model = invocation_params.get("model") or invocation_params.get("model_name") or "unknown"
            self._model_names[run_id_str] = model

            messages: list[dict[str, Any]] = []
            if self._capture_content:
                messages = [{"role": "user", "content": p} for p in prompts]

            event = LLMRequestEvent(
                session_id=self._session_id,
                name="llm_request",
                model=model,
                messages=messages,
                tools=[],
                settings=_extract_invocation_settings(invocation_params),
            )
            self._request_event_ids[run_id_str] = event.id
            self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning("LangChainAdapter on_llm_start failed", exc_info=True)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Adapt LangChain chat-model callbacks into the LLM start path."""
        prompts = [get_buffer_string(message_list) for message_list in messages]
        self.on_llm_start(
            serialized,
            prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        """Emit an LLMResponseEvent when an LLM call finishes."""
        try:
            run_id_str = str(run_id)
            start = self._start_times.pop(run_id_str, time.perf_counter())
            duration_ms = (time.perf_counter() - start) * 1000
            request_event_id = self._request_event_ids.pop(run_id_str, None)

            content, tool_calls = _extract_response_content_and_tool_calls(response, self._capture_content)

            usage: dict[str, int] = {}
            if hasattr(response, "llm_output") and response.llm_output:
                token_usage = response.llm_output.get("token_usage") or {}
                usage = {
                    "input_tokens": token_usage.get("prompt_tokens", 0),
                    "output_tokens": token_usage.get("completion_tokens", 0),
                }

            model = self._model_names.pop(run_id_str, "unknown")

            event = LLMResponseEvent(
                session_id=self._session_id,
                parent_id=request_event_id,
                name="llm_response",
                model=model,
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                duration_ms=duration_ms,
            )
            self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning("LangChainAdapter on_llm_end failed", exc_info=True)

    def on_llm_error(self, error: BaseException, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        """Clean up tracking state on LLM error."""
        run_id_str = str(run_id)
        self._start_times.pop(run_id_str, None)
        self._model_names.pop(run_id_str, None)
        self._request_event_ids.pop(run_id_str, None)

    # ------------------------------------------------------------------
    # Tool callbacks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        """Emit a ToolCallEvent when a tool is invoked."""
        try:
            run_id_str = str(run_id)
            self._start_times[run_id_str] = time.perf_counter()

            tool_name = serialized.get("name") or kwargs.get("name") or "unknown"
            arguments: Any = {"input": input_str}
            if isinstance(input_str, dict):
                arguments = input_str

            event = ToolCallEvent(
                session_id=self._session_id,
                name=f"tool_call_{tool_name}",
                tool_name=tool_name,
                arguments=arguments,
            )
            self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning("LangChainAdapter on_tool_start failed", exc_info=True)

    def on_tool_end(self, output: str, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        """Clean up tracking state when a tool completes."""
        self._start_times.pop(str(run_id), None)

    def on_tool_error(self, error: BaseException, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        """Clean up tracking state on tool error."""
        self._start_times.pop(str(run_id), None)

    # ------------------------------------------------------------------
    # Chain callbacks (no-op — we only track LLM and tool calls)
    # ------------------------------------------------------------------

    def on_chain_start(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_chain_end(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_chain_error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_agent_action(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_agent_finish(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_text(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_retry(self, *args: Any, **kwargs: Any) -> None:
        pass


class LangChainAdapter(BaseAdapter):
    """Auto-patch adapter for LangChain.

    Installs a synchronous callback handler into LangChain's global callback
    manager so that every LLM call automatically emits trace events.

    The handler is appended to ``langchain_core.callbacks.manager._handlers``
    (the list of global inheritable handlers) and removed on :meth:`unpatch`.
    """

    name = "langchain"

    def __init__(self) -> None:
        self._handler: _SyncTracingCallbackHandler | None = None
        self._transport: SyncTransport | None = None

    def is_available(self) -> bool:
        """Return True if ``langchain_core`` is importable."""
        try:
            import langchain_core  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Install the tracing handler into LangChain's global callback manager.

        Args:
            config: Active patch configuration.
        """
        self._transport = SyncTransport(config.server_url)
        session_id = get_or_create_session(self._transport, config.agent_name, self.name)

        self._handler = _SyncTracingCallbackHandler(
            session_id=session_id,
            transport=self._transport,
            capture_content=config.capture_content,
        )

        try:
            self._install_handler(self._handler)
        except Exception:
            logger.warning("LangChainAdapter: failed to install global handler", exc_info=True)

    def unpatch(self) -> None:
        """Remove the handler from LangChain's global callback manager."""
        if self._handler is not None:
            try:
                self._remove_handler(self._handler)
            except Exception:
                logger.warning("LangChainAdapter: failed to remove global handler", exc_info=True)
            finally:
                self._handler = None
        if self._transport is not None:
            self._transport.shutdown()
            self._transport = None

    # ------------------------------------------------------------------
    # Internal: LangChain global callback manager access
    # ------------------------------------------------------------------

    @staticmethod
    def _install_handler(handler: _SyncTracingCallbackHandler) -> None:
        """Append *handler* to LangChain's global inheritable handler list."""
        import langchain_core.callbacks.manager as _mgr  # noqa: PLC0415

        # LangChain stores global handlers in the module-level list
        # ``_handlers`` on the callback manager module (< 0.3) or exposes
        # ``get_callback_manager()`` returning a manager with ``handlers``.
        # We probe both locations gracefully.
        if hasattr(_mgr, "_handlers"):
            # Direct list access (langchain-core < 0.3-ish internal detail)
            _mgr._handlers.append(handler)  # type: ignore[attr-defined]
        elif hasattr(_mgr, "get_callback_manager"):
            mgr = _mgr.get_callback_manager()
            if hasattr(mgr, "add_handler"):
                mgr.add_handler(handler, inherit=True)
            elif hasattr(mgr, "handlers"):
                mgr.handlers.append(handler)
        else:
            # Fallback: store on the module so we can remove it later
            if not hasattr(_mgr, "_peaky_peek_handlers"):
                _mgr._peaky_peek_handlers = []  # type: ignore[attr-defined]
            _mgr._peaky_peek_handlers.append(handler)  # type: ignore[attr-defined]
            logger.debug(
                "LangChainAdapter: no known global handler API found — handler stored but may not fire automatically"
            )

    @staticmethod
    def _remove_handler(handler: _SyncTracingCallbackHandler) -> None:
        """Remove *handler* from LangChain's global inheritable handler list."""
        import langchain_core.callbacks.manager as _mgr  # noqa: PLC0415

        if hasattr(_mgr, "_handlers"):
            try:
                _mgr._handlers.remove(handler)  # type: ignore[attr-defined]
            except ValueError:
                pass
        elif hasattr(_mgr, "get_callback_manager"):
            mgr = _mgr.get_callback_manager()
            if hasattr(mgr, "remove_handler"):
                mgr.remove_handler(handler)
            elif hasattr(mgr, "handlers"):
                try:
                    mgr.handlers.remove(handler)
                except ValueError:
                    pass
        elif hasattr(_mgr, "_peaky_peek_handlers"):
            try:
                _mgr._peaky_peek_handlers.remove(handler)  # type: ignore[attr-defined]
            except ValueError:
                pass
