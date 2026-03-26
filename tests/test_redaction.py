"""Tests for PII redaction pipeline."""

import json

from agent_debugger_sdk.core.events import LLMResponseEvent
from redaction.patterns import PII_PATTERNS
from redaction.pipeline import RedactionPipeline


def test_redact_prompts(make_llm_event):
    pipeline = RedactionPipeline(redact_prompts=True)
    event = make_llm_event("The secret answer is 42")
    redacted = pipeline.apply(event)
    assert redacted.data["content"] == "[REDACTED]"
    assert redacted.data["model"] == "gpt-4"  # non-prompt fields preserved


def test_redact_pii_email(make_llm_event):
    pipeline = RedactionPipeline(redact_pii=True)
    event = make_llm_event("Contact john@example.com for details")
    redacted = pipeline.apply(event)
    assert "john@example.com" not in redacted.data["content"]
    assert "[EMAIL]" in redacted.data["content"]


def test_no_redaction_by_default(make_llm_event):
    pipeline = RedactionPipeline()
    event = make_llm_event("Contact john@example.com")
    redacted = pipeline.apply(event)
    assert redacted.data["content"] == "Contact john@example.com"


def test_payload_is_truncated_when_it_exceeds_max_payload_size():
    pipeline = RedactionPipeline(max_payload_kb=1)
    event = LLMResponseEvent(
        session_id="s1",
        name="llm_response",
        content="x" * 5000,
        tool_calls=[{"name": "lookup", "content": "y" * 5000}],
        metadata={},
    )

    redacted = pipeline.apply(event)
    payload = dict(redacted.data)
    payload["content"] = redacted.content
    payload["tool_calls"] = redacted.tool_calls

    assert redacted.metadata["_truncated"] is True
    assert redacted.content.endswith("[TRUNCATED]")
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 1024


def test_payload_under_limit_is_not_marked_truncated():
    pipeline = RedactionPipeline(max_payload_kb=1)
    event = LLMResponseEvent(
        session_id="s1",
        name="llm_response",
        content="short",
        metadata={},
    )

    redacted = pipeline.apply(event)

    assert "_truncated" not in redacted.metadata
    assert redacted.content == "short"


def test_pii_patterns_detect_email():
    assert PII_PATTERNS["email"].search("user@example.com")


def test_pii_patterns_detect_phone():
    assert PII_PATTERNS["phone"].search("+1-555-123-4567")
