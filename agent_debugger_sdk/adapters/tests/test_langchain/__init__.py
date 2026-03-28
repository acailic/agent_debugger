"""Tests for LangChain adapter.

This package contains test modules split by responsibility:
- test_langchain_mocks: Shared mock utilities and registration tests
- test_langchain_handler_*: Tests for LangChainTracingHandler by functionality
  - test_langchain_handler_init: Initialization and context tests
  - test_langchain_handler_llm: LLM callback tests
  - test_langchain_handler_tool: Tool callback tests
  - test_langchain_handler_chain: Chain callback tests
  - test_langchain_handler_edge_cases: Edge cases and error handling
- test_langchain_adapter: Tests for LangChainAdapter functionality
- test_langchain_error_boundaries: Tests for error boundary handling

For backward compatibility, all test classes are re-exported here.
"""

# Re-export all test classes for backward compatibility
from .test_langchain_adapter import TestLangChainAdapter
from .test_langchain_error_boundaries import TestLangChainErrorBoundaries
from .test_langchain_handler_chain import TestLangChainTracingHandlerChain
from .test_langchain_handler_edge_cases import TestLangChainTracingHandlerEdgeCases
from .test_langchain_handler_init import TestLangChainTracingHandlerInit
from .test_langchain_handler_llm import TestLangChainTracingHandlerLLM
from .test_langchain_handler_tool import TestLangChainTracingHandlerTool
from .test_langchain_mocks import MockGeneration, MockLLMResult, test_register_auto_patch_registers_langchain_adapter


# For backward compatibility, combine handler classes into single namespace
class TestLangChainTracingHandler(
    TestLangChainTracingHandlerInit,
    TestLangChainTracingHandlerLLM,
    TestLangChainTracingHandlerTool,
    TestLangChainTracingHandlerChain,
    TestLangChainTracingHandlerEdgeCases,
):
    """Combined test class for backward compatibility."""
    pass


__all__ = [
    "TestLangChainTracingHandler",
    "TestLangChainAdapter",
    "TestLangChainErrorBoundaries",
    "MockGeneration",
    "MockLLMResult",
    "test_register_auto_patch_registers_langchain_adapter",
]
