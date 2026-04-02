"""Reusable trace event recording helpers."""

from __future__ import annotations

import abc
import re
from typing import Any

from .events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    RiskLevel,
    SafetyCheckEvent,
    SafetyOutcome,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)

__all__ = ["RecordingMixin"]


def _enhance_error_message(error_message: str) -> str:
    """Append helpful suggestions to error messages based on common patterns.

    Args:
        error_message: The original error message.

    Returns:
        The enhanced error message with suggestions appended.
    """
    suggestions = []

    # Check for common error patterns and provide specific suggestions
    patterns = [
        (r"connection refused", "The server may be down. Check that the agent_debugger server is running."),  # noqa: E501
        (
            r"connection.*reset",
            "The connection was unexpectedly closed. This may indicate a network issue or server restart.",
        ),  # noqa: E501
        (
            r"timeout",
            "The request took too long. Consider increasing timeout settings or checking network connectivity.",
        ),  # noqa: E501
        (r"401|unauthorized|authentication", "Check your API key configuration in agent_debugger_sdk.config.init()."),  # noqa: E501
        (
            r"403|forbidden|access denied",
            "Your API key may not have permission for this operation. Verify your credentials.",
        ),  # noqa: E501
        (r"404|not found", "The API endpoint was not found. Check that the server URL is correct."),
        (r"429|rate limit", "You are sending requests too quickly. Implement exponential backoff and retry."),
        (r"5\d{2}|server error", "The server encountered an error. This is typically a temporary issue. Please retry."),
        (r"no route to host", "Network connectivity issue. Check your internet connection and firewall settings."),  # noqa: E501
        (
            r"certificate|tls|ssl",
            "SSL/TLS certificate issue. Ensure the server certificate is valid or check system clock.",
        ),  # noqa: E501
        (r"dns.*not.*resolved|nxdomain", "DNS resolution failed. Verify the server hostname and DNS configuration."),  # noqa: E501
    ]

    message_lower = error_message.lower()
    for pattern, suggestion in patterns:
        if re.search(pattern, message_lower):
            suggestions.append(f" Suggestion: {suggestion}")

    if suggestions:
        # Deduplicate and join suggestions
        return error_message + "\n" + "\n".join(set(suggestions))
    return error_message


