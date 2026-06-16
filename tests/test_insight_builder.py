"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
def session():
    return Session(
        id="sess-1",
        agent_name="my-agent",
        framework="langchain",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        status="completed",
        total_tokens=500,
        total_cost_usd=0.05,
        tool_calls=10,
        llm_calls=4,
        errors=2,
        replay_value=0.8,
        tags=["prod"],
    )


@pytest.fixture
def analysis():
    return {
        "session_replay_value": 0.8,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "session_summary": {
            "failure_count": 2,
            "behavior_alert_count": 1,
        },
        "live_summary": {"timestamp": "2026-01-01T10:05:00Z"},
        "failure_clusters": [
            {
                "fingerprint": "tool:search:RuntimeError",
                "count": 5,
                "representative_event_id": "ev-1",
                "event_ids": ["ev-1", "ev-2"],
            },
            {
                "fingerprint": "llm:timeout",
                "count": 2,
                "representative_event_id": "ev-3",
                "event_ids": ["ev-3"],
            },
        ],
        "event_rankings": [
            {
                "event_id": "ev-1",
                "timestamp": "2026-01-01T10:01:00Z",
                "severity": 0.9,
                "fingerprint": "RuntimeError:tool",
            },
            {
                "event_id": "ev-2",
                "timestamp": "2026-01-01T10:02:00Z",
                "severity": 0.7,
                "fingerprint": "error:lookup",
            },
            {
                "event_id": "ev-3",
                "timestamp": "2026-01-01T10:03:00Z",
                "severity": 0.5,
                "fingerprint": "timeout",
            },
        ],
    }


@pytest.fixture
def entity_data():
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "lookup", "count": 5, "session_count": 2},
            {"value": "write", "count": 3, "session_count": 1},
            {"value": "read", "count": 2, "session_count": 1},
            {"value": "delete", "count": 1, "session_count": 1},
            {"value": "extra-tool", "count": 1, "session_count": 1},  # 6th — should be capped
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 3, "session_count": 2},
        ],
    }


@pytest.fixture
def builder():
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, session, analysis):
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=analysis)

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest is not None
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, session, analysis):
    events = [MagicMock(), MagicMock()]
    checkpoints = [MagicMock()]

    insight = builder.build_insight(session, events=events, checkpoints=checkpoints, analysis=analysis)

    assert insight.metadata["event_count"] == 2
    assert insight.metadata["checkpoint_count"] == 1
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T10:05:00Z"


def test_build_insight_with_entity_data(builder, session, analysis, entity_data):
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=analysis, entity_data=entity_data)

    entity_types = {es.entity_type for es in insight.entity_summaries}
    assert EntityType.TOOL_NAME in entity_types
    assert EntityType.ERROR_TYPE in entity_types


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_session_digest_maps_fields(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)

    assert digest.session_id == "sess-1"
    assert digest.agent_name == "my-agent"
    assert digest.framework == "langchain"
    assert digest.status == "completed"
    assert digest.total_tokens == 500
    assert digest.total_cost_usd == 0.05
    assert digest.tool_calls == 10
    assert digest.llm_calls == 4
    assert digest.errors == 2
    assert digest.tags == ["prod"]


def test_session_digest_started_at_isoformat(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)
    assert digest.started_at == session.started_at.isoformat()


def test_session_digest_ended_at_isoformat(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)
    assert digest.ended_at == session.ended_at.isoformat()


def test_session_digest_ended_at_none_when_no_end(builder, analysis):
    open_session = Session(
        id="sess-open",
        agent_name="agent",
        framework="fw",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status="running",
        total_tokens=0,
        total_cost_usd=0.0,
        tool_calls=0,
        llm_calls=0,
        errors=0,
        replay_value=0.0,
        tags=[],
    )
    digest = builder._build_session_digest(open_session, analysis)
    assert digest.ended_at is None


def test_session_digest_analysis_fields(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)

    assert digest.replay_value == 0.8
    assert digest.retention_tier == "standard"
    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_session_digest_defaults_when_analysis_empty(builder, session):
    digest = builder._build_session_digest(session, {})

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0
    assert digest.highlights_count == 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_failure_patterns_sorted_by_count_desc(builder, analysis):
    patterns = builder._build_failure_patterns(analysis)

    counts = [p.count for p in patterns]
    assert counts == sorted(counts, reverse=True)


