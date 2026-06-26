"""Unit tests for InsightBuilder and MemoryExporterHook."""

from __future__ import annotations

from datetime import datetime, timezone
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
def completed_session():
    return Session(
        id="sess-abc",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_tokens=200,
        total_cost_usd=0.02,
        tool_calls=4,
        llm_calls=2,
        errors=1,
        tags=["ci"],
        fix_note="fixed it",
    )


@pytest.fixture
def running_session():
    return Session(
        id="sess-running",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.RUNNING,
    )


@pytest.fixture
def minimal_analysis():
    return {
        "session_replay_value": 0.9,
        "retention_tier": "standard",
        "highlights": ["h1", "h2"],
        "session_summary": {
            "failure_count": 2,
            "behavior_alert_count": 1,
        },
        "failure_clusters": [],
        "event_rankings": [],
    }


@pytest.fixture
def analysis_with_clusters():
    return {
        "session_replay_value": 0.5,
        "retention_tier": "downsampled",
        "highlights": [],
        "session_summary": {"failure_count": 3, "behavior_alert_count": 0},
        "failure_clusters": [
            {
                "fingerprint": "RuntimeError:tool_call_failed",
                "count": 5,
                "representative_event_id": "evt-1",
                "event_ids": ["evt-1", "evt-2"],
            },
            {
                "fingerprint": "ValueError:bad_input",
                "count": 2,
                "representative_event_id": "evt-3",
                "event_ids": ["evt-3"],
            },
            {
                "fingerprint": "TimeoutError:slow_tool",
                "count": 8,
                "representative_event_id": "evt-4",
                "event_ids": [],
            },
        ],
        "event_rankings": [
            {
                "event_id": "evt-1",
                "fingerprint": "RuntimeError:tool_call_failed",
                "timestamp": "2026-01-01T10:01:00Z",
                "severity": 0.9,
            },
            {
                "event_id": "evt-3",
                "fingerprint": "ValueError:bad_input",
                "timestamp": "2026-01-01T10:02:00Z",
                "severity": 0.6,
            },
            {
                "event_id": "evt-4",
                "fingerprint": "TimeoutError:slow_tool",
                "timestamp": "2026-01-01T10:03:00Z",
                "severity": 0.7,
            },
        ],
    }


@pytest.fixture
def entity_data():
    return {
        EntityType.TOOL_NAME: [
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "read_file", "count": 7, "session_count": 2},
            {"value": "write_file", "count": 4, "session_count": 1},
            {"value": "bash", "count": 3, "session_count": 1},
            {"value": "grep", "count": 2, "session_count": 1},
            {"value": "glob", "count": 1, "session_count": 1},  # 6th — should be capped
        ],
        EntityType.ERROR_TYPE: [
            {"value": "RuntimeError", "count": 5, "session_count": 2},
        ],
    }


# ---------------------------------------------------------------------------
# InsightBuilder.build_insight
# ---------------------------------------------------------------------------


class TestBuildInsight:
    def test_returns_trace_insight(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], minimal_analysis)

        assert isinstance(result, TraceInsight)

    def test_session_digest_present(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], minimal_analysis)

        assert result.session_digest is not None
        assert result.session_digest.session_id == "sess-abc"

    def test_metadata_event_and_checkpoint_counts(self, completed_session, minimal_analysis):
        events = [MagicMock(), MagicMock(), MagicMock()]
        checkpoints = [MagicMock()]
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, events, checkpoints, minimal_analysis)

        assert result.metadata["event_count"] == 3
        assert result.metadata["checkpoint_count"] == 1

    def test_metadata_analysis_timestamp_from_live_summary(self, completed_session):
        analysis = {
            "session_replay_value": 0.0,
            "retention_tier": "downsampled",
            "highlights": [],
            "session_summary": {},
            "failure_clusters": [],
            "event_rankings": [],
            "live_summary": {"timestamp": "2026-01-01T10:05:00Z"},
        }
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], analysis)

        assert result.metadata["analysis_timestamp"] == "2026-01-01T10:05:00Z"

    def test_metadata_analysis_timestamp_none_when_missing(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], minimal_analysis)

        assert result.metadata["analysis_timestamp"] is None

    def test_entity_summaries_empty_when_no_entity_data(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], minimal_analysis)

        assert result.entity_summaries == []

    def test_entity_summaries_populated_when_entity_data_provided(
        self, completed_session, minimal_analysis, entity_data
    ):
        builder = InsightBuilder()
        result = builder.build_insight(completed_session, [], [], minimal_analysis, entity_data)

        assert len(result.entity_summaries) > 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_session_digest
# ---------------------------------------------------------------------------


