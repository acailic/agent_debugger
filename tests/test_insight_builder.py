"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.exporters import TraceInsight
from agent_debugger_sdk.core.exporters.insights import InsightBuilder
from agent_debugger_sdk.core.exporters.pipeline import (
    MemoryExporterHook,
    create_memory_exporter_hook,
)
from storage.entities import EntityType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def completed_session():
    return Session(
        id="sess-001",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        status="completed",
        total_tokens=500,
        total_cost_usd=0.05,
        tool_calls=10,
        llm_calls=3,
        errors=2,
        tags=["prod", "v2"],
        fix_note="fixed by retry",
    )


@pytest.fixture
def running_session():
    return Session(
        id="sess-002",
        agent_name="test-agent",
        framework="pytest",
        status="running",
    )


@pytest.fixture
def minimal_analysis():
    return {
        "session_replay_value": 0.9,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "session_summary": {"failure_count": 2, "behavior_alert_count": 1},
        "failure_clusters": [],
        "event_rankings": [],
        "live_summary": {"timestamp": "2026-01-01T10:05:00Z"},
    }


@pytest.fixture
def builder():
    return InsightBuilder()


class MockExporter:
    def __init__(self):
        self.export = AsyncMock()
        self.query_similar = AsyncMock(return_value=[])
        self.get_failure_patterns = AsyncMock(return_value=[])
        self.health_check = AsyncMock(return_value={"status": "healthy"})


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, completed_session, minimal_analysis):
    insight = builder.build_insight(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest.session_id == "sess-001"
    assert insight.failure_patterns == []
    assert insight.entity_summaries == []


def test_build_insight_metadata(builder, completed_session, minimal_analysis):
    events = [MagicMock(), MagicMock()]
    checkpoints = [MagicMock()]

    insight = builder.build_insight(
        session=completed_session,
        events=events,
        checkpoints=checkpoints,
        analysis=minimal_analysis,
    )

    assert insight.metadata["event_count"] == 2
    assert insight.metadata["checkpoint_count"] == 1
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T10:05:00Z"


def test_build_insight_metadata_missing_timestamp(builder, completed_session):
    insight = builder.build_insight(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis={},
    )

    assert insight.metadata["analysis_timestamp"] is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(builder, completed_session, minimal_analysis):
    digest = builder._build_session_digest(completed_session, minimal_analysis)

    assert digest.session_id == "sess-001"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest"
    assert digest.status == "completed"
    assert digest.total_tokens == 500
    assert digest.total_cost_usd == 0.05
    assert digest.tool_calls == 10
    assert digest.llm_calls == 3
    assert digest.errors == 2
    assert digest.tags == ["prod", "v2"]
    assert digest.fix_note == "fixed by retry"


def test_build_session_digest_analysis_fields(builder, completed_session, minimal_analysis):
    digest = builder._build_session_digest(completed_session, minimal_analysis)

    assert digest.replay_value == 0.9
    assert digest.retention_tier == "standard"
    assert digest.highlights_count == 2
    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1


def test_build_session_digest_defaults_on_empty_analysis(builder, completed_session):
    digest = builder._build_session_digest(completed_session, {})

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.highlights_count == 0
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0


def test_build_session_digest_none_ended_at(builder):
    session = Session(
        id="sess-no-end",
        agent_name="",
        framework="",
        status="running",
    )
    digest = builder._build_session_digest(session, {})

    assert digest.ended_at is None
    assert digest.started_at != ""


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def _make_cluster(fingerprint: str, count: int, rep_id: str, event_ids: list[str]) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint,
        "count": count,
        "representative_event_id": rep_id,
        "event_ids": event_ids,
    }


def _make_ranking(event_id: str, timestamp: str, severity: float, fingerprint: str = "") -> dict[str, Any]:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "severity": severity,
        "fingerprint": fingerprint,
    }


