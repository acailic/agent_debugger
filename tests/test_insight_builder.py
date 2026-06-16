"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events.base import SessionStatus
from agent_debugger_sdk.core.exporters import (
    SessionDigest,
    TraceInsight,
)
from agent_debugger_sdk.core.exporters.insights import InsightBuilder
from agent_debugger_sdk.core.exporters.pipeline import (
    MemoryExporterHook,
    create_memory_exporter_hook,
)
from storage.entities import EntityType


@pytest.fixture
def sample_session():
    return Session(
        id="sess-abc-123",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=500,
        total_cost_usd=0.05,
        tool_calls=10,
        llm_calls=4,
        errors=2,
        tags=["prod", "nightly"],
        fix_note="resolved after retry",
    )


@pytest.fixture
def minimal_analysis():
    return {
        "session_replay_value": 0.8,
        "retention_tier": "standard",
        "session_summary": {"failure_count": 2, "behavior_alert_count": 1},
        "highlights": ["h1", "h2", "h3"],
        "failure_clusters": [],
        "event_rankings": [],
        "live_summary": {"timestamp": "2026-01-01T12:05:00Z"},
    }


@pytest.fixture
def builder():
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, sample_session, minimal_analysis):
    insight = builder.build_insight(
        session=sample_session,
        events=[MagicMock(), MagicMock()],
        checkpoints=[MagicMock()],
        analysis=minimal_analysis,
    )

    assert isinstance(insight, TraceInsight)
    assert isinstance(insight.session_digest, SessionDigest)
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, sample_session, minimal_analysis):
    events = [MagicMock(), MagicMock(), MagicMock()]
    checkpoints = [MagicMock(), MagicMock()]

    insight = builder.build_insight(
        session=sample_session,
        events=events,
        checkpoints=checkpoints,
        analysis=minimal_analysis,
    )

    assert insight.metadata["event_count"] == 3
    assert insight.metadata["checkpoint_count"] == 2


def test_build_insight_metadata_timestamp(builder, sample_session, minimal_analysis):
    insight = builder.build_insight(
        session=sample_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )

    assert insight.metadata["analysis_timestamp"] == "2026-01-01T12:05:00Z"


def test_build_insight_metadata_timestamp_missing(builder, sample_session):
    analysis = {"live_summary": {}, "failure_clusters": [], "event_rankings": []}

    insight = builder.build_insight(
        session=sample_session,
        events=[],
        checkpoints=[],
        analysis=analysis,
    )

    assert insight.metadata["analysis_timestamp"] is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(builder, sample_session, minimal_analysis):
    digest = builder._build_session_digest(sample_session, minimal_analysis)

    assert digest.session_id == "sess-abc-123"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest"
    assert digest.status == "completed"
    assert digest.total_tokens == 500
    assert digest.total_cost_usd == 0.05
    assert digest.tool_calls == 10
    assert digest.llm_calls == 4
    assert digest.errors == 2
    assert digest.tags == ["prod", "nightly"]
    assert digest.fix_note == "resolved after retry"


def test_build_session_digest_replay_and_tier(builder, sample_session, minimal_analysis):
    digest = builder._build_session_digest(sample_session, minimal_analysis)

    assert digest.replay_value == 0.8
    assert digest.retention_tier == "standard"


def test_build_session_digest_failure_and_alert_counts(builder, sample_session, minimal_analysis):
    digest = builder._build_session_digest(sample_session, minimal_analysis)

    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 3


def test_build_session_digest_started_at_iso(builder, sample_session, minimal_analysis):
    digest = builder._build_session_digest(sample_session, minimal_analysis)

    assert "2026-01-01" in digest.started_at
    assert digest.ended_at is not None
    assert "2026-01-01" in digest.ended_at


def test_build_session_digest_no_ended_at(builder, minimal_analysis):
    session = Session(
        id="sess-xyz",
        agent_name="agent",
        framework="fw",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status=SessionStatus.RUNNING,
    )
    digest = builder._build_session_digest(session, minimal_analysis)

    assert digest.ended_at is None


def test_build_session_digest_defaults_empty_analysis(builder, sample_session):
    digest = builder._build_session_digest(sample_session, {})

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0
    assert digest.highlights_count == 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_build_failure_patterns_sorted_by_count_desc(builder):
    analysis = {
        "failure_clusters": [
            {"fingerprint": "fp-a", "count": 1, "representative_event_id": "e1", "event_ids": []},
            {"fingerprint": "fp-b", "count": 5, "representative_event_id": "e2", "event_ids": []},
            {"fingerprint": "fp-c", "count": 3, "representative_event_id": "e3", "event_ids": []},
        ],
        "event_rankings": [],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert patterns[0].count == 5
    assert patterns[1].count == 3
    assert patterns[2].count == 1


def test_build_failure_patterns_caps_at_20(builder):
    clusters = [
        {"fingerprint": f"fp-{i}", "count": i, "representative_event_id": f"e{i}", "event_ids": []}
        for i in range(30)
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) <= 20


def test_build_failure_patterns_extracts_error_types_from_fingerprint(builder):
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "error-cluster",
                "count": 2,
                "representative_event_id": "e1",
                "event_ids": ["e1"],
            }
        ],
        "event_rankings": [
            {"event_id": "e1", "fingerprint": "RuntimeError:tool:search", "severity": 0.9, "timestamp": "ts"}
        ],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    pattern = patterns[0]
    assert "RuntimeError" in pattern.sample_error_types


