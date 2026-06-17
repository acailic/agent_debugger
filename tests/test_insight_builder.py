"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
def session():
    return Session(
        id="sess-abc",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=200,
        total_cost_usd=0.02,
        tool_calls=4,
        llm_calls=2,
        errors=1,
        tags=["ci"],
        fix_note="fixed by patch",
    )


@pytest.fixture
def running_session(session):
    return Session(
        id="sess-running",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        status=SessionStatus.RUNNING,
    )


@pytest.fixture
def analysis():
    return {
        "session_replay_value": 0.8,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "session_summary": {"failure_count": 2, "behavior_alert_count": 1},
        "live_summary": {"timestamp": "2026-01-01T00:05:00Z"},
        "failure_clusters": [
            {
                "fingerprint": "RuntimeError:tool_fail",
                "count": 5,
                "representative_event_id": "evt-1",
                "event_ids": ["evt-1", "evt-2"],
            },
            {
                "fingerprint": "ValueError:bad_input",
                "count": 3,
                "representative_event_id": "evt-3",
                "event_ids": ["evt-3"],
            },
        ],
        "event_rankings": [
            {
                "event_id": "evt-1",
                "timestamp": "2026-01-01T00:01:00Z",
                "severity": 0.9,
                "fingerprint": "error:RuntimeError",
            },
            {
                "event_id": "evt-2",
                "timestamp": "2026-01-01T00:02:00Z",
                "severity": 0.7,
                "fingerprint": "error:ValueError",
            },
            {
                "event_id": "evt-3",
                "timestamp": "2026-01-01T00:03:00Z",
                "severity": 0.6,
                "fingerprint": "other:blah",
            },
        ],
    }


@pytest.fixture
def entity_data():
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "write", "count": 5, "session_count": 2},
            {"value": "read", "count": 4, "session_count": 1},
            {"value": "exec", "count": 3, "session_count": 1},
            {"value": "delete", "count": 2, "session_count": 1},
            {"value": "extra", "count": 1, "session_count": 1},  # 6th → should be capped
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 5, "session_count": 2},
        ],
    }


# ---------------------------------------------------------------------------
# InsightBuilder — build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(session, analysis):
    builder = InsightBuilder()
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=analysis)

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest is not None
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(session, analysis):
    from agent_debugger_sdk.core.events import Checkpoint, TraceEvent

    events = [MagicMock(spec=TraceEvent), MagicMock(spec=TraceEvent)]
    checkpoints = [MagicMock(spec=Checkpoint)]

    builder = InsightBuilder()
    insight = builder.build_insight(session, events=events, checkpoints=checkpoints, analysis=analysis)

    assert insight.metadata["event_count"] == 2
    assert insight.metadata["checkpoint_count"] == 1
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T00:05:00Z"


def test_build_insight_no_entity_data(session, analysis):
    builder = InsightBuilder()
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=analysis, entity_data=None)

    assert insight.entity_summaries == []


# ---------------------------------------------------------------------------
# InsightBuilder — _build_session_digest
# ---------------------------------------------------------------------------


def test_build_session_digest_maps_fields(session, analysis):
    builder = InsightBuilder()
    digest = builder._build_session_digest(session, analysis)

    assert digest.session_id == session.id
    assert digest.agent_name == session.agent_name
    assert digest.framework == session.framework
    assert digest.started_at == session.started_at.isoformat()
    assert digest.ended_at == session.ended_at.isoformat()
    assert digest.status == str(session.status)
    assert digest.total_tokens == session.total_tokens
    assert digest.total_cost_usd == session.total_cost_usd
    assert digest.tool_calls == session.tool_calls
    assert digest.llm_calls == session.llm_calls
    assert digest.errors == session.errors
    assert digest.tags == session.tags
    assert digest.fix_note == session.fix_note


def test_build_session_digest_analysis_fields(session, analysis):
    builder = InsightBuilder()
    digest = builder._build_session_digest(session, analysis)

    assert digest.replay_value == 0.8
    assert digest.retention_tier == "standard"
    assert digest.failure_count == 2
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_build_session_digest_no_ended_at(analysis):
    running = Session(
        id="sess-run",
        agent_name="bot",
        status=SessionStatus.RUNNING,
    )
    builder = InsightBuilder()
    digest = builder._build_session_digest(running, analysis)

    assert digest.ended_at is None


def test_build_session_digest_defaults_for_empty_analysis(session):
    builder = InsightBuilder()
    digest = builder._build_session_digest(session, {})

    assert digest.replay_value == 0.0
    assert digest.retention_tier == "downsampled"
    assert digest.failure_count == 0
    assert digest.behavior_alert_count == 0
    assert digest.highlights_count == 0


