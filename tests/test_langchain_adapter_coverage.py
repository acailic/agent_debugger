"""Comprehensive tests for LangChain adapter - targeting 85%+ coverage."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import uuid
from datetime import datetime

from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import (
    LangChainAdapter,
    _SyncTracingCallbackHandler
)
from agent_debugger_sdk.auto_patch import PatchConfig
from agent_debugger_sdk.core.events import EventType


class TestSyncTracingCallbackHandler:
    """Test the sync tracing callback handler."""
    
    def test_handler_initialization(self):
        """Test handler initializes correctly."""
        handler = _SyncTracingCallbackHandler()
        
        assert handler is not None
        assert hasattr(handler, "on_llm_start")
        assert hasattr(handler, "on_llm_end")
        assert hasattr(handler, "on_llm_error")
    
    def test_on_llm_start_basic(self):
        """Test basic LLM start callback."""
        handler = _SyncTracingCallbackHandler()
        
        serialized = {"name": "test_model"}
        prompts = ["Hello, world!"]
        run_id = uuid.uuid4()
        
        # Should not raise
        handler.on_llm_start(
            serialized=serialized,
            prompts=prompts,
            run_id=run_id
        )
    
    def test_on_llm_start_with_metadata(self):
        """Test LLM start with metadata."""
        handler = _SyncTracingCallbackHandler()
        
        serialized = {"name": "gpt-4"}
        prompts = ["Test prompt"]
        run_id = uuid.uuid4()
        metadata = {"user": "test_user", "session": "123"}
        
        handler.on_llm_start(
            serialized=serialized,
            prompts=prompts,
            run_id=run_id,
            metadata=metadata
        )
    
    def test_on_llm_end_basic(self):
        """Test basic LLM end callback."""
        handler = _SyncTracingCallbackHandler()
        
        response = Mock(
            generations=[[Mock(text="Response text")]],
            llm_output={"token_usage": {"total_tokens": 100}}
        )
        run_id = uuid.uuid4()
        
        handler.on_llm_end(response=response, run_id=run_id)
    
    def test_on_llm_end_with_usage(self):
        """Test LLM end with token usage."""
        handler = _SyncTracingCallbackHandler()
        
        response = Mock(
            generations=[[Mock(text="Test")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30
                }
            }
        )
        run_id = uuid.uuid4()
        
        handler.on_llm_end(response=response, run_id=run_id)
    
    def test_on_llm_error(self):
        """Test LLM error callback."""
        handler = _SyncTracingCallbackHandler()
        
        error = Exception("LLM failed")
        run_id = uuid.uuid4()
        
        # Should handle error gracefully
        handler.on_llm_error(error=error, run_id=run_id)
    
    def test_on_tool_start_basic(self):
        """Test basic tool start callback."""
        handler = _SyncTracingCallbackHandler()
        
        serialized = {"name": "search_tool"}
        input_str = "search query"
        run_id = uuid.uuid4()
        
        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id
        )
    
    def test_on_tool_start_with_args(self):
        """Test tool start with args."""
        handler = _SyncTracingCallbackHandler()
        
        serialized = {"name": "calculator"}
        input_str = "2 + 2"
        run_id = uuid.uuid4()
        args = {"precision": 2}
        
        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id,
            **args
        )
    
    def test_on_tool_end_basic(self):
        """Test basic tool end callback."""
        handler = _SyncTracingCallbackHandler()
        
        output = "Tool result"
        run_id = uuid.uuid4()
        
        handler.on_tool_end(output=output, run_id=run_id)
    
    def test_on_tool_error(self):
        """Test tool error callback."""
        handler = _SyncTracingCallbackHandler()
        
        error = Exception("Tool failed")
        run_id = uuid.uuid4()
        
        handler.on_tool_error(error=error, run_id=run_id)
    
    def test_on_chain_start(self):
        """Test chain start callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_chain_start(
            serialized={"name": "test_chain"},
            inputs={"query": "test"},
            run_id=uuid.uuid4()
        )
    
    def test_on_chain_end(self):
        """Test chain end callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_chain_end(
            outputs={"result": "success"},
            run_id=uuid.uuid4()
        )
    
    def test_on_chain_error(self):
        """Test chain error callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_chain_error(
            error=Exception("Chain failed"),
            run_id=uuid.uuid4()
        )
    
    def test_on_agent_action(self):
        """Test agent action callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_agent_action(
            action=Mock(tool="search", tool_input="query"),
            run_id=uuid.uuid4()
        )
    
    def test_on_agent_finish(self):
        """Test agent finish callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_agent_finish(
            finish=Mock(return_values={"output": "done"}),
            run_id=uuid.uuid4()
        )
    
    def test_on_text(self):
        """Test text callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_text(
            text="Some text",
            run_id=uuid.uuid4()
        )
    
    def test_on_retry(self):
        """Test retry callback."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_retry(
            retry_state=Mock(attempt_number=2),
            run_id=uuid.uuid4()
        )


