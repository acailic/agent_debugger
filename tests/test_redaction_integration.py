"""Integration test for redaction pipeline integration."""

import pytest
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import TraceEvent
from redaction.pipeline import RedactionPipeline


@pytest.mark.asyncio
async def test_redaction_applied_before_persist():
    """Events should be redacted before persistence."""
    pipeline = RedactionPipeline(redact_pii=True)
    event = TraceEvent(
        session_id="s1", parent_id=None, event_type=EventType.LLM_RESPONSE,
        name="test", importance=0.5, upstream_event_ids=[],
        data={"content": "Email me at test@example.com"},
        metadata={},
    )
    redacted = pipeline.apply(event)
    assert "[EMAIL]" in redacted.data["content"]
    assert "test@example.com" not in redacted.data["content"]
