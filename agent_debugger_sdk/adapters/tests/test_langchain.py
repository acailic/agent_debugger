"""Tests for LangChain adapter.

This module now re-exports tests from the langchain test package for better modularity.
The original tests have been split into:
- agent_debugger_sdk.adapters.tests.langchain.fixtures - Mock classes
- agent_debugger_sdk.adapters.tests.langchain.test_handler - Handler tests
- agent_debugger_sdk.adapters.tests.langchain.test_adapter - Adapter tests
- agent_debugger_sdk.adapters.tests.langchain.test_errors - Error boundary tests

Note: Test discovery will still find all tests in the langchain package subdirectory.
"""

# Re-export for backward compatibility (pytest will discover tests in the package)
from agent_debugger_sdk.adapters.tests.langchain.test_adapter import TestLangChainAdapter
from agent_debugger_sdk.adapters.tests.langchain.test_errors import TestLangChainErrorBoundaries
from agent_debugger_sdk.adapters.tests.langchain.test_handler import TestLangChainTracingHandler

__all__ = [
    "TestLangChainTracingHandler",
    "TestLangChainAdapter",
    "TestLangChainErrorBoundaries",
]
