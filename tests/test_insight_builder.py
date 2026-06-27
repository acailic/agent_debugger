"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events.base import SessionStatus
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
def completed_session() -> Session:
    return Session(
        id="sess-001",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=500,
        total_cost_usd=0.05,
        tool_calls=10,
        llm_calls=4,
        errors=2,
        replay_value=0.8,
        tags=["prod", "nightly"],
        fix_note="fixed by retry",
    )


@pytest.fixture
def running_session() -> Session:
    return Session(
        id="sess-002",
        agent_name="running-agent",
        framework="langchain",
        started_at=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.RUNNING,
    )


@pytest.fixture
def minimal_analysis() -> dict[str, Any]:
    return {}


@pytest.fixture
def full_analysis() -> dict[str, Any]:
    return {
        "session_summary": {
            "failure_count": 3,
            "behavior_alert_count": 1,
        },
        "session_replay_value": 0.9,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "live_summary": {"timestamp": "2026-01-01T10:05:00Z"},
        "failure_clusters": [
            {
                "fingerprint": "tool:search:RuntimeError",
                "count": 5,
                "representative_event_id": "ev-10",
                "event_ids": ["ev-10", "ev-11"],
            },
            {
                "fingerprint": "network:timeout",
                "count": 2,
                "representative_event_id": "ev-20",
                "event_ids": ["ev-20"],
            },
        ],
        "event_rankings": [
            {
                "event_id": "ev-10",
                "fingerprint": "RuntimeError:tool_call_failed",
                "timestamp": "2026-01-01T10:01:00Z",
                "severity": 0.9,
            },
            {
                "event_id": "ev-11",
                "fingerprint": "ValueError:bad_input",
                "timestamp": "2026-01-01T10:02:00Z",
                "severity": 0.6,
            },
            {
                "event_id": "ev-20",
                "fingerprint": "network:timeout",
                "timestamp": "2026-01-01T10:03:00Z",
                "severity": 0.4,
            },
        ],
    }


@pytest.fixture
def entity_data() -> dict[str, Any]:
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 20, "session_count": 5},
            {"value": "write", "count": 10, "session_count": 3},
            {"value": "read", "count": 8, "session_count": 2},
            {"value": "delete", "count": 5, "session_count": 1},
            {"value": "list", "count": 3, "session_count": 1},
            {"value": "extra_tool", "count": 1, "session_count": 1},  # 6th — should be capped
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 5, "session_count": 3},
        ],
    }


@pytest.fixture
def builder() -> InsightBuilder:
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, completed_session, full_analysis):
    events = [MagicMock(), MagicMock()]
    checkpoints = [MagicMock()]
    insight = builder.build_insight(completed_session, events, checkpoints, full_analysis)

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest is not None
    assert insight.failure_patterns is not None
    assert insight.entity_summaries is not None


def test_build_insight_metadata_counts(builder, completed_session, full_analysis):
    events = [MagicMock(), MagicMock(), MagicMock()]
    checkpoints = [MagicMock(), MagicMock()]
    insight = builder.build_insight(completed_session, events, checkpoints, full_analysis)

    assert insight.metadata["event_count"] == 3
    assert insight.metadata["checkpoint_count"] == 2
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T10:05:00Z"


def test_build_insight_metadata_missing_timestamp(builder, completed_session, minimal_analysis):
    insight = builder.build_insight(completed_session, [], [], minimal_analysis)
    assert insight.metadata["analysis_timestamp"] is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(builder, completed_session, full_analysis):
    digest = builder._build_session_digest(completed_session, full_analysis)

    assert digest.session_id == "sess-001"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest"
    assert digest.started_at == "2026-01-01T10:00:00+00:00"
    assert digest.ended_at == "2026-01-01T10:05:00+00:00"
    assert digest.status == "completed"
    assert digest.total_tokens == 500
    assert digest.total_cost_usd == 0.05
    assert digest.tool_calls == 10
    assert digest.llm_calls == 4
    assert digest.errors == 2
    assert digest.tags == ["prod", "nightly"]
    assert digest.fix_note == "fixed by retry"


def test_build_session_digest_analysis_fields(builder, completed_session, full_analysis):
    digest = builder._build_session_digest(completed_session, full_analysis)

    assert digest.replay_value == 0.9
    assert digest.retention_tier == "standard"
    assert digest.failure_count == 3
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_build_session_digest_defaults_on_empty_analysis(builder, completed_session, minimal_analysis):
    digest = builder._build_session_digest(completed_session, minimal_analysis)

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0
    assert digest.highlights_count == 0


def test_build_session_digest_no_ended_at(builder, running_session, minimal_analysis):
    digest = builder._build_session_digest(running_session, minimal_analysis)

    assert digest.ended_at is None
    assert digest.agent_name == "running-agent"


