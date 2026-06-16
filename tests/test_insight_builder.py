"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
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
        total_tokens=200,
        total_cost_usd=0.02,
        tool_calls=4,
        llm_calls=2,
        errors=1,
        replay_value=0.8,
        tags=["ci"],
        fix_note="fixed it",
    )


@pytest.fixture
def running_session():
    return Session(
        id="sess-002",
        agent_name="other-agent",
        framework="pydantic_ai",
        started_at=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        status="running",
    )


@pytest.fixture
def events():
    return [TraceEvent(session_id="sess-001"), TraceEvent(session_id="sess-001")]


@pytest.fixture
def checkpoints():
    return [Checkpoint(session_id="sess-001"), Checkpoint(session_id="sess-001")]


@pytest.fixture
def basic_analysis():
    return {
        "session_replay_value": 0.75,
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


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, completed_session, events, checkpoints, basic_analysis):
    insight = builder.build_insight(completed_session, events, checkpoints, basic_analysis)

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest is not None
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, completed_session, events, checkpoints, basic_analysis):
    insight = builder.build_insight(completed_session, events, checkpoints, basic_analysis)

    assert insight.metadata["event_count"] == len(events)
    assert insight.metadata["checkpoint_count"] == len(checkpoints)
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T10:05:00Z"


def test_build_insight_metadata_missing_timestamp(builder, completed_session, events, checkpoints):
    analysis = {"failure_clusters": [], "event_rankings": [], "highlights": []}
    insight = builder.build_insight(completed_session, events, checkpoints, analysis)

    assert insight.metadata["analysis_timestamp"] is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_session_digest_maps_fields(builder, completed_session, basic_analysis):
    digest = builder._build_session_digest(completed_session, basic_analysis)

    assert digest.session_id == "sess-001"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest"
    assert digest.started_at == completed_session.started_at.isoformat()
    assert digest.ended_at == completed_session.ended_at.isoformat()
    assert digest.status == str(completed_session.status)
    assert digest.total_tokens == 200
    assert digest.total_cost_usd == 0.02
    assert digest.tool_calls == 4
    assert digest.llm_calls == 2
    assert digest.errors == 1
    assert digest.tags == ["ci"]
    assert digest.fix_note == "fixed it"


def test_session_digest_analysis_fields(builder, completed_session, basic_analysis):
    digest = builder._build_session_digest(completed_session, basic_analysis)

    assert digest.replay_value == 0.75
    assert digest.retention_tier == "standard"
    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_session_digest_no_ended_at(builder, running_session, basic_analysis):
    digest = builder._build_session_digest(running_session, basic_analysis)

    assert digest.ended_at is None


def test_session_digest_empty_agent_name(builder, basic_analysis):
    session = Session(id="x", status="running")
    digest = builder._build_session_digest(session, basic_analysis)

    assert digest.agent_name == ""
    assert digest.framework == ""


def test_session_digest_defaults_when_analysis_empty(builder, completed_session):
    digest = builder._build_session_digest(completed_session, {})

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0
    assert digest.highlights_count == 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_failure_patterns_empty(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})
    assert patterns == []


def test_failure_patterns_sorted_by_count_descending(builder):
    clusters = [
        {"fingerprint": "fp-a", "count": 1, "representative_event_id": "e1", "event_ids": []},
        {"fingerprint": "fp-b", "count": 10, "representative_event_id": "e2", "event_ids": []},
        {"fingerprint": "fp-c", "count": 5, "representative_event_id": "e3", "event_ids": []},
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)

    assert [p.count for p in patterns] == [10, 5, 1]


