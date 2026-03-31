"""Auto-patch adapter for the OpenAI Python SDK.

Wraps ``openai.OpenAI`` (sync) and ``openai.AsyncOpenAI`` (async) so that
every non-streaming ``chat.completions.create`` call emits
:class:`~agent_debugger_sdk.core.events.LLMRequestEvent`,
:class:`~agent_debugger_sdk.core.events.LLMResponseEvent`, and zero or more
:class:`~agent_debugger_sdk.core.events.ToolCallEvent` objects to the Peaky
Peek collector — without any changes to user code.

Streaming calls (``stream=True``) are passed through unchanged; intercepting
streamed responses requires different handling and is out of scope for this
adapter.

Usage
-----

Activate via environment variable:

.. code-block:: bash

    export PEAKY_PEEK_AUTO_PATCH="openai"
    export PEAKY_PEEK_SERVER_URL="http://localhost:8000"
    export PEAKY_PEEK_CAPTURE_CONTENT="true"
    python your_agent_script.py

Or activate programmatically:

.. code-block:: python

    from agent_debugger_sdk.auto_patch import activate, PatchConfig

    config = PatchConfig(
        server_url="http://localhost:8000",
        capture_content=True,
        agent_name="my-openai-agent",
    )
    activate(config)

    # All subsequent OpenAI calls are traced
    import openai
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )

OpenAI-specific notes
---------------------
* Tool use is indicated by ``choice.finish_reason == "tool_calls"``
* Tool call arguments are JSON strings in ``tc.function.arguments`` —
  the adapter parses these to dicts for :class:`~agent_debugger_sdk.core.events.ToolCallEvent`
* Token counts live at ``response.usage.prompt_tokens`` /
  ``response.usage.completion_tokens``
"""

from __future__ import annotations

import json
import logging

from agent_debugger_sdk.auto_patch._transport import SyncTransport
from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

logger = logging.getLogger("agent_debugger.auto_patch")


class OpenAIAdapter(BaseAdapter):
    """Auto-patch adapter for ``openai`` >= 1.x."""

    name = "openai"

    def is_available(self) -> bool:
        """Return True if the ``openai`` package is importable."""
        try:
            import openai  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch OpenAI sync and async clients.

        Replaces ``openai.OpenAI.chat.completions.create`` and
        ``openai.AsyncOpenAI.chat.completions.create`` with instrumented wrappers.

        Args:
            config: Patch configuration including server URL and content capture settings.
        """
        import openai

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._originals: dict[str, object] = {}

        # --- Sync client ---
        self._originals["sync_create"] = openai.OpenAI.chat.completions.create
        openai.OpenAI.chat.completions.create = self._make_sync_wrapper(openai.OpenAI.chat.completions.create)

        # --- Async client ---
        self._originals["async_create"] = openai.AsyncOpenAI.chat.completions.create
        openai.AsyncOpenAI.chat.completions.create = self._make_async_wrapper(
            openai.AsyncOpenAI.chat.completions.create
        )

    def unpatch(self) -> None:
        """Restore the original OpenAI client methods.

        Stops the background transport thread and restores the original
        ``chat.completions.create`` methods on both sync and async clients.
        """
        try:
            import openai

            if "sync_create" in self._originals:
                openai.OpenAI.chat.completions.create = self._originals["sync_create"]
            if "async_create" in self._originals:
                openai.AsyncOpenAI.chat.completions.create = self._originals["async_create"]
        except Exception:
            logger.warning("OpenAIAdapter: failed to restore original client methods", exc_info=True)
        finally:
            self._shutdown_transport()

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------

    def _emit_request(self, kwargs: dict, session_id: str) -> str:
        """Build and send an LLMRequestEvent; return its event id.

        Args:
            kwargs: The keyword arguments passed to the OpenAI ``create`` call.
            session_id: The current tracing session ID.

        Returns:
            The generated event ID string.
        """
        tools_raw = kwargs.get("tools") or []
        tools = [t.get("function", t) for t in tools_raw]

        event = LLMRequestEvent(
            session_id=session_id,
            name="llm_request",
            model=kwargs.get("model", ""),
            messages=kwargs.get("messages", []) if self._config.capture_content else [],
            tools=tools,
            settings={k: v for k, v in kwargs.items() if k in ("temperature", "max_tokens", "top_p")},
        )
        self._transport.send_event(event.to_dict())
        return event.id

    def _emit_response(
        self,
        response,
        request_event_id: str,
        session_id: str,
        duration_ms: float,
    ) -> None:
        """Build and send LLMResponseEvent plus individual ToolCallEvents.

        Args:
            response: The OpenAI ``ChatCompletion`` response object.
            request_event_id: The ID of the corresponding LLMRequestEvent.
            session_id: The current tracing session ID.
            duration_ms: Request duration in milliseconds.
        """
        choices = getattr(response, "choices", None)
        choice = choices[0] if choices else None
        content = ""
        tool_calls_raw: list[dict] = []

        if choice:
            message = getattr(choice, "message", None)
            if message:
                if self._config.capture_content and getattr(message, "content", None):
                    content = message.content

                if getattr(choice, "finish_reason", None) == "tool_calls" and getattr(message, "tool_calls", None):
                    for tc in message.tool_calls:
                        try:
                            # OpenAI serialises tool call arguments as a JSON string; parse to dict.
                            function = getattr(tc, "function", None)
                            if function and hasattr(function, "arguments") and hasattr(function, "name"):
                                args = json.loads(function.arguments)
                                tool_calls_raw.append(
                                    {
                                        "id": getattr(tc, "id", ""),
                                        "tool_name": function.name,
                                        "arguments": args,
                                    }
                                )
                        except (json.JSONDecodeError, TypeError, ValueError):
                            # Log and continue with empty args if parsing fails
                            logger.debug(
                                "OpenAIAdapter: failed to parse tool call arguments for tool %s",
                                getattr(getattr(tc, "function", None), "name", "unknown"),
                            )

        usage = getattr(response, "usage", None)
        response_event = LLMResponseEvent(
            session_id=session_id,
            parent_id=request_event_id,
            name="llm_response",
            model=getattr(response, "model", "") or "",
            content=content,
            tool_calls=tool_calls_raw,
            usage={
                "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            },
            duration_ms=duration_ms,
        )
        self._transport.send_event(response_event.to_dict())

        # One ToolCallEvent per tool invocation
        for tc in tool_calls_raw:
            tc_event = ToolCallEvent(
                session_id=session_id,
                parent_id=response_event.id,
                name=tc["tool_name"],
                tool_name=tc["tool_name"],
                arguments=tc["arguments"],
            )
            self._transport.send_event(tc_event.to_dict())