# ---------------------------------------------------------------------------
# InsightBuilder — _build_failure_patterns
# ---------------------------------------------------------------------------


def test_build_failure_patterns_sorted_by_count_desc(analysis):
    builder = InsightBuilder()
    patterns = builder._build_failure_patterns(analysis)

    assert patterns[0].count >= patterns[1].count


def test_build_failure_patterns_fingerprints(analysis):
    builder = InsightBuilder()
    patterns = builder._build_failure_patterns(analysis)

    fingerprints = [p.fingerprint for p in patterns]
    assert "RuntimeError:tool_fail" in fingerprints
    assert "ValueError:bad_input" in fingerprints


def test_build_failure_patterns_caps_at_20():
    clusters = [
        {"fingerprint": f"fp-{i}", "count": i, "representative_event_id": f"evt-{i}", "event_ids": []}
        for i in range(25)
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}

    builder = InsightBuilder()
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) <= 20


def test_build_failure_patterns_extracts_error_types_from_fingerprint():
    analysis = {
        "failure_clusters": [
            {
                "fingerprint": "fp-err",
                "count": 2,
                "representative_event_id": "e1",
                "event_ids": ["e1"],
            }
        ],
        "event_rankings": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-01T00:00:00Z",
                "severity": 0.8,
                "fingerprint": "MyError:some_context",
            }
        ],
    }
    builder = InsightBuilder()
    patterns = builder._build_failure_patterns(analysis)

    assert len(patterns) == 1
    assert patterns[0].sample_error_types == ["MyError"]


def test_build_failure_patterns_empty():
    builder = InsightBuilder()
    patterns = builder._build_failure_patterns({})

    assert patterns == []


# ---------------------------------------------------------------------------
# InsightBuilder — _build_entity_summaries
# ---------------------------------------------------------------------------


def test_build_entity_summaries_none_returns_empty():
    builder = InsightBuilder()
    assert builder._build_entity_summaries(None) == []


def test_build_entity_summaries_empty_dict_returns_empty():
    builder = InsightBuilder()
    assert builder._build_entity_summaries({}) == []


def test_build_entity_summaries_maps_entity_types(entity_data):
    builder = InsightBuilder()
    summaries = builder._build_entity_summaries(entity_data)

    types = [s.entity_type for s in summaries]
    assert EntityType.TOOL_NAME in types
    assert EntityType.ERROR_TYPE in types


def test_build_entity_summaries_caps_top_entities_at_5(entity_data):
    builder = InsightBuilder()
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert len(tool_summary.top_entities) <= 5


def test_build_entity_summaries_total_unique(entity_data):
    builder = InsightBuilder()
    summaries = builder._build_entity_summaries(entity_data)

    tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
    assert tool_summary.total_unique == 6  # all 6 entries, not capped for total


# ---------------------------------------------------------------------------
# MemoryExporterHook — on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_does_nothing_when_exporter_none(session, analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should not raise
    await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)


@pytest.mark.asyncio
async def test_hook_skips_export_when_not_completed(running_session, analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True, export_on_update=False)

    await hook.on_session_end(running_session, events=[], checkpoints=[], analysis=analysis)

    exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_hook_exports_when_completed(session, analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)

    exporter.export.assert_called_once()
    call_arg = exporter.export.call_args[0][0]
    assert isinstance(call_arg, TraceInsight)
    assert call_arg.session_digest.session_id == session.id


@pytest.mark.asyncio
async def test_hook_exports_on_update_regardless_of_status(running_session, analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=False, export_on_update=True)

    await hook.on_session_end(running_session, events=[], checkpoints=[], analysis=analysis)

    exporter.export.assert_called_once()


@pytest.mark.asyncio
async def test_hook_swallows_exporter_exceptions(session, analysis):
    exporter = AsyncMock()
    exporter.export.side_effect = RuntimeError("storage down")

    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    # Should not raise — exceptions are swallowed and logged
    await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)


@pytest.mark.asyncio
async def test_hook_logs_error_on_exception(session, analysis, caplog):
    exporter = AsyncMock()
    exporter.export.side_effect = ValueError("boom")

    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    with caplog.at_level(logging.ERROR):
        await hook.on_session_end(session, events=[], checkpoints=[], analysis=analysis)

    assert any("Failed to export" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook():
    exporter = AsyncMock()
    hook = create_memory_exporter_hook(exporter)

    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is exporter


def test_create_memory_exporter_hook_default_config():
    hook = create_memory_exporter_hook()

    assert hook.exporter is None
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_custom_config():
    hook = create_memory_exporter_hook(export_on_completion=False, export_on_update=True)

    assert hook.export_on_completion is False
    assert hook.export_on_update is True