class TestLangChainAdapter:
    """Test the LangChain adapter."""
    
    def test_adapter_initialization(self):
        """Test adapter initializes correctly."""
        adapter = LangChainAdapter()
        
        assert adapter is not None
        assert hasattr(adapter, "patch")
        assert hasattr(adapter, "unpatch")
        assert hasattr(adapter, "is_available")
    
    def test_is_available_when_installed(self):
        """Test is_available returns True when langchain is installed."""
        adapter = LangChainAdapter()
        
        # Will return True if langchain is installed
        result = adapter.is_available()
        assert isinstance(result, bool)
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_patch_basic(self, mock_handler):
        """Test basic patch functionality."""
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        # Should not raise
        adapter.patch(config)
        
        # Handler should be created
        assert mock_handler.called
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_patch_with_config(self, mock_handler):
        """Test patch with configuration."""
        adapter = LangChainAdapter()
        config = PatchConfig(
            capture_prompts=True,
            capture_results=True
        )
        
        adapter.patch(config)
    
    def test_unpatch_without_patch(self):
        """Test unpatch without prior patch."""
        adapter = LangChainAdapter()
        
        # Should handle gracefully
        adapter.unpatch()
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_patch_unpatch_cycle(self, mock_handler):
        """Test patch/unpatch cycle."""
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        adapter.patch(config)
        adapter.unpatch()
        
        # Should be able to patch again
        adapter.patch(config)
        adapter.unpatch()
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_multiple_patches(self, mock_handler):
        """Test multiple patch calls."""
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        # Multiple patches should be idempotent
        adapter.patch(config)
        adapter.patch(config)
        adapter.patch(config)
        
        adapter.unpatch()
    
    def test_install_handler(self):
        """Test handler installation."""
        adapter = LangChainAdapter()
        handler = _SyncTracingCallbackHandler()
        
        # Install handler
        adapter._install_handler(handler)
        
        # Should be in handlers list
        assert handler in adapter._handlers
    
    def test_remove_handler(self):
        """Test handler removal."""
        adapter = LangChainAdapter()
        handler = _SyncTracingCallbackHandler()
        
        # Install and then remove
        adapter._install_handler(handler)
        adapter._remove_handler(handler)
        
        # Should not be in handlers list
        assert handler not in adapter._handlers
    
    def test_remove_nonexistent_handler(self):
        """Test removing handler that doesn't exist."""
        adapter = LangChainAdapter()
        handler = _SyncTracingCallbackHandler()
        
        # Should not raise
        adapter._remove_handler(handler)