class TestBuildSessionDigest:
    def test_maps_session_id(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.session_id == "sess-abc"

    def test_maps_agent_name(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.agent_name == "test-agent"

    def test_maps_framework(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.framework == "pytest"

    def test_maps_started_at_as_iso(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.started_at == completed_session.started_at.isoformat()

    def test_maps_ended_at_as_iso_when_set(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.ended_at == completed_session.ended_at.isoformat()

    def test_ended_at_none_when_session_still_running(self, running_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(running_session, minimal_analysis)

        assert digest.ended_at is None

    def test_maps_status(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.status == str(SessionStatus.COMPLETED)

    def test_maps_metrics(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.total_tokens == 200
        assert digest.total_cost_usd == 0.02
        assert digest.tool_calls == 4
        assert digest.llm_calls == 2
        assert digest.errors == 1

    def test_maps_replay_value_from_analysis(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.replay_value == 0.9

    def test_maps_retention_tier_from_analysis(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.retention_tier == "standard"

    def test_maps_failure_count_from_session_summary(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.failure_count == 2

    def test_maps_behavior_alert_count_from_session_summary(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.behavior_alert_count == 1

    def test_maps_highlights_count_from_analysis(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.highlights_count == 2

    def test_maps_tags(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.tags == ["ci"]

    def test_maps_fix_note(self, completed_session, minimal_analysis):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, minimal_analysis)

        assert digest.fix_note == "fixed it"

    def test_defaults_when_analysis_keys_missing(self, completed_session):
        builder = InsightBuilder()
        digest = builder._build_session_digest(completed_session, {})

        assert digest.replay_value == 0.0
        assert digest.retention_tier == "downsampled"
        assert digest.failure_count == 0
        assert digest.behavior_alert_count == 0
        assert digest.highlights_count == 0


# ---------------------------------------------------------------------------
# InsightBuilder._build_failure_patterns
# ---------------------------------------------------------------------------


class TestBuildFailurePatterns:
    def test_empty_on_no_clusters(self, minimal_analysis):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(minimal_analysis)

        assert patterns == []

    def test_sorted_by_count_descending(self, analysis_with_clusters):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis_with_clusters)

        counts = [p.count for p in patterns]
        assert counts == sorted(counts, reverse=True)

    def test_highest_count_first(self, analysis_with_clusters):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis_with_clusters)

        assert patterns[0].count == 8  # TimeoutError cluster

    def test_caps_at_20_patterns(self):
        analysis = {
            "failure_clusters": [
                {
                    "fingerprint": f"err:{i}",
                    "count": i,
                    "representative_event_id": f"evt-{i}",
                    "event_ids": [],
                }
                for i in range(25)
            ],
            "event_rankings": [],
        }
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis)

        assert len(patterns) == 20

    def test_fingerprint_mapped(self, analysis_with_clusters):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis_with_clusters)

        fingerprints = {p.fingerprint for p in patterns}
        assert "RuntimeError:tool_call_failed" in fingerprints

    def test_extracts_error_type_from_fingerprint(self, analysis_with_clusters):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis_with_clusters)

        # evt-1 ranking fingerprint contains "error" (RuntimeError) → extracted
        runtime_pattern = next(
            p for p in patterns if p.representative_event_id == "evt-1"
        )
        # error_type extraction: fingerprint.split(":")[0] when "error" in fingerprint lower
        # "RuntimeError:tool_call_failed" — "error" is in "runtimeerror" lower → extracts "RuntimeError"
        assert "RuntimeError" in runtime_pattern.sample_error_types

    def test_severity_from_event_rankings(self, analysis_with_clusters):
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis_with_clusters)

        runtime_pattern = next(
            p for p in patterns if p.representative_event_id == "evt-1"
        )
        assert runtime_pattern.severity == 0.9

    def test_default_severity_when_no_ranking(self):
        analysis = {
            "failure_clusters": [
                {
                    "fingerprint": "unknown",
                    "count": 1,
                    "representative_event_id": "no-ranking",
                    "event_ids": [],
                }
            ],
            "event_rankings": [],
        }
        builder = InsightBuilder()
        patterns = builder._build_failure_patterns(analysis)

        assert patterns[0].severity == 0.5


# ---------------------------------------------------------------------------
# InsightBuilder._build_entity_summaries
# ---------------------------------------------------------------------------


class TestBuildEntitySummaries:
    def test_returns_empty_list_on_none(self):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(None)

        assert summaries == []

    def test_returns_empty_list_on_empty_dict(self):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries({})

        assert summaries == []

    def test_maps_entity_types(self, entity_data):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(entity_data)

        entity_types = {s.entity_type for s in summaries}
        assert EntityType.TOOL_NAME in entity_types
        assert EntityType.ERROR_TYPE in entity_types

    def test_caps_top_entities_at_5(self, entity_data):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(entity_data)

        tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
        assert len(tool_summary.top_entities) == 5

    def test_total_unique_reflects_full_list(self, entity_data):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(entity_data)

        tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
        assert tool_summary.total_unique == 6  # all 6, even though top_entities capped at 5

    def test_skips_entity_types_with_no_data(self, entity_data):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(entity_data)

        # MODEL, POLICY_NAME, ALERT_TYPE have no data → should not appear
        entity_types = {s.entity_type for s in summaries}
        assert EntityType.MODEL not in entity_types
        assert EntityType.POLICY_NAME not in entity_types

    def test_top_entity_structure(self, entity_data):
        builder = InsightBuilder()
        summaries = builder._build_entity_summaries(entity_data)

        tool_summary = next(s for s in summaries if s.entity_type == EntityType.TOOL_NAME)
        first = tool_summary.top_entities[0]
        assert "value" in first
        assert "count" in first
        assert "session_count" in first


# ---------------------------------------------------------------------------
# MemoryExporterHook.on_session_end
# ---------------------------------------------------------------------------


class TestMemoryExporterHookOnSessionEnd:
    @pytest.mark.asyncio
    async def test_does_nothing_when_exporter_is_none(self, completed_session, minimal_analysis):
        hook = MemoryExporterHook(exporter=None)
        # Should complete without error and without calling anything
        await hook.on_session_end(completed_session, [], [], minimal_analysis)

    @pytest.mark.asyncio
    async def test_skips_export_when_export_on_completion_and_session_not_completed(
        self, running_session, minimal_analysis
    ):
        mock_exporter = AsyncMock()
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

        await hook.on_session_end(running_session, [], [], minimal_analysis)

        mock_exporter.export.assert_not_called()

    @pytest.mark.asyncio
    async def test_exports_when_export_on_completion_and_session_completed(
        self, completed_session, minimal_analysis
    ):
        mock_exporter = AsyncMock()
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True, export_on_update=False)

        await hook.on_session_end(completed_session, [], [], minimal_analysis)

        mock_exporter.export.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exports_when_export_on_update_regardless_of_status(
        self, running_session, minimal_analysis
    ):
        mock_exporter = AsyncMock()
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=False, export_on_update=True)

        await hook.on_session_end(running_session, [], [], minimal_analysis)

        mock_exporter.export.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exports_insight_as_trace_insight(self, completed_session, minimal_analysis):
        mock_exporter = AsyncMock()
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

        await hook.on_session_end(completed_session, [], [], minimal_analysis)

        call_args = mock_exporter.export.await_args
        insight = call_args[0][0]
        assert isinstance(insight, TraceInsight)
        assert insight.session_digest.session_id == "sess-abc"

    @pytest.mark.asyncio
    async def test_swallows_exporter_exception_does_not_raise(
        self, completed_session, minimal_analysis
    ):
        mock_exporter = AsyncMock()
        mock_exporter.export.side_effect = RuntimeError("export kaboom")
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

        # Must not raise
        await hook.on_session_end(completed_session, [], [], minimal_analysis)

    @pytest.mark.asyncio
    async def test_swallows_exporter_exception_logs_error(
        self, completed_session, minimal_analysis
    ):
        mock_exporter = AsyncMock()
        mock_exporter.export.side_effect = RuntimeError("export kaboom")
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

        with patch("agent_debugger_sdk.core.exporters.pipeline.logger") as mock_logger:
            await hook.on_session_end(completed_session, [], [], minimal_analysis)
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_entity_data_to_insight_builder(self, completed_session, minimal_analysis, entity_data):
        mock_exporter = AsyncMock()
        hook = MemoryExporterHook(exporter=mock_exporter, export_on_completion=True)

        await hook.on_session_end(completed_session, [], [], minimal_analysis, entity_data)

        call_args = mock_exporter.export.await_args
        insight = call_args[0][0]
        assert len(insight.entity_summaries) > 0


# ---------------------------------------------------------------------------
# create_memory_exporter_hook
# ---------------------------------------------------------------------------


class TestCreateMemoryExporterHook:
    def test_returns_memory_exporter_hook_instance(self):
        result = create_memory_exporter_hook()

        assert isinstance(result, MemoryExporterHook)

    def test_sets_exporter(self):
        mock_exporter = MagicMock()
        hook = create_memory_exporter_hook(exporter=mock_exporter)

        assert hook.exporter is mock_exporter

    def test_none_exporter_by_default(self):
        hook = create_memory_exporter_hook()

        assert hook.exporter is None

    def test_passes_export_on_completion_kwarg(self):
        hook = create_memory_exporter_hook(export_on_completion=False)

        assert hook.export_on_completion is False

    def test_export_on_completion_true_by_default(self):
        hook = create_memory_exporter_hook()

        assert hook.export_on_completion is True

    def test_passes_export_on_update_kwarg(self):
        hook = create_memory_exporter_hook(export_on_update=True)

        assert hook.export_on_update is True

    def test_export_on_update_false_by_default(self):
        hook = create_memory_exporter_hook()

        assert hook.export_on_update is False
