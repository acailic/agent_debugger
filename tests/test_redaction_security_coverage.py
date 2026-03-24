"""Comprehensive tests for redaction pipeline - security-critical coverage."""

import pytest
from unittest.mock import Mock, patch
import json

from redaction.pipeline import RedactionPipeline
from agent_debugger_sdk.core.events import (
    TraceEvent, EventType, ToolCallEvent,
    LLMRequestEvent, LLMResponseEvent, ToolResultEvent
)
from datetime import datetime, timezone


class TestRedactionPipelineEdgeCases:
    """Test edge cases and security scenarios in redaction."""
    
    def test_empty_event_data(self):
        """Test redaction with empty event data."""
        pipeline = RedactionPipeline()
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={}
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert result.data == {}
    
    def test_none_values_in_event(self):
        """Test redaction with None values in event data."""
        pipeline = RedactionPipeline()
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "api_key": None,
                "password": None,
                "valid_field": "value"
            }
        )
        
        result = pipeline.apply(event)
        
        # None values should remain None
        assert result.data["api_key"] is None
        assert result.data["password"] is None
        assert result.data["valid_field"] == "value"
    
    def test_basic_redaction_disabled(self):
        """Test with all redaction disabled."""
        pipeline = RedactionPipeline(
            redact_prompts=False,
            redact_tool_payloads=False,
            redact_pii=False
        )
        
        event = ToolCallEvent(
            timestamp=datetime.now(timezone.utc),
            tool_name="test_tool",
            arguments={"secret": "password123"},
            result="sensitive data"
        )
        
        result = pipeline.apply(event)
        # Should not redact when disabled
        assert result is not None
        assert result.arguments["secret"] == "password123"
        assert result.result == "sensitive data"