def test_failure_patterns_capped_at_20(builder):
    clusters = [
        {"fingerprint": f"fp-{i}", "count": i, "representative_event_id": f"e{i}", "event_ids": []}
        for i in range(25)
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 20


def test_failure_patterns_extracts_error_type_from_fingerprint(builder):
    rankings = [{"event_id": "e1", "fingerprint": "RuntimeError:divide by zero", "timestamp": "t1", "severity": 0.9}]
    clusters = [
        {
            "fingerprint": "err-cluster",
            "count": 3,
            "representative_event_id": "e1",
            "event_ids": ["e1"],
        }
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": rankings}
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    assert "RuntimeError" in patterns[0].sample_error_types


def test_failure_patterns_uses_ranking_severity_and_timestamp(builder):
    rankings = [{"event_id": "e1", "fingerprint": "SomeError:msg", "timestamp": "2026-01-01T10:00:00Z", "severity": 0.7}]
    clusters = [
        {
            "fingerprint": "fp",
            "count": 2,
            "representative_event_id": "e1",
            "event_ids": ["e1"],
        }
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": rankings}
    patterns = builder._build_failure_patterns(analysis)

    assert patterns[0].severity == 0.7
    assert patterns[0].first_seen_at == "2026-01-01T10:00:00Z"


def test_failure_patterns_default_severity_when_no_ranking(builder):
    clusters = [{"fingerprint": "fp", "count": 1, "representative_event_id": "missing", "event_ids": []}]
    analysis = {"failure_clusters": clusters, "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)

    assert patterns[0].severity == 0.5


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_entity_summaries_none_input(builder):
    assert builder._build_entity_summaries(None) == []


def test_entity_summaries_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_entity_summaries_maps_tool_name(builder):
    entity_data = {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "write", "count": 5, "session_count": 2},
        ]
    }
    summaries = builder._build_entity_summaries(entity_data)

    assert len(summaries) == 1
    assert summaries[0].entity_type == EntityType.TOOL_NAME
    assert summaries[0].total_unique == 2
    assert summaries[0].top_entities[0]["value"] == "search"


def test_entity_summaries_caps_top_entities_at_5(builder):
    entity_data = {
        EntityType.ERROR_TYPE: [
            {"value": f"err-{i}", "count": i, "session_count": 1}
            for i in range(10)
        ]
    }
    summaries = builder._build_entity_summaries(entity_data)

    assert summaries[0].total_unique == 10
    assert len(summaries[0].top_entities) == 5


def test_entity_summaries_all_entity_types(builder):
    entity_data = {
        EntityType.TOOL_NAME: [{"value": "t", "count": 1, "session_count": 1}],
        EntityType.ERROR_TYPE: [{"value": "e", "count": 1, "session_count": 1}],
        EntityType.MODEL: [{"value": "m", "count": 1, "session_count": 1}],
        EntityType.POLICY_NAME: [{"value": "p", "count": 1, "session_count": 1}],
        EntityType.ALERT_TYPE: [{"value": "a", "count": 1, "session_count": 1}],
    }
    summaries = builder._build_entity_summaries(entity_data)

    types_found = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME in types_found
    assert EntityType.ERROR_TYPE in types_found
    assert EntityType.MODEL in types_found
    assert EntityType.POLICY_NAME in types_found
    assert EntityType.ALERT_TYPE in types_found


def test_entity_summaries_skips_empty_entity_lists(builder):
    entity_data = {
        EntityType.TOOL_NAME: [],
        EntityType.ERROR_TYPE: [{"value": "e", "count": 1, "session_count": 1}],
    }
    summaries = builder._build_entity_summaries(entity_data)

    types_found = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME not in types_found
    assert EntityType.ERROR_TYPE in types_found


# ---------------------------------------------------------------------------
# MemoryExporterHook
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_exporter():
    exporter = MagicMock()
    exporter.export = AsyncMock()
    return exporter


@pytest.mark.asyncio
async def test_on_session_end_no_exporter(completed_session, events, checkpoints, basic_analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should return without error
    await hook.on_session_end(completed_session, events, checkpoints, basic_analysis)


@pytest.mark.asyncio
async def test_on_session_end_skips_when_not_completed(mock_exporter, running_session, events, checkpoints, basic_analysis):
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)
    await hook.on_session_end(running_session, events, checkpoints, basic_analysis)

    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_when_completed(mock_exporter, completed_session, events, checkpoints, basic_analysis):
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)
    await hook.on_session_end(completed_session, events, checkpoints, basic_analysis)

    mock_exporter.export.assert_awaited_once()
    exported_insight = mock_exporter.export.call_args[0][0]
    assert isinstance(exported_insight, TraceInsight)


@pytest.mark.asyncio
async def test_on_session_end_export_on_update_always_exports(mock_exporter, running_session, events, checkpoints, basic_analysis):
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)
    await hook.on_session_end(running_session, events, checkpoints, basic_analysis)

    mock_exporter.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_session_end_export_on_update_overrides_completion_check(mock_exporter, running_session, events, checkpoints, basic_analysis):
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=True)
    await hook.on_session_end(running_session, events, checkpoints, basic_analysis)

    mock_exporter.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exception(mock_exporter, completed_session, events, checkpoints, basic_analysis):
    mock_exporter.export.side_effect = RuntimeError("export boom")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    # Must not raise
    await hook.on_session_end(completed_session, events, checkpoints, basic_analysis)


@pytest.mark.asyncio
async def test_on_session_end_logs_error_on_exception(mock_exporter, completed_session, events, checkpoints, basic_analysis):
    mock_exporter.export.side_effect = ValueError("bad data")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(completed_session, events, checkpoints, basic_analysis)
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook(mock_exporter):
    hook = create_memory_exporter_hook(mock_exporter)
    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is mock_exporter


def test_create_memory_exporter_hook_default_config():
    hook = create_memory_exporter_hook()
    assert hook.exporter is None
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_custom_kwargs(mock_exporter):
    hook = create_memory_exporter_hook(mock_exporter, export_on_completion=False, export_on_update=True)
    assert hook.export_on_completion is False
    assert hook.export_on_update is True
