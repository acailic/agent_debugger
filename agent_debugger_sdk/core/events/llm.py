"""LLM request and response events."""

from dataclasses import dataclass, field
from typing import Any

from .base import EventType, TraceEvent

__all__ = ["LLMRequestEvent", "LLMResponseEvent"]


@dataclass(kw_only=True)
class LLMRequestEvent(TraceEvent):
    """Event representing an LLM API request.

    Captures the details of a request sent to an LLM, including
    the model, messages, available tools, and request settings.

    Attributes:
        event_type: Always EventType.LLM_REQUEST
        model: The model identifier (e.g., "gpt-4", "claude-3-opus")
        messages: The conversation history sent to the LLM
        tools: Tool definitions available to the LLM
        settings: Model settings (temperature, max_tokens, etc.)
    """

    event_type: EventType = EventType.LLM_REQUEST
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class LLMResponseEvent(TraceEvent):
    """Event representing an LLM API response.

    Captures the response from an LLM, including generated content,
    tool calls requested, token usage, and cost information.

    Attributes:
        event_type: Always EventType.LLM_RESPONSE
        model: The model that generated this response
        content: The text content of the response
        tool_calls: Tool calls requested by the LLM
        usage: Token usage (input_tokens, output_tokens)
        cost_usd: Estimated cost in USD
        duration_ms: API call duration in milliseconds
    """

    event_type: EventType = EventType.LLM_RESPONSE
    model: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    cost_usd: float = 0.0
    duration_ms: float = 1.0

    def __post_init__(self):
        """Auto-calculate cost if not explicitly set and tokens available."""
        if self.cost_usd == 0.0:
            input_tokens = self.usage.get("input_tokens", 0)
            output_tokens = self.usage.get("output_tokens", 0)
            if input_tokens or output_tokens:
                from agent_debugger_sdk.pricing import calculate_cost

                calculated = calculate_cost(self.model, input_tokens, output_tokens)
                if calculated is not None:
                    object.__setattr__(self, "cost_usd", calculated)