def test_build_failure_patterns_empty_clusters(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})

    assert patterns == []


def test_build_failure_patterns_fingerprint_and_severity(builder):
    analysis = {
        "failure_clusters": [
            {"fingerprint": "my-fp", "count": 1, "representative_event_id": "e1", "event_ids": []}
        ],
        "event_rankings": [{"event_id": "e1", "severity": 0.75, "timestamp": "2026-01-01T00:00:00Z"}],
    }

    patterns = builder._build_failure_patterns(analysis)

    assert patterns[0].fingerprint == "my-fp"
    assert patterns[0].severity == 0.75
    assert patterns[0].representative_event_id == "e1"


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_build_entity_summaries_none_returns_empty(builder):
    assert builder._build_entity_summaries(None) == []


def test_build_entity_summaries_empty_dict_returns_empty(builder):
    assert builder._build_entity_summaries({}) == []


def test_build_entity_summaries_maps_entity_types(builder):
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


def test_build_entity_summaries_caps_top_entities_at_5(builder):
    entity_data = {
        EntityType.ERROR_TYPE: [
            {"value": f"Err{i}", "count": i + 1, "session_count": 1}
            for i in range(10)
        ]
    }

    summaries = builder._build_entity_summaries(entity_data)

    assert len(summaries[0].top_entities) == 5


def test_build_entity_summaries_multiple_types(builder):
    entity_data = {
        EntityType.TOOL_NAME: [{"value": "search", "count": 3, "session_count": 1}],
        EntityType.ERROR_TYPE: [{"value": "ValueError", "count": 2, "session_count": 1}],
    }

    summaries = builder._build_entity_summaries(entity_data)
    types_present = {s.entity_type for s in summaries}

    assert EntityType.TOOL_NAME in types_present
    assert EntityType.ERROR_TYPE in types_present


def test_build_entity_summaries_skips_empty_type(builder):
    entity_data = {
        EntityType.TOOL_NAME: [],
        EntityType.ERROR_TYPE: [{"value": "ValueError", "count": 1, "session_count": 1}],
    }

    summaries = builder._build_entity_summaries(entity_data)

    assert len(summaries) == 1
    assert summaries[0].entity_type == EntityType.ERROR_TYPE


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_no_exporter_does_nothing(sample_session, minimal_analysis):
    hook = MemoryExporterHook(exporter=None)

    # Should return without error
    await hook.on_session_end(
        session=sample_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )


@pytest.mark.asyncio
async def test_on_session_end_skips_non_completed_when_export_on_completion(minimal_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    running_session = Session(
        id="sess-run",
        agent_name="a",
        framework="f",
        status=SessionStatus.RUNNING,
    )

    await hook.on_session_end(
        session=running_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )

    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_completed_session(sample_session, minimal_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    await hook.on_session_end(
        session=sample_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )

    mock_exporter.export.assert_awaited_once()
    call_arg = mock_exporter.export.call_args[0][0]
    assert isinstance(call_arg, TraceInsight)


@pytest.mark.asyncio
async def test_on_session_end_export_on_update_always_exports(minimal_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)

    running_session = Session(
        id="sess-upd",
        agent_name="a",
        framework="f",
        status=SessionStatus.RUNNING,
    )

    await hook.on_session_end(
        session=running_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )

    mock_exporter.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exception(sample_session, minimal_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = RuntimeError("export failed")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    # Should not raise
    await hook.on_session_end(
        session=sample_session,
        events=[],
        checkpoints=[],
        analysis=minimal_analysis,
    )


@pytest.mark.asyncio
async def test_on_session_end_logs_error_on_exception(sample_session, minimal_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = ValueError("bad data")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(
            session=sample_session,
            events=[],
            checkpoints=[],
            analysis=minimal_analysis,
        )
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook():
    hook = create_memory_exporter_hook()

    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is None


def test_create_memory_exporter_hook_passes_exporter():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter=mock_exporter)

    assert hook.exporter is mock_exporter


def test_create_memory_exporter_hook_passes_kwargs():
    hook = create_memory_exporter_hook(export_on_completion=False, export_on_update=True)

    assert hook.export_on_completion is False
    assert hook.export_on_update is True
