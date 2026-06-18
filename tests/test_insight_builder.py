"""Tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.exporters import SessionDigest, TraceInsight
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
        tags=["ci", "test"],
        fix_note="fixed",
    )


@pytest.fixture
def analysis():
    return {
        "session_summary": {"failure_count": 2, "behavior_alert_count": 1},
        "session_replay_value": 0.9,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
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
                "timestamp": "2026-01-01T10:01:00+00:00",
                "severity": 0.9,
                "fingerprint": "RuntimeError:tool:search:RuntimeError",
            },
            {
                "event_id": "ev-2",
                "timestamp": "2026-01-01T10:02:00+00:00",
                "severity": 0.7,
                "fingerprint": "error:something",
            },
            {
                "event_id": "ev-3",
                "timestamp": "2026-01-01T10:03:00+00:00",
                "severity": 0.5,
                "fingerprint": "llm:timeout",
            },
        ],
        "live_summary": {"timestamp": "2026-01-01T10:05:00+00:00"},
    }


@pytest.fixture
def entity_data():
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 5, "session_count": 3},
            {"value": "read_file", "count": 3, "session_count": 2},
            {"value": "write_file", "count": 2, "session_count": 1},
            {"value": "execute", "count": 1, "session_count": 1},
            {"value": "fetch", "count": 1, "session_count": 1},
            {"value": "extra_tool", "count": 1, "session_count": 1},  # beyond cap
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 4, "session_count": 2},
        ],
    }


@pytest.fixture
def builder():
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, session, analysis):
    insight = builder.build_insight(session, [], [], analysis)

    assert isinstance(insight, TraceInsight)
    assert isinstance(insight.session_digest, SessionDigest)
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, session, analysis):
    events = [object(), object(), object()]
    checkpoints = [object()]

    insight = builder.build_insight(session, events, checkpoints, analysis)

    assert insight.metadata["event_count"] == 3
    assert insight.metadata["checkpoint_count"] == 1
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T10:05:00+00:00"


def test_build_insight_entity_summaries_present(builder, session, analysis, entity_data):
    insight = builder.build_insight(session, [], [], analysis, entity_data)

    assert len(insight.entity_summaries) > 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)

    assert digest.session_id == "sess-1"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest"
    assert digest.status == "completed"
    assert digest.total_tokens == 200
    assert digest.total_cost_usd == 0.02
    assert digest.tool_calls == 4
    assert digest.llm_calls == 2
    assert digest.errors == 1
    assert digest.tags == ["ci", "test"]
    assert digest.fix_note == "fixed"


def test_build_session_digest_analysis_fields(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)

    assert digest.replay_value == 0.9
    assert digest.retention_tier == "standard"
    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_build_session_digest_started_at_isoformat(builder, session, analysis):
    digest = builder._build_session_digest(session, analysis)

    assert "2026-01-01" in digest.started_at
    assert digest.ended_at is not None
    assert "2026-01-01" in digest.ended_at


def test_build_session_digest_no_ended_at(builder, analysis):
    s = Session(
        id="s2",
        agent_name="a",
        framework="f",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status="running",
    )
    digest = builder._build_session_digest(s, analysis)

    assert digest.ended_at is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_build_failure_patterns_sorted_by_count_desc(builder, analysis):
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 2
    assert patterns[0].count >= patterns[1].count
    assert patterns[0].count == 5


def test_build_failure_patterns_caps_at_20(builder):
    clusters = [
        {"fingerprint": f"fp:{i}", "count": i, "representative_event_id": f"ev-{i}", "event_ids": []}
        for i in range(25)
    ]
    big_analysis = {"failure_clusters": clusters, "event_rankings": []}

    patterns = builder._build_failure_patterns(big_analysis)

    assert len(patterns) == 20


def test_build_failure_patterns_empty_clusters(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})

    assert patterns == []


def test_build_failure_patterns_extracts_error_types_from_fingerprint(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "some:fp",
                "count": 1,
                "representative_event_id": "e1",
                "event_ids": ["e1"],
            }
        ],
        "event_rankings": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-01T10:00:00+00:00",
                "severity": 0.8,
                "fingerprint": "ValueError:tool:call",
            }
        ],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    assert "ValueError" in patterns[0].sample_error_types


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_build_entity_summaries_returns_empty_on_none(builder):
    assert builder._build_entity_summaries(None) == []


def test_build_entity_summaries_returns_empty_on_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_build_entity_summaries_maps_entity_types(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    types = {s.entity_type for s in summaries}
    assert EntityType.TOOL_NAME in types
    assert EntityType.ERROR_TYPE in types


def test_build_entity_summaries_caps_top_entities_at_5(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert len(tool_summary.top_entities) == 5


def test_build_entity_summaries_total_unique_reflects_full_list(builder, entity_data):
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert tool_summary.total_unique == 6  # all 6, not just top 5


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_does_nothing_when_exporter_none(session, analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should not raise
    await hook.on_session_end(session, [], [], analysis)


@pytest.mark.asyncio
async def test_on_session_end_skips_when_not_completed(analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)
    running_session = Session(
        id="s-running",
        agent_name="a",
        framework="f",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="running",
    )

    await hook.on_session_end(running_session, [], [], analysis)

    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_when_completed(session, analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    await hook.on_session_end(session, [], [], analysis)

    mock_exporter.export.assert_called_once()
    arg = mock_exporter.export.call_args[0][0]
    assert isinstance(arg, TraceInsight)


@pytest.mark.asyncio
async def test_on_session_end_always_exports_when_export_on_update(analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)
    running_session = Session(
        id="s-upd",
        agent_name="a",
        framework="f",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="running",
    )

    await hook.on_session_end(running_session, [], [], analysis)

    mock_exporter.export.assert_called_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exceptions(session, analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = RuntimeError("export boom")
    hook = MemoryExporterHook(exporter=mock_exporter)

    # Should not raise
    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(session, [], [], analysis)
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook():
    hook = create_memory_exporter_hook()
    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is None


def test_create_memory_exporter_hook_passes_config():
    mock_exporter = AsyncMock()
    hook = create_memory_exporter_hook(
        exporter=mock_exporter,
        export_on_completion=False,
        export_on_update=True,
    )

    assert hook.exporter is mock_exporter
    assert hook.export_on_completion is False
    assert hook.export_on_update is True