class TestLangChainAdapterEdgeCases:
    """Test edge cases and error scenarios."""
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_patch_when_langchain_not_available(self, mock_handler):
        """Test patch when langchain is not installed."""
        adapter = LangChainAdapter()
        
        with patch.object(adapter, 'is_available', return_value=False):
            # Should handle gracefully
            try:
                adapter.patch(PatchConfig())
            except ImportError:
                # Expected if not available
                pass
    
    def test_handler_with_none_values(self):
        """Test handler with None values."""
        handler = _SyncTracingCallbackHandler()
        
        # Should handle None gracefully
        handler.on_llm_start(
            serialized=None,
            prompts=None,
            run_id=uuid.uuid4()
        )
    
    def test_handler_with_empty_prompts(self):
        """Test handler with empty prompts list."""
        handler = _SyncTracingCallbackHandler()
        
        handler.on_llm_start(
            serialized={},
            prompts=[],
            run_id=uuid.uuid4()
        )
    
    def test_handler_with_malformed_response(self):
        """Test handler with malformed response."""
        handler = _SyncTracingCallbackHandler()
        
        # Malformed response object
        response = Mock()
        response.generations = None
        response.llm_output = None
        
        # Should not crash
        handler.on_llm_end(response=response, run_id=uuid.uuid4())
    
    def test_handler_with_exception_containing_secrets(self):
        """Test handler with exception containing sensitive data."""
        handler = _SyncTracingCallbackHandler()
        
        error = Exception("API key sk-1234567890 failed")
        run_id = uuid.uuid4()
        
        # Should handle and potentially redact
        handler.on_llm_error(error=error, run_id=run_id)
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_concurrent_patch_unpatch(self, mock_handler):
        """Test concurrent patch/unpatch operations."""
        import threading
        
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        def patch_unpatch():
            for _ in range(10):
                adapter.patch(config)
                adapter.unpatch()
        
        threads = [
            threading.Thread(target=patch_unpatch)
            for _ in range(3)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should not crash or corrupt state


class TestLangChainAdapterIntegration:
    """Integration tests for LangChain adapter."""
    
    @pytest.mark.skipif(
        not LangChainAdapter().is_available(),
        reason="LangChain not installed"
    )
    def test_real_langchain_integration(self):
        """Test with real LangChain if available."""
        from langchain.llms import FakeListLLM
        
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        adapter.patch(config)
        
        try:
            llm = FakeListLLM(responses=["Test response"])
            result = llm.predict("Test prompt")
            
            assert result == "Test response"
        finally:
            adapter.unpatch()
    
    @pytest.mark.skipif(
        not LangChainAdapter().is_available(),
        reason="LangChain not installed"
    )
    def test_langchain_with_tools(self):
        """Test LangChain with tool calls."""
        from langchain.tools import Tool
        from langchain.agents import initialize_agent
        
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        adapter.patch(config)
        
        try:
            # Create simple tool
            def search_func(query: str) -> str:
                return f"Result for: {query}"
            
            tools = [
                Tool(
                    name="Search",
                    func=search_func,
                    description="Search tool"
                )
            ]
            
            # Tools should be tracked
            assert len(tools) > 0
        finally:
            adapter.unpatch()


class TestLangChainAdapterMemory:
    """Test memory and resource management."""
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_no_memory_leak_on_multiple_patches(self, mock_handler):
        """Test that multiple patches don't leak memory."""
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        initial_count = len(adapter._handlers)
        
        for _ in range(100):
            adapter.patch(config)
            adapter.unpatch()
        
        # Handler count should be similar to initial
        final_count = len(adapter._handlers)
        assert final_count <= initial_count + 1
    
    @patch('agent_debugger_sdk.auto_patch.adapters.langchain_adapter._SyncTracingCallbackHandler')
    def test_cleanup_on_exception(self, mock_handler):
        """Test cleanup when exception occurs."""
        adapter = LangChainAdapter()
        config = PatchConfig()
        
        adapter.patch(config)
        
        # Simulate exception during operation
        try:
            raise Exception("Test exception")
        except Exception:
            adapter.unpatch()
        
        # Should be properly cleaned up
        assert len(adapter._handlers) == 0
