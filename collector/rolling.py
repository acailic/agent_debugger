"""Rolling window calculation for live monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .causal_analysis import _event_value
from .models import RollingSummary, RollingWindow


@dataclass
class RollingPattern:
    """A detected pattern in the rolling window."""

    name: str
    severity: float
    description: str


class RollingWindowCalculator:
    """Calculate rolling window metrics for live monitoring."""

    def _handle_tool_call(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        del confidences
        window.tool_calls += 1
        tool_name = _event_value(event, "tool_name", "")
        if tool_name:
            window.unique_tools.add(tool_name)

    def _handle_llm_call(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        del confidences
        window.llm_calls += 1
        usage = _event_value(event, "usage", {}) or {}
        if isinstance(usage, dict):
            window.total_tokens += usage.get("total_tokens", 0)
        cost = _event_value(event, "cost_usd", 0.0)
        if isinstance(cost, (int, float)):
            window.total_cost_usd += float(cost)

    def _handle_decision(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        window.decisions += 1
        confidence = _event_value(event, "confidence", None)
        if confidence is not None and isinstance(confidence, (int, float)):
            confidences.append(float(confidence))

    def _handle_error(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        del event, confidences
        window.errors += 1

    def _handle_refusal(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        del event, confidences
        window.refusals += 1

    def _handle_agent_turn(
        self,
        window: RollingWindow,
        event: TraceEvent,
        confidences: list[float],
    ) -> None:
        del confidences
        speaker = _event_value(event, "speaker", "")
        if speaker:
            window.unique_agents.add(speaker)
        state_summary = _event_value(event, "state_summary", "")
        if state_summary and isinstance(state_summary, str):
            window.state_progression.append(state_summary)

    def _event_handlers(self) -> dict[EventType, Any]:
        return {
            EventType.TOOL_CALL: self._handle_tool_call,
            EventType.LLM_REQUEST: self._handle_llm_call,
            EventType.LLM_RESPONSE: self._handle_llm_call,
            EventType.DECISION: self._handle_decision,
            EventType.ERROR: self._handle_error,
            EventType.REFUSAL: self._handle_refusal,
            EventType.AGENT_TURN: self._handle_agent_turn,
        }

    def compute_rolling_window(
        self,
        events: list[TraceEvent],
        window_seconds: int = 60,
    ) -> RollingWindow:
        """Compute rolling window metrics for the specified time period.

        Args:
            events: List of trace events to analyze
            window_seconds: Rolling window size in seconds (default: 60)

        Returns:
            RollingWindow dataclass with aggregated metrics
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        window = RollingWindow(
            window_start=cutoff,
            window_end=now,
        )

        recent_events = [
            e
            for e in events
            if e.timestamp
            and (e.timestamp.replace(tzinfo=timezone.utc) if e.timestamp.tzinfo is None else e.timestamp) >= cutoff
        ]

        confidences: list[float] = []
        handlers = self._event_handlers()
        for event in recent_events:
            window.event_count += 1
            handler = handlers.get(event.event_type)
            if handler is not None:
                handler(window, event, confidences)

        if confidences:
            window.avg_confidence = sum(confidences) / len(confidences)

        return window

    def detect_patterns(
        self,
        window: RollingWindow,
        events: list[TraceEvent],
    ) -> list[RollingPattern]:
        """Detect behavioral patterns in the rolling window.

        Args:
            window: RollingWindow containing aggregated metrics
            events: List of trace events in the window (should be filtered by time)

        Returns:
            List of detected RollingPattern instances
        """
        patterns: list[RollingPattern] = []

        if window.event_count == 0:
            return patterns

        # Detect repeated tool call patterns
        if window.tool_calls >= 3:
            tool_counts: dict[str, int] = {}
            for event in events:
                if event.event_type == EventType.TOOL_CALL:
                    tool_name = _event_value(event, "tool_name", "")
                    if tool_name:
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

            for tool_name, count in tool_counts.items():
                if count >= 3:
                    severity = min(1.0, count / 5.0)
                    patterns.append(
                        RollingPattern(
                            name="repeated_tool_calls",
                            severity=severity,
                            description=f"Tool '{tool_name}' called {count} times in window",
                        )
                    )

        # Detect error rate spikes
        if window.event_count > 0:
            error_ratio = window.errors / window.event_count
            if error_ratio > 0.3:
                severity = min(1.0, error_ratio)
                patterns.append(
                    RollingPattern(
                        name="error_spike",
                        severity=severity,
                        description=f"Error rate at {error_ratio:.1%} ({window.errors}/{window.event_count} events)",
                    )
                )

        # Detect cost acceleration (second half > 2x first half)
        # Only check if we have cost data in the events
        if len(events) >= 4:
            mid_point = len(events) // 2
            first_half_cost = 0.0
            second_half_cost = 0.0

            for i, event in enumerate(events):
                cost = _event_value(event, "cost_usd", 0.0)
                if isinstance(cost, (int, float)) and cost > 0:
                    cost_float = float(cost)
                    if i < mid_point:
                        first_half_cost += cost_float
                    else:
                        second_half_cost += cost_float

            # Check for acceleration: second half more than 2x first half
            if first_half_cost > 0 and second_half_cost > (2.0 * first_half_cost):
                acceleration_ratio = second_half_cost / first_half_cost
                severity = min(1.0, (acceleration_ratio - 2.0) / 3.0)
                patterns.append(
                    RollingPattern(
                        name="cost_acceleration",
                        severity=severity,
                        description=(
                            f"Cost accelerated {acceleration_ratio:.1f}x "
                            f"(${second_half_cost:.4f} vs ${first_half_cost:.4f})"
                        ),
                    )
                )

        return patterns

    def generate_summary(
        self,
        window: RollingWindow,
        patterns: list[RollingPattern] | None = None,
    ) -> str:
        """Generate a human-readable summary incorporating detected patterns.

        Args:
            window: RollingWindow containing aggregated metrics
            patterns: Optional list of detected patterns (if None, detects them)

        Returns:
            Human-readable summary string
        """
        if patterns is None:
            # Need events to detect patterns, but we don't have them here
            # Return basic summary without pattern detection
            patterns = []

        base_summary = self.build_rolling_summary(window)

        if not patterns:
            return base_summary.text

        # Add pattern information to the summary
        pattern_descriptions = [p.description for p in patterns if p.severity > 0.3]
        if pattern_descriptions:
            return f"{base_summary.text} | Patterns: {'; '.join(pattern_descriptions)}"

        return base_summary.text

    def to_dict(
        self,
        window: RollingWindow,
        patterns: list[RollingPattern] | None = None,
    ) -> dict[str, Any]:
        """Convert rolling window state and patterns to JSON-serializable dict.

        Args:
            window: RollingWindow containing aggregated metrics
            patterns: Optional list of detected patterns

        Returns:
            JSON-serializable dictionary with window state and patterns
        """
        result: dict[str, Any] = {
            "window_start": window.window_start.isoformat(),
            "window_end": window.window_end.isoformat(),
            "event_count": window.event_count,
            "tool_calls": window.tool_calls,
            "llm_calls": window.llm_calls,
            "decisions": window.decisions,
            "errors": window.errors,
            "refusals": window.refusals,
            "total_tokens": window.total_tokens,
            "total_cost_usd": window.total_cost_usd,
            "unique_tools": list(window.unique_tools),
            "unique_agents": list(window.unique_agents),
            "avg_confidence": window.avg_confidence,
            "state_progression": window.state_progression,
        }

        if patterns:
            result["patterns"] = [
                {
                    "name": p.name,
                    "severity": p.severity,
                    "description": p.description,
                }
                for p in patterns
            ]

        return result

    def build_rolling_summary(
        self,
        window: RollingWindow,
    ) -> RollingSummary:
        """Build a human-readable rolling summary from window metrics.

        Args:
            window: RollingWindow containing aggregated metrics

        Returns:
            RollingSummary with text description and structured metrics
        """
        parts: list[str] = []

        if window.event_count == 0:
            text = "No recent activity in the rolling window"
        else:
            parts.append(f"{window.event_count} events")

            detail_parts: list[str] = []
            if window.tool_calls > 0:
                detail_parts.append(f"{window.tool_calls} tool calls")
            if window.decisions > 0:
                detail_parts.append(f"{window.decisions} decisions")
            if window.llm_calls > 0:
                detail_parts.append(f"{window.llm_calls} LLM calls")

            if detail_parts:
                parts.append("(" + ", ".join(detail_parts) + ")")

            if window.errors > 0:
                parts.append(f", {window.errors} errors")
            if window.refusals > 0:
                parts.append(f", {window.refusals} refusals")

            if window.unique_tools:
                tools_preview = sorted(window.unique_tools)[:3]
                tools_str = ", ".join(tools_preview)
                if len(window.unique_tools) > 3:
                    tools_str += f" (+{len(window.unique_tools) - 3} more)"
                parts.append(f" | Tools: {tools_str}")

            text = " ".join(parts)

        metrics: dict[str, Any] = {
            "event_count": window.event_count,
            "tool_calls": window.tool_calls,
            "llm_calls": window.llm_calls,
            "decisions": window.decisions,
            "errors": window.errors,
            "refusals": window.refusals,
            "total_tokens": window.total_tokens,
            "total_cost_usd": round(window.total_cost_usd, 4),
            "unique_tools_count": len(window.unique_tools),
            "unique_agents_count": len(window.unique_agents),
            "avg_confidence": round(window.avg_confidence, 3),
        }

        return RollingSummary(
            text=text,
            metrics=metrics,
            window_type="time",
            window_size=int((window.window_end - window.window_start).total_seconds()),
            computed_at=datetime.now(timezone.utc),
        )
