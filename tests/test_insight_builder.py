"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events.base import EventType, SessionStatus, TraceEvent
from agent_debugger_sdk.core.exporters import TraceInsight
from agent_debugger_sdk.core.exporters.insights import InsightBuilder
from agent_debugger_sdk.core.exporters.pipeline import (
    MemoryExporterHook,
    create_memory_exporter_hook,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session():
    return Session(
        id="sess-1",
        agent_name="my-agent",
        framework="pydantic_ai",
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=200,
        total_cost_usd=0.02,
        tool_calls=10,
        llm_calls=4,
        errors=2,
        tags=["prod"],
        fix_note="fixed by retry",
    )


@pytest.fixture
def minimal_analysis():
    return {
        "session_replay_value": 0.9,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "failure_clusters": [],
        "event_rankings": [],
        "session_summary": {"failure_count": 3, "behavior_alert_count": 1},
        "live_summary": {"timestamp": "2026-01-01T12:05:00Z"},
    }


@pytest.fixture
def builder():
    return InsightBuilder()


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


def test_build_insight_returns_trace_insight(builder, session, minimal_analysis):
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=minimal_analysis)

    assert isinstance(insight, TraceInsight)
    assert insight.session_digest.session_id == "sess-1"
    assert isinstance(insight.failure_patterns, list)
    assert isinstance(insight.entity_summaries, list)
    assert isinstance(insight.metadata, dict)


def test_build_insight_metadata_counts(builder, session, minimal_analysis):
    event = TraceEvent(session_id="sess-1", event_type=EventType.TOOL_CALL)
    insight = builder.build_insight(session, events=[event, event], checkpoints=["cp1"], analysis=minimal_analysis)

    assert insight.metadata["event_count"] == 2
    assert insight.metadata["checkpoint_count"] == 1
    assert insight.metadata["analysis_timestamp"] == "2026-01-01T12:05:00Z"


def test_build_insight_metadata_timestamp_missing(builder, session):
    analysis = {"live_summary": {}}
    insight = builder.build_insight(session, events=[], checkpoints=[], analysis=analysis)
    assert insight.metadata["analysis_timestamp"] is None


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


def test_session_digest_maps_session_fields(builder, session, minimal_analysis):
    digest = builder._build_session_digest(session, minimal_analysis)

    assert digest.session_id == "sess-1"
    assert digest.agent_name == "my-agent"
    assert digest.framework == "pydantic_ai"
    assert digest.started_at == "2026-01-01T12:00:00+00:00"
    assert digest.ended_at == "2026-01-01T12:05:00+00:00"
    assert digest.status == "completed"
    assert digest.total_tokens == 200
    assert digest.total_cost_usd == 0.02
    assert digest.tool_calls == 10
    assert digest.llm_calls == 4
    assert digest.errors == 2
    assert digest.tags == ["prod"]
    assert digest.fix_note == "fixed by retry"


def test_session_digest_replay_value_and_retention(builder, session, minimal_analysis):
    digest = builder._build_session_digest(session, minimal_analysis)

    assert digest.replay_value == 0.9
    assert digest.retention_tier == "standard"


def test_session_digest_counts_from_analysis(builder, session, minimal_analysis):
    digest = builder._build_session_digest(session, minimal_analysis)

    assert digest.failure_count == 3
    assert digest.behavior_alert_count == 1
    assert digest.highlights_count == 2


def test_session_digest_none_ended_at(builder, minimal_analysis):
    session = Session(
        id="sess-2",
        agent_name="agent",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        status=SessionStatus.RUNNING,
    )
    digest = builder._build_session_digest(session, minimal_analysis)
    assert digest.ended_at is None


def test_session_digest_empty_agent_and_framework(builder, minimal_analysis):
    session = Session(id="sess-3", agent_name=None, framework=None, status=SessionStatus.RUNNING)
    digest = builder._build_session_digest(session, minimal_analysis)
    assert digest.agent_name == ""
    assert digest.framework == ""


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


def test_failure_patterns_empty_clusters(builder):
    patterns = builder._build_failure_patterns({"failure_clusters": [], "event_rankings": []})
    assert patterns == []


def test_failure_patterns_sorted_by_count_descending(builder):
    analysis = {
        "failure_clusters": [
            {"fingerprint": "fp-a", "count": 1, "representative_event_id": "e1", "event_ids": []},
            {"fingerprint": "fp-b", "count": 5, "representative_event_id": "e2", "event_ids": []},
            {"fingerprint": "fp-c", "count": 3, "representative_event_id": "e3", "event_ids": []},
        ],
        "event_rankings": [],
    }
    patterns = builder._build_failure_patterns(analysis)

    assert [p.count for p in patterns] == [5, 3, 1]


def test_failure_patterns_capped_at_20(builder):
    clusters = [
        {"fingerprint": f"fp-{i}", "count": i, "representative_event_id": f"e{i}", "event_ids": []}
        for i in range(30)
    ]
    analysis = {"failure_clusters": clusters, "event_rankings": []}
    patterns = builder._build_failure_patterns(analysis)
    assert len(patterns) == 20


