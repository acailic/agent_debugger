"""Ingestion-time redaction pipeline."""
from __future__ import annotations

import copy
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent, EventType
from redaction.patterns import PII_PATTERNS, REPLACEMENT_MAP

# Fields that contain prompt/response content
PROMPT_FIELDS = {"content", "messages", "prompts", "result", "arguments"}
TOOL_PAYLOAD_FIELDS = {"result", "arguments"}


class RedactionPipeline:
    def __init__(
        self,
        redact_prompts: bool = False,
        redact_tool_payloads: bool = False,
        redact_pii: bool = False,
        max_payload_kb: int = 0,
    ) -> None:
        self.redact_prompts = redact_prompts
        self.redact_tool_payloads = redact_tool_payloads
        self.redact_pii = redact_pii
        self.max_payload_kb = max_payload_kb

    def apply(self, event: TraceEvent) -> TraceEvent:
        # NOTE: We use copy + mutation instead of dataclasses.replace()
        # because TraceEvent subclasses have kw_only=True with extra
        # required fields that replace() cannot handle from a base reference.
        redacted = copy.deepcopy(event)

        if self.redact_prompts and event.event_type in (
            EventType.LLM_REQUEST, EventType.LLM_RESPONSE,
        ):
            redacted.data = self._redact_fields(redacted.data, PROMPT_FIELDS)

        if self.redact_tool_payloads and event.event_type in (
            EventType.TOOL_CALL, EventType.TOOL_RESULT,
        ):
            redacted.data = self._redact_fields(redacted.data, TOOL_PAYLOAD_FIELDS)

        if self.redact_pii:
            redacted.data = self._scrub_pii(redacted.data)

        return redacted

    def _redact_fields(self, data: dict, fields: set[str]) -> dict:
        for key in fields:
            if key in data:
                data[key] = "[REDACTED]"
        return data

    def _scrub_pii(self, obj: Any) -> Any:
        if isinstance(obj, str):
            for pattern_name, pattern in PII_PATTERNS.items():
                obj = pattern.sub(REPLACEMENT_MAP[pattern_name], obj)
            return obj
        if isinstance(obj, dict):
            return {k: self._scrub_pii(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._scrub_pii(item) for item in obj]
        return obj