def test_build_failure_patterns_sorted_by_count_descending(builder):
    analysis = {
        "failure_clusters": [
            _make_cluster("fp-a", 1, "e1", ["e1"]),
            _make_cluster("fp-b", 5, "e2", ["e2"]),
            _make_cluster("fp-c", 3, "e3", ["e3"]),
        ],
        "event_rankings": [
            _make_ranking("e1", "2026-01-01T10:01:00Z", 0.4),
            _make_ranking("e2", "2026-01-01T10:02:00Z", 0.8),
            _make_ranking("e3", "2026-01-01T10:03:00Z", 0.6),
        ],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 3
    assert patterns[0].count == 5
    assert patterns[1].count == 3
    assert patterns[2].count == 1


def test_build_failure_patterns_capped_at_20(builder):
    clusters = [_make_cluster(f"fp-{i}", i + 1, f"e{i}", [f"e{i}"]) for i in range(25)]
    analysis = {"failure_clusters": clusters, "event_rankings": []}

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 20


def test_build_failure_patterns_extracts_error_types_from_fingerprint(builder):
    analysis = {
        "failure_clusters": [
            _make_cluster("RuntimeError:search", 2, "e1", ["e2"]),
        ],
        "event_rankings": [
            _make_ranking("e1", "2026-01-01T10:00:00Z", 0.7),
            _make_ranking("e2", "2026-01-01T10:00:00Z", 0.7, fingerprint="RuntimeError:search"),
        ],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    assert patterns[0].fingerprint == "RuntimeError:search"
    assert "RuntimeError" in patterns[0].sample_error_types


def test_build_failure_patterns_empty(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})
    assert patterns == []


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_build_entity_summaries_returns_empty_on_none(builder):
    assert builder._build_entity_summaries(None) == []


def test_build_entity_summaries_returns_empty_on_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_build_entity_summaries_maps_entity_types(builder):
    entity_data = {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "write", "count": 5, "session_count": 2},
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 4, "session_count": 1},
        ],
    }

    summaries = builder._build_entity_summaries(entity_data)

    entity_types_in_summaries = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME in entity_types_in_summaries
    assert EntityType.ERROR_TYPE in entity_types_in_summaries


def test_build_entity_summaries_caps_top_entities_at_5(builder):
    entity_data = {
        EntityType.TOOL_NAME: [
            {"value": f"tool-{i}", "count": 10 - i, "session_count": 1}
            for i in range(10)
        ],
    }

    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert len(tool_summary.top_entities) == 5


def test_build_entity_summaries_total_unique_reflects_full_count(builder):
    entity_data = {
        EntityType.MODEL: [
            {"value": f"model-{i}", "count": 1, "session_count": 1}
            for i in range(8)
        ],
    }

    summaries = builder._build_entity_summaries(entity_data)

    model_summary = next(s for s in summaries if s.entity_type == EntityType.MODEL)
    assert model_summary.total_unique == 8


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_does_nothing_when_no_exporter(completed_session, minimal_analysis):
    hook = MemoryExporterHook(exporter=None)
    await hook.on_session_end(completed_session, [], [], minimal_analysis)


@pytest.mark.asyncio
async def test_on_session_end_skips_when_not_completed(running_session, minimal_analysis):
    exporter = MockExporter()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(running_session, [], [], minimal_analysis)

    exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_when_completed(completed_session, minimal_analysis):
    exporter = MockExporter()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    await hook.on_session_end(completed_session, [], [], minimal_analysis)

    exporter.export.assert_awaited_once()
    exported_insight = exporter.export.call_args[0][0]
    assert isinstance(exported_insight, TraceInsight)
    assert exported_insight.session_digest.session_id == "sess-001"


@pytest.mark.asyncio
async def test_on_session_end_export_on_update_ignores_status(running_session, minimal_analysis):
    exporter = MockExporter()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=False, export_on_update=True)

    await hook.on_session_end(running_session, [], [], minimal_analysis)

    exporter.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exceptions(completed_session, minimal_analysis):
    exporter = MockExporter()
    exporter.export.side_effect = RuntimeError("boom")
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    await hook.on_session_end(completed_session, [], [], minimal_analysis)


@pytest.mark.asyncio
async def test_on_session_end_logs_error_on_exception(completed_session, minimal_analysis):
    exporter = MockExporter()
    exporter.export.side_effect = ValueError("bad data")
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(completed_session, [], [], minimal_analysis)
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_correct_type():
    exporter = MockExporter()
    hook = create_memory_exporter_hook(exporter=exporter)

    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is exporter


def test_create_memory_exporter_hook_default_config():
    hook = create_memory_exporter_hook()

    assert hook.exporter is None
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_passes_kwargs():
    exporter = MockExporter()
    hook = create_memory_exporter_hook(
        exporter=exporter,
        export_on_completion=False,
        export_on_update=True,
    )

    assert hook.export_on_completion is False
    assert hook.export_on_update is True