class RecordingMixin(abc.ABC):
    """Mixin that records typed trace events through a shared emitter."""

    session_id: str
    session: Any

    @abc.abstractmethod
    def _check_entered(self) -> None: ...

    @abc.abstractmethod
    def get_current_parent(self) -> str | None: ...

    @abc.abstractmethod
    async def _emit_event(self, event: TraceEvent) -> None: ...

    async def record_decision(
        self,
        reasoning: str,
        confidence: float,
        evidence: list[dict[str, Any]],
        chosen_action: str,
        evidence_event_ids: list[str] | None = None,
        upstream_event_ids: list[str] | None = None,
        alternatives: list[dict[str, Any]] | None = None,
        name: str = "decision",
    ) -> str:
        self._check_entered()

        event = DecisionEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            event_type=EventType.DECISION,
            name=name,
            reasoning=reasoning,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=evidence,
            evidence_event_ids=evidence_event_ids or [],
            alternatives=alternatives or [],
            chosen_action=chosen_action,
            importance=0.7,
            upstream_event_ids=upstream_event_ids or [],
        )
        await self._emit_event(event)
        return event.id

    async def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()

        event = ToolCallEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else self.get_current_parent(),
            event_type=EventType.TOOL_CALL,
            name=name or f"{tool_name}_call",
            tool_name=tool_name,
            arguments=arguments,
            importance=0.4,
            upstream_event_ids=upstream_event_ids or [],
        )
        await self._emit_event(event)
        return event.id

    async def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: float = 0,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()

        importance = 0.9 if error else 0.5
        if error:
            self.session.errors += 1

        event = ToolResultEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else self.get_current_parent(),
            event_type=EventType.TOOL_RESULT,
            name=name or f"{tool_name}_result",
            tool_name=tool_name,
            result=result,
            error=error,
            duration_ms=duration_ms,
            importance=importance,
            upstream_event_ids=upstream_event_ids or [],
        )

        self.session.tool_calls += 1
        await self._emit_event(event)
        return event.id

    async def record_llm_request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()

        event = LLMRequestEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else self.get_current_parent(),
            event_type=EventType.LLM_REQUEST,
            name=name or f"llm_request_{model}",
            model=model,
            messages=messages,
            tools=tools or [],
            settings=settings or {},
            importance=0.35,
            upstream_event_ids=upstream_event_ids or [],
        )
        await self._emit_event(event)
        return event.id

    async def record_llm_response(
        self,
        model: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float = 0.0,
        duration_ms: float = 0.0,
        upstream_event_ids: list[str] | None = None,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()

        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=parent_id if parent_id is not None else self.get_current_parent(),
            event_type=EventType.LLM_RESPONSE,
            name=name or f"llm_response_{model}",
            model=model,
            content=content,
            tool_calls=tool_calls or [],
            usage=usage or {"input_tokens": 0, "output_tokens": 0},
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            importance=0.5,
            upstream_event_ids=upstream_event_ids or [],
        )
        await self._emit_event(event)
        return event.id

    async def record_error(
        self,
        error_type: str,
        error_message: str,
        stack_trace: str | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()

        # Append helpful suggestions for common error patterns
        enhanced_message = _enhance_error_message(error_message)

        event = ErrorEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            event_type=EventType.ERROR,
            name=name or f"error_{error_type}",
            error_type=error_type,
            error_message=enhanced_message,
            stack_trace=stack_trace,
            importance=0.9,
        )

        self.session.errors += 1
        await self._emit_event(event)
        return event.id

    async def record_safety_check(
        self,
        policy_name: str,
        outcome: SafetyOutcome | str,
        risk_level: RiskLevel | str,
        rationale: str,
        *,
        blocked_action: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        normalized_outcome = SafetyOutcome(outcome)
        event = SafetyCheckEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"safety_check_{policy_name}",
            policy_name=policy_name,
            outcome=normalized_outcome,
            risk_level=RiskLevel(risk_level),
            rationale=rationale,
            blocked_action=blocked_action,
            evidence=evidence or [],
            upstream_event_ids=upstream_event_ids or [],
            importance=0.8 if normalized_outcome != SafetyOutcome.PASS else 0.55,
        )
        await self._emit_event(event)
        return event.id

    async def record_refusal(
        self,
        reason: str,
        policy_name: str,
        *,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
        blocked_action: str | None = None,
        safe_alternative: str | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        event = RefusalEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"refusal_{policy_name}",
            reason=reason,
            policy_name=policy_name,
            risk_level=RiskLevel(risk_level),
            blocked_action=blocked_action,
            safe_alternative=safe_alternative,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.85,
        )
        await self._emit_event(event)
        return event.id

    async def record_policy_violation(
        self,
        policy_name: str,
        violation_type: str,
        *,
        severity: RiskLevel | str = RiskLevel.MEDIUM,
        details: dict[str, Any] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        event = PolicyViolationEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"policy_violation_{violation_type}",
            policy_name=policy_name,
            severity=RiskLevel(severity),
            violation_type=violation_type,
            details=details or {},
            upstream_event_ids=upstream_event_ids or [],
            importance=0.9,
        )
        await self._emit_event(event)
        return event.id

    async def record_prompt_policy(
        self,
        template_id: str,
        policy_parameters: dict[str, Any],
        *,
        speaker: str = "",
        state_summary: str = "",
        goal: str = "",
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        event = PromptPolicyEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"prompt_policy_{template_id}",
            template_id=template_id,
            policy_parameters=policy_parameters,
            speaker=speaker,
            state_summary=state_summary,
            goal=goal,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.65,
        )
        await self._emit_event(event)
        return event.id

    async def record_agent_turn(
        self,
        agent_id: str,
        speaker: str,
        turn_index: int,
        *,
        goal: str = "",
        content: str = "",
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        event = AgentTurnEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"agent_turn_{turn_index}",
            agent_id=agent_id,
            speaker=speaker,
            turn_index=turn_index,
            goal=goal,
            content=content,
            upstream_event_ids=upstream_event_ids or [],
            importance=0.6,
        )
        await self._emit_event(event)
        return event.id

    async def record_behavior_alert(
        self,
        alert_type: str,
        signal: str,
        *,
        severity: RiskLevel | str = RiskLevel.MEDIUM,
        related_event_ids: list[str] | None = None,
        upstream_event_ids: list[str] | None = None,
        name: str | None = None,
    ) -> str:
        self._check_entered()
        event = BehaviorAlertEvent(
            session_id=self.session_id,
            parent_id=self.get_current_parent(),
            name=name or f"behavior_alert_{alert_type}",
            alert_type=alert_type,
            severity=RiskLevel(severity),
            signal=signal,
            related_event_ids=related_event_ids or [],
            upstream_event_ids=upstream_event_ids or [],
            importance=0.82,
        )
        await self._emit_event(event)
        return event.id