def test_failure_patterns_extracts_error_types_from_fingerprint(builder):
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
            {"event_id": "e1", "fingerprint": "SomeError:tool:search", "severity": 0.7, "timestamp": "2026-01-01T00:00:00Z"}
        ],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert len(patterns) == 1
    assert "SomeError" in patterns[0].sample_error_types


def test_failure_patterns_uses_ranking_severity(builder):
    analysis = {
        "failure_clusters": [
            {"fingerprint": "fp", "count": 1, "representative_event_id": "e1", "event_ids": []}
        ],
        "event_rankings": [
            {"event_id": "e1", "fingerprint": "fp", "severity": 0.42, "timestamp": "2026-01-01T00:00:00Z"}
        ],
    }
    patterns = builder._build_failure_patterns(analysis)
    assert patterns[0].severity == 0.42
    assert patterns[0].representative_event_id == "e1"


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


def test_entity_summaries_none_data(builder):
    assert builder._build_entity_summaries(None) == []


def test_entity_summaries_empty_dict(builder):
    assert builder._build_entity_summaries({}) == []


def test_entity_summaries_maps_entity_types(builder):
    entity_data = {
        "tool_name": [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "write", "count": 5, "session_count": 1},
        ],
        "error_type": [
            {"value": "RuntimeError", "count": 4, "session_count": 2},
        ],
    }
    summaries = builder._build_entity_summaries(entity_data)

    types = {s.entity_type for s in summaries}
    assert "tool_name" in types
    assert "error_type" in types


def test_entity_summaries_caps_top_entities_at_5(builder):
    entity_data = {
        "tool_name": [{"value": f"tool-{i}", "count": i, "session_count": 1} for i in range(10)]
    }
    summaries = builder._build_entity_summaries(entity_data)
    tool_summary = next(s for s in summaries if s.entity_type == "tool_name")
    assert len(tool_summary.top_entities) == 5


def test_entity_summaries_total_unique_reflects_all_entities(builder):
    entity_data = {
        "model": [{"value": f"m-{i}", "count": 1, "session_count": 1} for i in range(8)]
    }
    summaries = builder._build_entity_summaries(entity_data)
    model_summary = next(s for s in summaries if s.entity_type == "model")
    assert model_summary.total_unique == 8


def test_entity_summaries_skips_empty_entity_type(builder):
    entity_data = {"tool_name": [], "error_type": [{"value": "IOError", "count": 1, "session_count": 1}]}
    summaries = builder._build_entity_summaries(entity_data)
    types = [s.entity_type for s in summaries]
    assert "tool_name" not in types
    assert "error_type" in types


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_session_end_no_exporter(session, minimal_analysis):
    hook = MemoryExporterHook(exporter=None)
    # Should return without error
    await hook.on_session_end(session, [], [], minimal_analysis)


@pytest.mark.asyncio
async def test_on_session_end_skips_non_completed_when_export_on_completion(session, minimal_analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True, export_on_update=False)

    running_session = Session(id="s", status=SessionStatus.RUNNING)
    await hook.on_session_end(running_session, [], [], minimal_analysis)

    exporter.export.assert_not_called()


@pytest.mark.asyncio
async def test_on_session_end_exports_completed_session(session, minimal_analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    await hook.on_session_end(session, [], [], minimal_analysis)

    exporter.export.assert_awaited_once()
    exported_insight = exporter.export.call_args[0][0]
    assert isinstance(exported_insight, TraceInsight)
    assert exported_insight.session_digest.session_id == "sess-1"


@pytest.mark.asyncio
async def test_on_session_end_exports_on_update_regardless_of_status(minimal_analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=False, export_on_update=True)

    running = Session(id="s-run", status=SessionStatus.RUNNING)
    await hook.on_session_end(running, [], [], minimal_analysis)

    exporter.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_session_end_swallows_exporter_exception(session, minimal_analysis, caplog):
    import logging

    exporter = AsyncMock()
    exporter.export.side_effect = RuntimeError("export boom")
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)

    with caplog.at_level(logging.ERROR):
        await hook.on_session_end(session, [], [], minimal_analysis)

    assert "Failed to export insight" in caplog.text
    assert "sess-1" in caplog.text


@pytest.mark.asyncio
async def test_on_session_end_passes_entity_data(session, minimal_analysis):
    exporter = AsyncMock()
    hook = MemoryExporterHook(exporter=exporter, export_on_completion=True)
    entity_data = {"tool_name": [{"value": "search", "count": 3, "session_count": 1}]}

    await hook.on_session_end(session, [], [], minimal_analysis, entity_data=entity_data)

    exported_insight = exporter.export.call_args[0][0]
    assert len(exported_insight.entity_summaries) >= 1


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


def test_create_memory_exporter_hook_returns_hook():
    exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter)
    assert isinstance(hook, MemoryExporterHook)
    assert hook.exporter is exporter


def test_create_memory_exporter_hook_defaults():
    hook = create_memory_exporter_hook()
    assert hook.exporter is None
    assert hook.export_on_completion is True
    assert hook.export_on_update is False


def test_create_memory_exporter_hook_kwargs():
    exporter = MagicMock()
    hook = create_memory_exporter_hook(exporter, export_on_completion=False, export_on_update=True)
    assert hook.export_on_completion is False
    assert hook.export_on_update is True
