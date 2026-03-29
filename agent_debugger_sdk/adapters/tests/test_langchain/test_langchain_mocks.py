"""Shared mock utilities for LangChain adapter tests."""

from __future__ import annotations


class MockGeneration:
    """Mock LangChain generation."""

    def __init__(self, text: str):
        self.text = text


class MockLLMResult:
    """Mock LangChain LLM result."""

    def __init__(self, text: str = "Hello!"):
        self.generations = [[MockGeneration(text)]]
        self.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_register_auto_patch_registers_langchain_adapter():
    """Test that register_auto_patch properly registers the LangChain adapter."""
    from agent_debugger_sdk.adapters.langchain import register_auto_patch
    from agent_debugger_sdk.auto_patch.registry import get_registry

    registry = get_registry()
    original_adapters = list(registry._adapters)
    try:
        register_auto_patch()
        assert any(a.name == "langchain" for a in registry._adapters)
    finally:
        registry._adapters[:] = original_adapters