def test_failure_patterns_capped_at_20(builder):
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
    assert len(patterns) <= 20


def test_failure_patterns_empty_on_no_clusters(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})
    assert patterns == []


def test_failure_patterns_extracts_error_types_from_fingerprints(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "RuntimeError:tool",
                "count": 3,
                "representative_event_id": "ev-1",
                "event_ids": ["ev-1"],
            }
        ],
        "event_rankings": [
            {
                "event_id": "ev-1",
                "timestamp": "2026-01-01T10:00:00Z",
                "severity": 0.8,
                "fingerprint": "RuntimeError:tool",
            }
        ],
    }
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    # fingerprint contains "error" (case-insensitive) — error_types should be extracted
    # "RuntimeError:tool" → split on ":" → "RuntimeError"
    assert "RuntimeError" in patterns[0].sample_error_types


def test_failure_patterns_uses_severity_from_ranking(builder):
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
            {"event_id": "ev-1", "timestamp": "2026-01-01T10:00:00Z", "severity": 0.99, "fingerprint": "fp"}
        ],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert patterns[0].severity == 0.99


def test_failure_patterns_default_severity_when_no_ranking(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "fp",
                "count": 1,
                "representative_event_id": "ev-99",
                "event_ids": [],
            }
        ],
        "event_rankings": [],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert patterns[0].severity == 0.5


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_entity_summaries_empty_on_none(builder):
    assert builder._build_entity_summaries(None) == []


def test_entity_summaries_empty_on_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_entity_summaries_maps_entity_types(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    types = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME in types
    assert EntityType.ERROR_TYPE in types


def test_entity_summaries_caps_top_entities_at_5(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert len(tool_summary.top_entities) <= 5


def test_entity_summaries_total_unique_reflects_all_entities(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert tool_summary.total_unique == len(entity_data[EntityType.TOOL_NAME])


def test_entity_summaries_skips_empty_entity_type(builder):
    data = {EntityType.TOOL_NAME: [], EntityType.ERROR_TYPE: [{"value": "E", "count": 1, "session_count": 1}]}
    summaries = builder._build_entity_summaries(data)

    types = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME not in types
    assert EntityType.ERROR_TYPE in types


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_does_nothing_when_exporter_none(session, analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should not raise
    await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)


@pytest.mark.asyncio
async def test_hook_skips_export_when_not_completed(analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    running_session = Session(
        id="s",
        agent_name="a",
        framework="f",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status="running",
        total_tokens=0,
        total_cost_usd=0.0,
        tool_calls=0,
        llm_calls=0,
        errors=0,
        replay_value=0.0,
        tags=[],
    )

    await hook.on_session_end(running_session, events=[], checkpoints=[], analysis=analysis)
    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_hook_exports_when_session_completed(session, analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)
    mock_exporter.export.assert_called_once()

    exported_insight = mock_exporter.export.call_args[0][0]
    assert isinstance(exported_insight, TraceInsight)
    assert exported_insight.session_digest.session_id == "sess-1"


@pytest.mark.asyncio
async def test_hook_exports_on_update_regardless_of_status(analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)

    running_session = Session(
        id="s2",
        agent_name="a",
        framework="f",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status="running",
        total_tokens=0,
        total_cost_usd=0.0,
        tool_calls=0,
        llm_calls=0,
        errors=0,
        replay_value=0.0,
        tags=[],
    )

    await hook.on_session_end(running_session, events=[], checkpoints=[], analysis=analysis)
    mock_exporter.export.assert_called_once()


@pytest.mark.asyncio
async def test_hook_swallows_exporter_exceptions(session, analysis, caplog):
    import logging

    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = RuntimeError("export failed")

    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    with caplog.at_level(logging.ERROR):
        # Should not raise
        await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)

    assert any("Failed to export" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_default_config():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(mock_exporter)

    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is mock_exporter
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_custom_config():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(mock_exporter, export_on_completion=False, export_on_update=True)

    assert hook.export_on_completion is False
    assert hook.export_on_update is True


def test_create_memory_exporter_hook_none_exporter():
    hook = create_memory_exporter_hook(None)
    assert hook.exporter is None
