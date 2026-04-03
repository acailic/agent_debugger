"""Event pipeline hook for automatic insight generation and export.

This module provides hooks for integrating memory exporters into the
event pipeline, enabling automatic insight generation and export when
sessions are completed or updated.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from agent_debugger_sdk.core.exporters import MemoryExporter

logger = logging.getLogger(__name__)


class MemoryExporterHook:
    """Hook for automatic insight generation and export.

    This class integrates with the event pipeline to automatically
    generate insights and export them when sessions are completed.
    """

    def __init__(
        self,
        exporter: MemoryExporter | None = None,
        *,
        export_on_completion: bool = True,
        export_on_update: bool = False,
    ):
        """Initialize the memory exporter hook.

        Args:
            exporter: The memory exporter to use. If None, export is disabled.
            export_on_completion: Whether to export when session status is 'completed'
            export_on_update: Whether to export on any session update
        """
        self.exporter = exporter
        self.export_on_completion = export_on_completion
        self.export_on_update = export_on_update

    async def on_session_end(
        self,
        session: Session,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint],
        analysis: dict[str, Any],
        entity_data: dict[str, Any] | None = None,
    ) -> None:
        """Handle session end event by generating and exporting insights.

        Args:
            session: The session that ended
            events: List of trace events from the session
            checkpoints: List of checkpoints from the session
            analysis: Analysis results from TraceIntelligence
            entity_data: Optional entity extraction data
        """
        if self.exporter is None:
            return

        # Check if we should export based on session status
        should_export = False
        if self.export_on_completion and str(session.status) == "completed":
            should_export = True
        elif self.export_on_update:
            should_export = True

        if not should_export:
            return

        try:
            # Import here to avoid circular dependency
            from agent_debugger_sdk.core.exporters.insights import InsightBuilder

            builder = InsightBuilder()
            insight = builder.build_insight(session, events, checkpoints, analysis, entity_data)

            await self.exporter.export(insight)
            logger.info(f"Exported insight for session {session.id} to memory")

        except Exception as e:
            logger.error(f"Failed to export insight for session {session.id}: {e}")


def create_memory_exporter_hook(
    exporter: MemoryExporter | None = None,
    **kwargs: Any,
) -> MemoryExporterHook:
    """Create a memory exporter hook with configuration.

    Args:
        exporter: The memory exporter to use
        **kwargs: Additional configuration for the hook

    Returns:
        Configured MemoryExporterHook instance
    """
    return MemoryExporterHook(exporter, **kwargs)


__all__ = ["MemoryExporterHook", "create_memory_exporter_hook"]
