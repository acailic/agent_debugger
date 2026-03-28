"""Auto-patch registration for LangChain adapter.

This module provides the register_auto_patch function that registers the
LangChain adapter with the global auto-patch registry for automatic
instrumentation.
"""


def register_auto_patch() -> None:
    """Register the LangChain adapter with the global auto-patch registry.

    This function is called by the auto-instrumentation system to register
    the :class:`~agent_debugger_sdk.auto_patch.adapters.langchain_adapter.LangChainAdapter`
    with the global :class:`~agent_debugger_sdk.auto_patch.registry.PatchRegistry`.

    Once registered, the adapter will be activated the next time
    :func:`~agent_debugger_sdk.auto_patch.activate` is called.  It installs a
    lightweight synchronous callback handler into LangChain's global callback
    manager so that every LLM call automatically emits trace events.
    """
    from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import (  # noqa: PLC0415
        LangChainAdapter,
    )
    from agent_debugger_sdk.auto_patch.registry import get_registry  # noqa: PLC0415

    registry = get_registry()
    if "langchain" not in registry.registered_names():
        registry.register(LangChainAdapter())
