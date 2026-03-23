"""Ingestion-time redaction pipeline."""
from __future__ import annotations

import copy
import json
from dataclasses import fields
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent
from redaction.patterns import PII_PATTERNS, REPLACEMENT_MAP

# Fields that contain prompt/response content
PROMPT_FIELDS = {"content", "messages", "prompts", "result", "arguments"}
TOOL_PAYLOAD_FIELDS = {"result", "arguments"}
TRUNCATION_PRIORITY_FIELDS = {
    "content",
    "messages",
    "prompts",
    "result",
    "arguments",
    "reasoning",
    "tool_calls",
    "evidence",
}
TRUNCATED_MARKER = "[TRUNCATED]"
BASE_EVENT_FIELDS = {
    "id",
    "session_id",
    "parent_id",
    "event_type",
    "timestamp",
    "name",
    "data",
    "metadata",
    "importance",
    "upstream_event_ids",
}


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
        payload = self._build_event_payload(redacted)

        if self.redact_prompts and event.event_type in (
            EventType.LLM_REQUEST, EventType.LLM_RESPONSE,
        ):
            payload = self._redact_fields(payload, PROMPT_FIELDS)

        if self.redact_tool_payloads and event.event_type in (
            EventType.TOOL_CALL, EventType.TOOL_RESULT,
        ):
            payload = self._redact_fields(payload, TOOL_PAYLOAD_FIELDS)

        if self.redact_pii:
            payload = self._scrub_pii(payload)

        truncated = False
        if self.max_payload_kb > 0:
            payload, truncated = self._truncate_payload(payload, self.max_payload_kb * 1024)

        self._apply_event_payload(redacted, payload)
        if truncated:
            redacted.metadata["_truncated"] = True

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

    def _build_event_payload(self, event: TraceEvent) -> dict[str, Any]:
        payload = copy.deepcopy(event.data)
        for field_info in fields(event):
            if field_info.name in BASE_EVENT_FIELDS:
                continue
            payload[field_info.name] = copy.deepcopy(getattr(event, field_info.name))
        return payload

    def _apply_event_payload(self, event: TraceEvent, payload: dict[str, Any]) -> None:
        remaining = copy.deepcopy(payload)
        for field_info in fields(event):
            if field_info.name in BASE_EVENT_FIELDS:
                continue
            if field_info.name in remaining:
                setattr(event, field_info.name, remaining.pop(field_info.name))
        event.data = remaining

    def _truncate_payload(self, payload: dict[str, Any], max_bytes: int) -> tuple[dict[str, Any], bool]:
        if self._payload_size_bytes(payload) <= max_bytes:
            return payload, False

        truncated = copy.deepcopy(payload)
        did_truncate = False

        for priority_only in (True, False):
            while self._payload_size_bytes(truncated) > max_bytes:
                candidates = self._collect_string_candidates(truncated, priority_only=priority_only)
                if not candidates:
                    break

                changed = False
                for path, value in candidates:
                    current_size = self._payload_size_bytes(truncated)
                    excess = current_size - max_bytes
                    replacement = self._truncate_string(value, excess)
                    if replacement == value:
                        continue
                    self._set_nested_value(truncated, path, replacement)
                    did_truncate = True
                    changed = True
                    if self._payload_size_bytes(truncated) <= max_bytes:
                        return truncated, True

                if not changed:
                    break

        while self._payload_size_bytes(truncated) > max_bytes:
            container_candidates = self._collect_container_candidates(truncated)
            if not container_candidates:
                break
            self._set_nested_value(truncated, container_candidates[0], TRUNCATED_MARKER)
            did_truncate = True

        return truncated, did_truncate

    def _collect_string_candidates(
        self,
        obj: Any,
        path: tuple[str | int, ...] = (),
        *,
        priority_only: bool,
    ) -> list[tuple[tuple[str | int, ...], str]]:
        candidates: list[tuple[tuple[str | int, ...], str]] = []
        if isinstance(obj, str):
            if not path:
                return []
            is_priority = any(
                isinstance(part, str) and part in TRUNCATION_PRIORITY_FIELDS
                for part in path
            )
            if not priority_only or is_priority:
                candidates.append((path, obj))
            return candidates

        if isinstance(obj, dict):
            for key, value in obj.items():
                candidates.extend(self._collect_string_candidates(value, path + (key,), priority_only=priority_only))
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                candidates.extend(self._collect_string_candidates(value, path + (index,), priority_only=priority_only))

        candidates.sort(key=lambda item: len(item[1].encode("utf-8")), reverse=True)
        return candidates

    def _collect_container_candidates(
        self,
        payload: dict[str, Any],
    ) -> list[tuple[str | int, ...]]:
        candidates: list[tuple[tuple[str | int, ...], int]] = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                candidates.append(((key,), len(self._serialize_json(value).encode("utf-8"))))

        candidates.sort(
            key=lambda item: (
                0 if item[0][0] in TRUNCATION_PRIORITY_FIELDS else 1,
                -item[1],
            )
        )
        return [path for path, _ in candidates]

    def _truncate_string(self, value: str, excess_bytes: int) -> str:
        marker_bytes = len(TRUNCATED_MARKER.encode("utf-8"))
        value_bytes = value.encode("utf-8")
        if len(value_bytes) <= marker_bytes:
            return value

        target_bytes = max(len(value_bytes) - excess_bytes, 0)
        allowed_bytes = max(target_bytes - marker_bytes, 0)
        if allowed_bytes <= 0:
            return TRUNCATED_MARKER

        truncated_bytes = value_bytes[:allowed_bytes]
        truncated_text = truncated_bytes.decode("utf-8", errors="ignore")
        if not truncated_text:
            return TRUNCATED_MARKER
        return f"{truncated_text}{TRUNCATED_MARKER}"

    def _set_nested_value(self, obj: Any, path: tuple[str | int, ...], value: Any) -> None:
        target = obj
        for segment in path[:-1]:
            target = target[segment]
        target[path[-1]] = value

    def _payload_size_bytes(self, payload: dict[str, Any]) -> int:
        return len(self._serialize_json(payload).encode("utf-8"))

    def _serialize_json(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)