def test_build_session_digest_empty_agent_name(builder, minimal_analysis):
    session = Session(id="s-bare", started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    digest = builder._build_session_digest(session, minimal_analysis)

    assert digest.agent_name == ""
    assert digest.framework == ""


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_build_failure_patterns_sorted_by_count_descending(builder, full_analysis):
    patterns = builder._build_failure_patterns(full_analysis)

    assert len(patterns) == 2
    assert patterns[0].count == 5
    assert patterns[1].count == 2


def test_build_failure_patterns_caps_at_20(builder):
    clusters = [
        {
            "fingerprint": f"fp-{i}",
            "count": i,
            "representative_event_id": f"ev-{i}",
            "event_ids": [],
        }
        for i in range(25)
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 20


def test_build_failure_patterns_extracts_error_types_from_fingerprint(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "tool:error",
                "count": 1,
                "representative_event_id": "ev-1",
                "event_ids": ["ev-1"],
            }
        ],
        "event_rankings": [
            {
                "event_id": "ev-1",
                "fingerprint": "RuntimeError:tool_call_failed",
                "timestamp": "2026-01-01T10:00:00Z",
                "severity": 0.7,
            }
        ],
    }
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    assert "RuntimeError" in patterns[0].sample_error_types


def test_build_failure_patterns_empty_clusters(builder, minimal_analysis):
    patterns = builder._build_failure_patterns(minimal_analysis)
    assert patterns == []


def test_build_failure_patterns_uses_ranking_severity(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "fp",
                "count": 1,
                "representative_event_id": "ev-1",
                "event_ids": [],
            }
        ],
        "event_rankings": [
            {
                "event_id": "ev-1",
                "fingerprint": "some:fp",
                "timestamp": "2026-01-01T10:00:00Z",
                "severity": 0.42,
            }
        ],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert patterns[0].severity == 0.42


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_build_entity_summaries_returns_empty_on_none(builder):
    assert builder._build_entity_summaries(None) == []


def test_build_entity_summaries_returns_empty_on_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_build_entity_summaries_maps_entity_types(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    entity_types_found = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME in entity_types_found
    assert EntityType.ERROR_TYPE in entity_types_found


def test_build_entity_summaries_caps_top_entities_at_5(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert len(tool_summary.top_entities) == 5
    assert tool_summary.total_unique == 6


def test_build_entity_summaries_skips_empty_entity_lists(builder):
    data = {
        EntityType.TOOL_NAME: [],
        EntityType.ERROR_TYPE: [{"value": "RuntimeError", "count": 1, "session_count": 1}],
    }
    summaries = builder._build_entity_summaries(data)

    assert len(summaries) == 1
    assert summaries[0].entity_type == EntityType.ERROR_TYPE


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_does_nothing_when_exporter_none(completed_session, full_analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should return without error
    await hook.on_session_end(completed_session, [], [], full_analysis)


@pytest.mark.asyncio
async def test_on_session_end_skips_non_completed_when_export_on_completion(running_session, full_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(running_session, [], [], full_analysis)

    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_on_completed_session(completed_session, full_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(completed_session, [], [], full_analysis)

    mock_exporter.export.assert_called_once()
    insight_arg = mock_exporter.export.call_args[0][0]
    assert isinstance(insight_arg, TraceInsight)
    assert insight_arg.session_digest.session_id == "sess-001"


@pytest.mark.asyncio
async def test_on_session_end_exports_on_update_regardless_of_status(running_session, full_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)

    await hook.on_session_end(running_session, [], [], full_analysis)

    mock_exporter.export.assert_called_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exceptions(completed_session, full_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = RuntimeError("export failed")

    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    # Should not raise
    await hook.on_session_end(completed_session, [], [], full_analysis)


@pytest.mark.asyncio
async def test_on_session_end_logs_error_on_exception(completed_session, full_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = ValueError("bad export")

    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(completed_session, [], [], full_analysis)
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_on_session_end_passes_entity_data_to_builder(completed_session, full_analysis, entity_data):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    await hook.on_session_end(completed_session, [], [], full_analysis, entity_data=entity_data)

    mock_exporter.export.assert_called_once()
    insight = mock_exporter.export.call_args[0][0]
    entity_types = {s.entity_type for s in insight.entity_summaries}
    assert EntityType.TOOL_NAME in entity_types


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook():
    hook = create_memory_exporter_hook()
    assert isinstance(hook, MemoryExporterHook)


def test_create_memory_exporter_hook_default_config():
    hook = create_memory_exporter_hook()
    assert hook.exporter is None
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_with_exporter():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter=mock_exporter)
    assert hook.exporter is mock_exporter


def test_create_memory_exporter_hook_with_kwargs():
    hook = create_memory_exporter_hook(export_on_completion=False, export_on_update=True)
    assert hook.export_on_completion is False
    assert hook.export_on_update is True
