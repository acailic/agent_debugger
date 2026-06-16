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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def completed_session():
    return Session(
        id="sess-001",
        agent_name="test-agent",
        framework="pytest-framework",
        started_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 1, 10, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=500,
        total_cost_usd=0.05,
        tool_calls=10,
        llm_calls=4,
        errors=2,
        replay_value=0.9,
        tags=["prod", "v2"],
        fix_note="Fixed retry logic",
    )


@pytest.fixture
def running_session():
    return Session(
        id="sess-002",
        agent_name="agent-b",
        framework="langchain",
        status=SessionStatus.RUNNING,
    )


@pytest.fixture
def sample_analysis():
    return {
        "session_summary": {
            "failure_count": 3,
            "behavior_alert_count": 1,
        },
        "session_replay_value": 0.85,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "live_summary": {"timestamp": "2026-06-01T10:05:00"},
        "failure_clusters": [
            {
                "fingerprint": "tool:search:RuntimeError",
                "count": 5,
                "representative_event_id": "evt-10",
                "event_ids": ["evt-10", "evt-11"],
            },
            {
                "fingerprint": "llm:timeout",
                "count": 2,
                "representative_event_id": "evt-20",
                "event_ids": ["evt-20"],
            },
        ],
        "event_rankings": [
            {
                "event_id": "evt-10",
                "timestamp": "2026-06-01T10:01:00",
                "severity": 0.9,
                "fingerprint": "RuntimeError:tool_search",
            },
            {
                "event_id": "evt-20",
                "timestamp": "2026-06-01T10:03:00",
                "severity": 0.5,
                "fingerprint": "timeout",
            },
        ],
    }


@pytest.fixture
def sample_entity_data():
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "write", "count": 7, "session_count": 2},
            {"value": "read", "count": 5, "session_count": 2},
            {"value": "delete", "count": 3, "session_count": 1},
            {"value": "list", "count": 2, "session_count": 1},
            {"value": "create", "count": 1, "session_count": 1},  # 6th — should be capped
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 4, "session_count": 2},
        ],
    }


@pytest.fixture
def builder():
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight()
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, completed_session, sample_analysis):
    insight = builder.build_insight(
        session=completed_session,
        events=[MagicMock(), MagicMock()],
        checkpoints=[MagicMock()],
        analysis=sample_analysis,
    )

    assert isinstance(insight, TraceInsight)
    assert isinstance(insight.session_digest, SessionDigest)
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, completed_session, sample_analysis):
    events = [MagicMock(), MagicMock(), MagicMock()]
    checkpoints = [MagicMock(), MagicMock()]

    insight = builder.build_insight(
        session=completed_session,
        events=events,
        checkpoints=checkpoints,
        analysis=sample_analysis,
    )

    assert insight.metadata["event_count"] == 3
    assert insight.metadata["checkpoint_count"] == 2
    assert insight.metadata["analysis_timestamp"] == "2026-06-01T10:05:00"


def test_build_insight_with_entity_data(builder, completed_session, sample_analysis, sample_entity_data):
    insight = builder.build_insight(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
        entity_data=sample_entity_data,
    )

    assert len(insight.entity_summaries) > 0


def test_build_insight_without_entity_data(builder, completed_session, sample_analysis):
    insight = builder.build_insight(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
        entity_data=None,
    )

    assert insight.entity_summaries == []


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest()
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)

    assert digest.session_id == "sess-001"
    assert digest.agent_name == "test-agent"
    assert digest.framework == "pytest-framework"
    assert digest.status == str(SessionStatus.COMPLETED)
    assert digest.total_tokens == 500
    assert digest.total_cost_usd == 0.05
    assert digest.tool_calls == 10
    assert digest.llm_calls == 4
    assert digest.errors == 2
    assert digest.tags == ["prod", "v2"]
    assert digest.fix_note == "Fixed retry logic"


