"""Auto-patch adapter for the Anthropic Python SDK.

Wraps ``anthropic.Anthropic`` (sync) and ``anthropic.AsyncAnthropic`` (async)
so that every non-streaming ``messages.create`` call emits
:class:`~agent_debugger_sdk.core.events.LLMRequestEvent`,
:class:`~agent_debugger_sdk.core.events.LLMResponseEvent`, and zero or more
:class:`~agent_debugger_sdk.core.events.ToolCallEvent` objects to the Peaky
Peek collector — without any changes to user code.

Streaming calls (``stream=True``) are passed through unchanged.

Anthropic-specific structural notes
------------------------------------
* Tool use is indicated by ``response.stop_reason == "tool_use"``
* Content is a list of typed blocks; ``type == "tool_use"`` blocks carry tool
  calls.  The ``.input`` attribute is already a plain dict — no JSON parsing
  needed.
* Text blocks have ``type == "text"`` and a ``.text`` string attribute.
* Token counts live at ``response.usage.input_tokens`` /
  ``response.usage.output_tokens``.
"""

from __future__ import annotations

import logging

from agent_debugger_sdk.auto_patch._transport import SyncTransport
from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import LLMRequestEvent, LLMResponseEvent, ToolCallEvent

logger = logging.getLogger("agent_debugger.auto_patch")


class AnthropicAdapter(BaseAdapter):
    """Auto-patch adapter for ``anthropic`` >= 0.20.x."""

    name = "anthropic"

    def is_available(self) -> bool:
        """Return True if the ``anthropic`` package is importable."""
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch Anthropic sync and async clients."""
        import anthropic

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._originals: dict = {}

        # --- Sync client ---
        self._originals["sync_create"] = anthropic.Anthropic.messages.create
        anthropic.Anthropic.messages.create = self._make_sync_wrapper(anthropic.Anthropic.messages.create)

        # --- Async client ---
        self._originals["async_create"] = anthropic.AsyncAnthropic.messages.create
        anthropic.AsyncAnthropic.messages.create = self._make_async_wrapper(anthropic.AsyncAnthropic.messages.create)

    def unpatch(self) -> None:
        """Restore the original Anthropic client methods."""
        try:
            import anthropic

            if "sync_create" in self._originals:
                anthropic.Anthropic.messages.create = self._originals["sync_create"]
            if "async_create" in self._originals:
                anthropic.AsyncAnthropic.messages.create = self._originals["async_create"]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event emission helpers (Anthropic-specific)
    # ------------------------------------------------------------------

    def _emit_request(self, kwargs: dict, session_id: str) -> str:
        """Build and send an LLMRequestEvent; return its event id."""
        tools_raw = kwargs.get("tools") or []

        event = LLMRequestEvent(
            session_id=session_id,
            name="llm_request",
            model=kwargs.get("model", ""),
            messages=kwargs.get("messages", []) if self._config.capture_content else [],
            tools=tools_raw,
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
        """Build and send LLMResponseEvent plus individual ToolCallEvents."""
        content = ""
        tool_calls_raw: list[dict] = []

        if response.content:
            # Collect text from text blocks
            if self._config.capture_content:
                text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
                content = "\n".join(text_parts)

            # Collect tool-use blocks when stop reason indicates tool use
            if getattr(response, "stop_reason", None) == "tool_use":
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        tool_calls_raw.append(
                            {
                                "id": block.id,
                                "tool_name": block.name,
                                # .input is already a dict — no JSON parsing
                                "arguments": block.input if isinstance(block.input, dict) else {},
                            }
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
                "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
                "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
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