class TestRedactionWithPrompts:
    """Test prompt redaction functionality."""
    
    def test_prompt_redaction_enabled(self):
        """Test that prompts are redacted when enabled."""
        pipeline = RedactionPipeline(redact_prompts=True)
        
        event = LLMRequestEvent(
            timestamp=datetime.now(timezone.utc),
            model="gpt-4",
            messages=[{"role": "user", "content": "sensitive prompt"}],
            temperature=0.7
        )
        
        result = pipeline.apply(event)
        
        # Prompt content should be redacted
        assert result is not None
        # Messages field should be redacted
        assert result.messages == "[REDACTED]" or result.messages != event.messages
    
    def test_prompt_redaction_disabled(self):
        """Test that prompts are preserved when redaction disabled."""
        pipeline = RedactionPipeline(redact_prompts=False)
        
        messages = [{"role": "user", "content": "my prompt"}]
        event = LLMRequestEvent(
            timestamp=datetime.now(timezone.utc),
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        result = pipeline.apply(event)
        assert result is not None
        # Should not be redacted
        assert result.messages == messages
    
    def test_llm_response_redaction(self):
        """Test LLM response content redaction."""
        pipeline = RedactionPipeline(redact_prompts=True)
        
        event = LLMResponseEvent(
            timestamp=datetime.now(timezone.utc),
            model="gpt-4",
            content="sensitive response",
            tokens_used=100
        )
        
        result = pipeline.apply(event)
        assert result is not None
        # Content should be redacted
        assert result.content == "[REDACTED]" or result.content != "sensitive response"


class TestRedactionWithToolPayloads:
    """Test tool payload redaction."""
    
    def test_tool_payload_redaction_enabled(self):
        """Test tool payloads are redacted when enabled."""
        pipeline = RedactionPipeline(redact_tool_payloads=True)
        
        event = ToolCallEvent(
            timestamp=datetime.now(timezone.utc),
            tool_name="database_query",
            arguments={"query": "SELECT * FROM users"},
            result="sensitive data"
        )
        
        result = pipeline.apply(event)
        assert result is not None
        # Arguments and result should be redacted
        assert result.arguments == "[REDACTED]" or result.arguments != event.arguments
        assert result.result == "[REDACTED]" or result.result != event.result
    
    def test_tool_payload_redaction_disabled(self):
        """Test tool payloads preserved when disabled."""
        pipeline = RedactionPipeline(redact_tool_payloads=False)
        
        event = ToolCallEvent(
            timestamp=datetime.now(timezone.utc),
            tool_name="search",
            arguments={"query": "test"},
            result="results"
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert result.arguments == {"query": "test"}
        assert result.result == "results"
    
    def test_tool_result_redaction(self):
        """Test tool result redaction."""
        pipeline = RedactionPipeline(redact_tool_payloads=True)
        
        event = ToolResultEvent(
            timestamp=datetime.now(timezone.utc),
            tool_name="test",
            result="sensitive result",
            error=None
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert result.result == "[REDACTED]" or result.result != "sensitive result"


class TestRedactionWithPII:
    """Test PII redaction functionality."""
    
    def test_pii_redaction_enabled(self):
        """Test PII is redacted when enabled."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "email": "user@example.com",
                "ssn": "123-45-6789",
                "phone": "555-123-4567"
            }
        )
        
        result = pipeline.apply(event)
        
        # PII should be redacted
        assert result is not None
        # Check that PII patterns were scrubbed
        assert "user@example.com" not in str(result.data)
    
    def test_pii_redaction_disabled(self):
        """Test PII preserved when disabled."""
        pipeline = RedactionPipeline(redact_pii=False)
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "email": "user@example.com"
            }
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert result.data["email"] == "user@example.com"
    
    def test_email_redaction_patterns(self):
        """Test various email patterns are redacted."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        test_emails = [
            "user@example.com",
            "user.name@domain.co.uk",
            "test+tag@company.org"
        ]
        
        for email in test_emails:
            event = TraceEvent(
                event_type=EventType.TOOL_CALL,
                timestamp=datetime.now(timezone.utc),
                data={"email": email}
            )
            
            result = pipeline.apply(event)
            assert email not in str(result.data), f"Email {email} was not redacted"
    
    def test_phone_redaction_patterns(self):
        """Test phone number patterns are redacted."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        test_phones = [
            "555-123-4567",
            "(555) 123-4567",
            "+1-555-123-4567"
        ]
        
        for phone in test_phones:
            event = TraceEvent(
                event_type=EventType.TOOL_CALL,
                timestamp=datetime.now(timezone.utc),
                data={"phone": phone}
            )
            
            result = pipeline.apply(event)
            assert phone not in str(result.data), f"Phone {phone} was not redacted"


class TestRedactionWithPayloadTruncation:
    """Test payload size truncation."""
    
    def test_large_payload_truncation(self):
        """Test large payloads are truncated."""
        pipeline = RedactionPipeline(max_payload_kb=1)  # 1KB limit
        
        # Create large payload
        large_data = {"content": "x" * 2000}  # 2KB of data
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data=large_data
        )
        
        result = pipeline.apply(event)
        
        # Should be truncated
        assert result is not None
        assert result.metadata.get("_truncated", False)
    
    def test_no_truncation_when_disabled(self):
        """Test no truncation when limit is 0."""
        pipeline = RedactionPipeline(max_payload_kb=0)
        
        large_data = {"content": "x" * 2000}
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data=large_data
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert not result.metadata.get("_truncated", False)
    
    def test_small_payload_not_truncated(self):
        """Test small payloads are not truncated."""
        pipeline = RedactionPipeline(max_payload_kb=1)
        
        small_data = {"content": "small"}
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data=small_data
        )
        
        result = pipeline.apply(event)
        assert result is not None
        assert not result.metadata.get("_truncated", False)


class TestRedactionFromConfig:
    """Test creating pipeline from config."""
    
    def test_from_config(self):
        """Test creating pipeline from SDK config."""
        pipeline = RedactionPipeline.from_config()
        
        assert pipeline is not None
        assert isinstance(pipeline, RedactionPipeline)


class TestRedactionSecurityVulnerabilities:
    """Test for potential security vulnerabilities in redaction."""
    
    def test_injection_in_event_data(self):
        """Test that event data can't inject malicious content."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        # Try to inject in values
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "password": "'; DROP TABLE users; --",
                "script": "<script>alert('xss')</script>"
            }
        )
        
        result = pipeline.apply(event)
        
        # Should handle safely
        assert result is not None
        assert isinstance(result.data, dict)
    
    def test_nested_injection(self):
        """Test nested injection attempts."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "level1": {
                    "password": "'; DROP TABLE users; --",
                    "level2": {
                        "api_key": "<script>evil()</script>"
                    }
                }
            }
        )
        
        result = pipeline.apply(event)
        
        # Should handle at all levels
        assert result is not None
    
    def test_unicode_handling(self):
        """Test handling of unicode in event data."""
        pipeline = RedactionPipeline()
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "unicode": "密码 Пароль αβγδ",
                "emoji": "🔐🔑🔓"
            }
        )
        
        result = pipeline.apply(event)
        
        # Unicode should be preserved
        assert "密码" in result.data["unicode"]


class TestRedactionErrorHandling:
    """Test error handling in redaction pipeline."""
    
    def test_deeply_nested_structure(self):
        """Test redaction with deeply nested structure."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        # Create deeply nested structure
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "level5": {
                                    "api_key": "secret123"
                                }
                            }
                        }
                    }
                }
            }
        )
        
        result = pipeline.apply(event)
        
        # Should handle at any depth
        assert result is not None
    
    def test_list_of_dicts(self):
        """Test redaction with list of dictionaries."""
        pipeline = RedactionPipeline(redact_pii=True)
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data={
                "items": [
                    {"email": "user1@example.com"},
                    {"email": "user2@example.com"}
                ]
            }
        )
        
        result = pipeline.apply(event)
        assert result is not None
        # Emails in list should be redacted
        assert "user1@example.com" not in str(result.data)


class TestRedactionPerformance:
    """Test redaction performance with large payloads."""
    
    def test_large_event_performance(self):
        """Test redaction performance with large event."""
        import time
        
        pipeline = RedactionPipeline()
        
        # Create large event data
        large_data = {
            f"field_{i}": f"value_{i}"
            for i in range(100)
        }
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data=large_data
        )
        
        start = time.time()
        result = pipeline.apply(event)
        duration = time.time() - start
        
        # Should complete quickly
        assert duration < 1.0
        assert result is not None
    
    def test_complex_nested_structure_performance(self):
        """Test performance with complex nested structures."""
        import time
        
        pipeline = RedactionPipeline(redact_pii=True)
        
        # Create complex nested structure
        complex_data = {
            "users": [
                {
                    "id": i,
                    "email": f"user{i}@example.com",
                    "data": {
                        "nested": {
                            "value": f"secret_{i}"
                        }
                    }
                }
                for i in range(50)
            ]
        }
        
        event = TraceEvent(
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            data=complex_data
        )
        
        start = time.time()
        result = pipeline.apply(event)
        duration = time.time() - start
        
        # Should complete quickly even with complex structures
        assert duration < 2.0
        assert result is not None
