"""Auto-patch adapter for PydanticAI.

Tier 2 strategy: monkey-patches ``pydantic_ai.Agent.run`` at the class level
so that every agent run emits trace events without any changes to user code.

PydanticAI's ``Agent.run`` is an async method, so the patch wraps it in an
async wrapper that emits :class:`~agent_debugger_sdk.core.events.LLMRequestEvent`
and :class:`~agent_debugger_sdk.core.events.LLMResponseEvent` events using the
synchronous :class:`~agent_debugger_sdk.auto_patch._transport.SyncTransport`.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_debugger_sdk.adapters.pydantic_ai.utils import resolve_model_name
from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session
from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent

logger = logging.getLogger("agent_debugger.auto_patch")


class PydanticAIAdapter(BaseAdapter):
    """Auto-patch adapter for PydanticAI.

    Monkey-patches ``pydantic_ai.Agent.run`` at the class level so that every
    agent invocation automatically emits LLM request/response trace events.

    The original ``run`` method is restored on :meth:`unpatch`.

    Note: One instance per process is assumed when using class-level monkey-patching.
    """

    name = "pydanticai"

    def __init__(self) -> None:
        self._original_run: Any = None
        self._transport: SyncTransport | None = None
        self._config: PatchConfig | None = None
        self._session_id: str | None = None

    def is_available(self) -> bool:
        """Return True if ``pydantic_ai`` is importable."""
        try:
            import pydantic_ai  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch ``pydantic_ai.Agent.run`` to emit trace events.

        Args:
            config: Active patch configuration.
        """
        import pydantic_ai  # noqa: PLC0415

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._session_id = get_or_create_session(self._transport, config.agent_name, self.name)

        Agent = pydantic_ai.Agent

        if self._check_double_patch(Agent.run):
            return

        self._original_run = Agent.run
        adapter = self

        async def _traced_run(agent_self: Any, user_prompt: Any = None, **kwargs: Any) -> Any:
            transport = adapter._transport
            cfg = adapter._config

            if transport is None or cfg is None:
                return await adapter._original_run(agent_self, user_prompt, **kwargs)

            try:
                session_id = adapter._session_id or ""
                model_name = resolve_model_name(agent_self, None)

                messages: list[dict[str, Any]] = []
                if cfg.capture_content and user_prompt is not None:
                    messages = [{"role": "user", "content": str(user_prompt)}]

                request_event = LLMRequestEvent(
                    session_id=session_id,
                    name="llm_request",
                    model=model_name,
                    messages=messages,
                    tools=[],
                    settings={},
                )
                transport.send_event(request_event.to_dict())
            except Exception:
                logger.warning("PydanticAIAdapter: failed to emit request event", exc_info=True)
                session_id = ""
                request_event = None

            start = time.perf_counter()
            result = await adapter._original_run(agent_self, user_prompt, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000

            try:
                if session_id and transport is not None and cfg is not None:
                    content = ""
                    if cfg.capture_content and hasattr(result, "data"):
                        content = str(result.data)

                    model_name = resolve_model_name(agent_self, None)
                    usage = _extract_usage(result)

                    response_event = LLMResponseEvent(
                        session_id=session_id,
                        parent_id=request_event.id if request_event is not None else None,
                        name="llm_response",
                        model=model_name,
                        content=content,
                        tool_calls=[],
                        usage=usage,
                        duration_ms=duration_ms,
                    )
                    transport.send_event(response_event.to_dict())
            except Exception:
                logger.warning("PydanticAIAdapter: failed to emit response event", exc_info=True)

            return result

        _traced_run._peaky_peek_patched = True  # type: ignore[attr-defined]
        Agent.run = _traced_run  # type: ignore[method-assign]
        logger.debug("PydanticAIAdapter: patched Agent.run")

    def unpatch(self) -> None:
        """Restore the original ``pydantic_ai.Agent.run`` method."""
        if self._original_run is None:
            return

        try:
            import pydantic_ai  # noqa: PLC0415

            pydantic_ai.Agent.run = self._original_run  # type: ignore[method-assign]
            self._original_run = None
            logger.debug("PydanticAIAdapter: restored original Agent.run")
        except Exception:
            logger.warning("PydanticAIAdapter: failed to restore Agent.run", exc_info=True)
        finally:
            self._shutdown_transport()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_usage(result: Any) -> dict[str, int]:
    """Extract token usage from a PydanticAI ``RunResult``.

    Args:
        result: A ``pydantic_ai.result.RunResult`` (or compatible) object.

    Returns:
        A dict with ``input_tokens`` and ``output_tokens`` keys.
    """
    empty: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    # PydanticAI >= 0.0.9 exposes result.usage() returning a Usage object
    usage_fn = getattr(result, "usage", None)
    if callable(usage_fn):
        try:
            usage_obj = usage_fn()
            return {
                "input_tokens": getattr(usage_obj, "request_tokens", 0) or 0,
                "output_tokens": getattr(usage_obj, "response_tokens", 0) or 0,
            }
        except Exception:
            logger.warning("PydanticAIAdapter: failed to extract usage from result.usage()", exc_info=True)

    # Older / alternate attribute layouts
    if hasattr(result, "usage") and not callable(result.usage):
        u = result.usage
        return {
            "input_tokens": getattr(u, "request_tokens", 0) or getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "response_tokens", 0) or getattr(u, "output_tokens", 0) or 0,
        }

    return empty
