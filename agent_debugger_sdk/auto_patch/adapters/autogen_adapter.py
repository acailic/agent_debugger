"""Auto-patch adapter for AutoGen.

Tier 3 strategy: detects which AutoGen API version is available and
monkey-patches the top-level orchestration method so that every agent
run emits AGENT_START and AGENT_END trace events without any user-code
changes.

Supports:
- AutoGen v0.2.x (``autogen``): patches ``ConversableAgent.initiate_chat``
- AutoGen v0.4.x (``autogen_agentchat``): patches
  ``autogen_agentchat.agents.AssistantAgent.run``
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import EventType

logger = logging.getLogger("agent_debugger.auto_patch")


class AutoGenAdapter(BaseAdapter):
    """Auto-patch adapter for AutoGen (v0.2.x and v0.4.x).

    Detects which AutoGen package is installed and patches the appropriate
    top-level orchestration method to emit AGENT_START / AGENT_END events.

    For v0.2.x: patches ``autogen.ConversableAgent.initiate_chat``
    For v0.4.x: patches ``autogen_agentchat.agents.AssistantAgent.run``
    """

    name = "autogen"

    def __init__(self) -> None:
        super().__init__()
        self._original_method: Any = None
        self._patched_class: Any = None
        self._patched_method_name: str | None = None
        self._api_version: str | None = None  # "v02" or "v04"

    def is_available(self) -> bool:
        """Return True if ``autogen`` or ``autogen_agentchat`` is importable."""
        try:
            import autogen  # noqa: F401

            return True
        except ImportError:
            pass
        try:
            import autogen_agentchat  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch AutoGen's orchestration method to emit trace events.

        Args:
            config: Active patch configuration.
        """
        self._config = config

        # Prefer v0.2 (``autogen``) if available; fall back to v0.4.
        # Transport is only created if patching succeeds.
        patched = self._try_patch_v02() or self._try_patch_v04()
        if not patched:
            logger.debug("AutoGenAdapter: no patchable target found")
            return

        self._setup_transport_and_session(config)

    # ------------------------------------------------------------------
    # Version-specific patchers
    # ------------------------------------------------------------------

    def _try_patch_v02(self) -> bool:
        """Attempt to patch AutoGen v0.2 ``ConversableAgent.initiate_chat``.

        Returns:
            True if the patch was applied, False if ``autogen`` is unavailable.
        """
        try:
            import autogen  # noqa: PLC0415
        except ImportError:
            return False

        target_cls = autogen.ConversableAgent
        method_name = "initiate_chat"

        method = getattr(target_cls, method_name, None)
        if method is not None and self._is_patched(method):
            logger.debug("AutoGenAdapter: ConversableAgent.initiate_chat already patched — skipping")
            return False

        original = getattr(target_cls, method_name)
        self._original_method = original
        self._patched_class = target_cls
        self._patched_method_name = method_name
        self._api_version = "v02"

        adapter = self

        def traced_initiate_chat(self_agent: Any, *args: Any, **kwargs: Any) -> Any:
            return adapter._wrap_sync_call(
                lambda: adapter._original_method(self_agent, *args, **kwargs),
                start_name="autogen.initiate_chat",
                end_name="autogen.initiate_chat.end",
                error_name="autogen.initiate_chat.error",
            )

        traced_initiate_chat._peaky_peek_patched = True  # type: ignore[attr-defined]
        setattr(target_cls, method_name, traced_initiate_chat)
        logger.debug("AutoGenAdapter: patched ConversableAgent.initiate_chat (v0.2)")
        return True

    def _try_patch_v04(self) -> bool:
        """Attempt to patch AutoGen v0.4 ``AssistantAgent.run``.

        Returns:
            True if the patch was applied, False if ``autogen_agentchat`` is unavailable.
        """
        try:
            import autogen_agentchat.agents  # noqa: PLC0415
        except ImportError:
            return False

        target_cls = autogen_agentchat.agents.AssistantAgent
        method_name = "run"

        method = getattr(target_cls, method_name, None)
        if method is not None and self._is_patched(method):
            logger.debug("AutoGenAdapter: AssistantAgent.run already patched — skipping")
            return False

        original = getattr(target_cls, method_name)
        self._original_method = original
        self._patched_class = target_cls
        self._patched_method_name = method_name
        self._api_version = "v04"

        adapter = self

        async def traced_run(self_agent: Any, *args: Any, **kwargs: Any) -> Any:
            return await adapter._wrap_async_call(
                lambda: adapter._original_method(self_agent, *args, **kwargs),
                start_name="autogen.run",
                end_name="autogen.run.end",
                error_name="autogen.run.error",
            )

        traced_run._peaky_peek_patched = True  # type: ignore[attr-defined]
        setattr(target_cls, method_name, traced_run)
        logger.debug("AutoGenAdapter: patched AssistantAgent.run (v0.4)")
        return True

    # ------------------------------------------------------------------
    # Shared wrap helpers
    # ------------------------------------------------------------------

    def _wrap_sync_call(
        self,
        fn: Any,
        *,
        start_name: str,
        end_name: str,
        error_name: str,
    ) -> Any:
        self._emit_trace_event_safe(EventType.AGENT_START, start_name)

        try:
            result = fn()
        except Exception as exc:
            self._emit_error_event_safe(error_name, exc)
            raise

        self._emit_trace_event_safe(EventType.AGENT_END, end_name)
        return result

    async def _wrap_async_call(
        self,
        fn: Any,
        *,
        start_name: str,
        end_name: str,
        error_name: str,
    ) -> Any:
        self._emit_trace_event_safe(EventType.AGENT_START, start_name, is_async=True)

        try:
            result = await fn()
        except Exception as exc:
            self._emit_error_event_safe(error_name, exc, is_async=True)
            raise

        self._emit_trace_event_safe(EventType.AGENT_END, end_name, is_async=True)
        return result

    def unpatch(self) -> None:
        """Restore the original AutoGen method."""
        if self._original_method is None:
            return

        try:
            if self._patched_class is not None and self._patched_method_name is not None:
                setattr(self._patched_class, self._patched_method_name, self._original_method)
                logger.debug(
                    "AutoGenAdapter: restored %s.%s",
                    self._patched_class.__name__,
                    self._patched_method_name,
                )
            self._original_method = None
            self._patched_class = None
            self._patched_method_name = None
            self._api_version = None
        except Exception:
            logger.warning("AutoGenAdapter: failed to restore original method", exc_info=True)
        finally:
            self._cleanup_transport()
