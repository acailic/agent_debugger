"""Rolling window calculation for live monitoring."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .causal_analysis import _event_value
from .models import RollingSummary, RollingWindow


class RollingWindowCalculator:
    """Calculate rolling window metrics for live monitoring."""

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
        for event in recent_events:
            window.event_count += 1

            if event.event_type == EventType.TOOL_CALL:
                window.tool_calls += 1
                tool_name = _event_value(event, "tool_name", "")
                if tool_name:
                    window.unique_tools.add(tool_name)
            elif event.event_type == EventType.LLM_REQUEST or event.event_type == EventType.LLM_RESPONSE:
                window.llm_calls += 1
                usage = _event_value(event, "usage", {}) or {}
                if isinstance(usage, dict):
                    window.total_tokens += usage.get("total_tokens", 0)
                cost = _event_value(event, "cost_usd", 0.0)
                if isinstance(cost, (int, float)):
                    window.total_cost_usd += float(cost)
            elif event.event_type == EventType.DECISION:
                window.decisions += 1
                confidence = _event_value(event, "confidence", None)
                if confidence is not None and isinstance(confidence, (int, float)):
                    confidences.append(float(confidence))
            elif event.event_type == EventType.ERROR:
                window.errors += 1
            elif event.event_type == EventType.REFUSAL:
                window.refusals += 1
            elif event.event_type == EventType.AGENT_TURN:
                speaker = _event_value(event, "speaker", "")
                if speaker:
                    window.unique_agents.add(speaker)
                state_summary = _event_value(event, "state_summary", "")
                if state_summary and isinstance(state_summary, str):
                    window.state_progression.append(state_summary)

        if confidences:
            window.avg_confidence = sum(confidences) / len(confidences)

        return window

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
