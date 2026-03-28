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
        """Monkey-patch OpenAI sync and async clients."""
        import openai

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._originals: dict = {}

        # --- Sync client ---
        self._originals["sync_create"] = openai.OpenAI.chat.completions.create
        openai.OpenAI.chat.completions.create = self._make_sync_wrapper(openai.OpenAI.chat.completions.create)

        # --- Async client ---
        self._originals["async_create"] = openai.AsyncOpenAI.chat.completions.create
        openai.AsyncOpenAI.chat.completions.create = self._make_async_wrapper(
            openai.AsyncOpenAI.chat.completions.create
        )

    def unpatch(self) -> None:
        """Restore the original OpenAI client methods."""
        try:
            import openai

            if "sync_create" in self._originals:
                openai.OpenAI.chat.completions.create = self._originals["sync_create"]
            if "async_create" in self._originals:
                openai.AsyncOpenAI.chat.completions.create = self._originals["async_create"]
        except Exception:
            pass
        finally:
            if self._transport is not None:
                self._transport.shutdown()
                self._transport = None

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------

    def _emit_request(self, kwargs: dict, session_id: str) -> str:
        """Build and send an LLMRequestEvent; return its event id."""
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
        """Build and send LLMResponseEvent plus individual ToolCallEvents."""
        choice = response.choices[0] if response.choices else None
        content = ""
        tool_calls_raw: list[dict] = []

        if choice:
            if self._config.capture_content and choice.message.content:
                content = choice.message.content

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        # OpenAI serialises tool call arguments as a JSON string; parse to dict.
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, AttributeError):
                        args = {}
                    tool_calls_raw.append(
                        {
                            "id": tc.id,
                            "tool_name": tc.function.name,
                            "arguments": args,
                        }
                    )

        usage = response.usage
        response_event = LLMResponseEvent(
            session_id=session_id,
            parent_id=request_event_id,
            name="llm_response",
            model=response.model or "",
            content=content,
            tool_calls=tool_calls_raw,
            usage={
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
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