def test_build_session_digest_started_at_isoformat(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.started_at == completed_session.started_at.isoformat()


def test_build_session_digest_ended_at_isoformat(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.ended_at == completed_session.ended_at.isoformat()


def test_build_session_digest_ended_at_none_when_no_end(builder, running_session):
    analysis = {"session_summary": {}, "highlights": []}
    digest = builder._build_session_digest(running_session, analysis)
    assert digest.ended_at is None


def test_build_session_digest_replay_value_from_analysis(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.replay_value == 0.85


def test_build_session_digest_retention_tier(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.retention_tier == "standard"


def test_build_session_digest_failure_count(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.failure_count == 3


def test_build_session_digest_highlights_count(builder, completed_session, sample_analysis):
    digest = builder._build_session_digest(completed_session, sample_analysis)
    assert digest.highlights_count == 2


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns()
# ---------------------------------------------------------------------------


def test_build_failure_patterns_sorted_by_count_descending(builder, sample_analysis):
    patterns = builder._build_failure_patterns(sample_analysis)

    counts = [p.count for p in patterns]
    assert counts == sorted(counts, reverse=True)


def test_build_failure_patterns_count(builder, sample_analysis):
    patterns = builder._build_failure_patterns(sample_analysis)
    assert len(patterns) == 2


def test_build_failure_patterns_caps_at_20(builder):
    """More than 20 clusters should be capped at 20."""
    clusters = [
        {
            "fingerprint": f"error:{i}",
            "count": i,
            "representative_event_id": f"evt-{i}",
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
                "fingerprint": "tool:search:RuntimeError",
                "count": 3,
                "representative_event_id": "evt-1",
                "event_ids": ["evt-1"],
            }
        ],
        "event_rankings": [
            {
                "event_id": "evt-1",
                "timestamp": "2026-06-01T10:01:00",
                "severity": 0.8,
                "fingerprint": "RuntimeError:some_tool_error",
            }
        ],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert len(patterns) == 1
    assert isinstance(patterns[0].sample_error_types, list)


def test_build_failure_patterns_empty_when_no_clusters(builder):
    analysis = {"failure_clusters": [], "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)
    assert patterns == []


def test_build_failure_patterns_fingerprint_and_count(builder, sample_analysis):
    patterns = builder._build_failure_patterns(sample_analysis)
    fingerprints = {p.fingerprint: p.count for p in patterns}
    assert "tool:search:RuntimeError" in fingerprints
    assert fingerprints["tool:search:RuntimeError"] == 5


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries()
# ---------------------------------------------------------------------------


def test_build_entity_summaries_returns_empty_on_none(builder):
    result = builder._build_entity_summaries(None)
    assert result == []


def test_build_entity_summaries_returns_empty_on_empty_dict(builder):
    result = builder._build_entity_summaries({})
    assert result == []


def test_build_entity_summaries_maps_entity_types(builder, sample_entity_data):
    summaries = builder._build_entity_summaries(sample_entity_data)
    entity_types = [s.entity_type for s in summaries]
    assert EntityType.TOOL_NAME in entity_types
    assert EntityType.ERROR_TYPE in entity_types


def test_build_entity_summaries_caps_top_entities_at_5(builder, sample_entity_data):
    summaries = builder._build_entity_summaries(sample_entity_data)
    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    # 6 entities provided but should cap at 5
    assert len(tool_summary.top_entities) == 5


def test_build_entity_summaries_total_unique_reflects_full_list(builder, sample_entity_data):
    summaries = builder._build_entity_summaries(sample_entity_data)
    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert tool_summary.total_unique == 6  # all 6 from input, not capped


def test_build_entity_summaries_skips_missing_entity_types(builder):
    entity_data = {
        EntityType.TOOL_NAME: [{"value": "search", "count": 5, "session_count": 1}],
    }
    summaries = builder._build_entity_summaries(entity_data)
    entity_types = [s.entity_type for s in summaries]
    assert EntityType.TOOL_NAME in entity_types
    assert EntityType.ERROR_TYPE not in entity_types


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_does_nothing_when_exporter_none(completed_session, sample_analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should return without raising
    await hook.on_session_end(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
    )


@pytest.mark.asyncio
async def test_on_session_end_skips_export_when_not_completed(running_session, sample_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(
        session=running_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
    )

    mock_exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_when_completed(completed_session, sample_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
    )

    mock_exporter.export.assert_called_once()
    call_arg = mock_exporter.export.call_args[0][0]
    assert isinstance(call_arg, TraceInsight)


@pytest.mark.asyncio
async def test_on_session_end_exports_on_update_regardless_of_status(running_session, sample_analysis):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)

    await hook.on_session_end(
        session=running_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
    )

    mock_exporter.export.assert_called_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exception(completed_session, sample_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = RuntimeError("export failed")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    # Should NOT raise
    await hook.on_session_end(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
    )


@pytest.mark.asyncio
async def test_on_session_end_logs_error_on_exception(completed_session, sample_analysis):
    mock_exporter = AsyncMock()
    mock_exporter.export.side_effect = ValueError("bad export")
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
        await hook.on_session_end(
            session=completed_session,
            events=[],
            checkpoints=[],
            analysis=sample_analysis,
        )
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_on_session_end_passes_entity_data_to_builder(completed_session, sample_analysis, sample_entity_data):
    mock_exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

    await hook.on_session_end(
        session=completed_session,
        events=[],
        checkpoints=[],
        analysis=sample_analysis,
        entity_data=sample_entity_data,
    )

    mock_exporter.export.assert_called_once()
    insight = mock_exporter.export.call_args[0][0]
    assert len(insight.entity_summaries) > 0


# ---------------------------------------------------------------------------
# create_memory_exporter_hook()
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_instance():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter=mock_exporter)
    assert isinstance(hook, MemoryExporterHook)


def test_create_memory_exporter_hook_sets_exporter():
    mock_exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter=mock_exporter)
    assert hook.exporter is mock_exporter


def test_create_memory_exporter_hook_none_exporter():
    hook = create_memory_exporter_hook(exporter=None)
    assert hook.exporter is None


def test_create_memory_exporter_hook_default_config():
    hook = create_memory_exporter_hook()
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_custom_config():
    hook = create_memory_exporter_hook(export_on_completion=False, export_on_update=True)
    assert hook.export_on_completion is False
    assert hook.export_on_update is True
