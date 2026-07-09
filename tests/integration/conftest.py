"""Shared fixtures for integration tests.

All integration tests require the ZAI_API_KEY environment variable.
Tests are marked with ``@pytest.mark.integration`` and excluded from default runs.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Session-scoped gate
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Mark tests under this directory as integration tests, then skip if no API key.

    ``pytestmark`` at conftest module scope is inert (pytest only honors it in
    test modules), and this hook receives *every* collected item in the session
    regardless of which conftest defines it — so we must (a) gate the marker on
    the item living under this conftest's directory, and (b) add the marker
    per-item. That makes the ``-m 'not integration'`` filter in pyproject.toml
    actually deselect these tests in the default run, and lets the no-API-key
    skip apply to every integration item.
    """
    api_key = os.environ.get("ZAI_API_KEY")
    integration_root = Path(__file__).resolve().parent
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except (TypeError, ValueError):
            continue
        if integration_root not in item_path.parents:
            continue
        item.add_marker(pytest.mark.integration)
        if not api_key:
            item.add_marker(pytest.mark.skip(reason="No ZAI_API_KEY found — skipping integration test"))


# ---------------------------------------------------------------------------
# LLM fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def zai_api_key():
    """Return the required z.ai API key for live integration tests."""
    api_key = os.environ.get("ZAI_API_KEY")
    if not api_key:
        pytest.skip("No ZAI_API_KEY found — skipping integration test")
    return api_key


@pytest.fixture
def zai_chat_model(zai_api_key):
    """ChatOpenAI instance configured for the z.ai endpoint.

    Uses GLM-4.6 (a reasoning model) with sufficient max_tokens for
    both reasoning and response content.
    """
    pytest.importorskip("langchain_openai")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url="https://api.z.ai/api/coding/paas/v4",
        api_key=zai_api_key,
        model="glm-4.6",
        max_tokens=500,
        temperature=0,
    )


@pytest.fixture
def zai_pydantic_model(zai_api_key):
    """PydanticAI OpenAI-compatible model configured for the z.ai endpoint."""
    pytest.importorskip("pydantic_ai")

    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        api_key=zai_api_key,
        base_url="https://api.z.ai/api/coding/paas/v4",
    )
    return OpenAIChatModel("glm-4.6", provider=provider)


# ---------------------------------------------------------------------------
# TraceContext + handler fixture (manual mode)
# ---------------------------------------------------------------------------


class IntegrationSession:
    """Holds the trace context and handler for one test."""

    def __init__(self, ctx, handler):
        self.ctx = ctx
        self.handler = handler


@pytest.fixture
async def langchain_session():
    """Creates a TraceContext + LangChainTracingHandler for manual-mode tests.

    The context is active during the test body. Use ctx.get_events() to
    read captured events non-destructively. The context exits during fixture
    teardown (emitting AGENT_END).
    """
    from agent_debugger_sdk.adapters.langchain import LangChainTracingHandler
    from agent_debugger_sdk.core.context import TraceContext

    session_id = f"integ-{uuid.uuid4().hex[:12]}"
    ctx = TraceContext(
        session_id=session_id,
        agent_name="integration-test",
        framework="langchain",
    )
    handler = LangChainTracingHandler(session_id=session_id)

    sess = IntegrationSession(ctx, handler)

    async with ctx:
        handler.set_context(ctx)
        yield sess

    # Best-effort cleanup of global buffer
    try:
        from collector.buffer import get_event_buffer

        await get_event_buffer().flush(session_id)
    except Exception:
        pass
