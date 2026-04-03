"""Tests for memory exporter abstraction."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.exporters import (
    EntitySummary,
    FailurePattern,
    FileExporter,
    SessionDigest,
    TraceInsight,
)


@pytest.fixture
def temp_exporter():
    """Create a temporary file exporter for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield FileExporter(base_dir=tmpdir)


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return Session(
        id="test-session-1",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 3, 10, 5, tzinfo=timezone.utc),
        status="completed",
        total_tokens=100,
        total_cost_usd=0.01,
        tool_calls=5,
        llm_calls=2,
        errors=1,
        replay_value=0.75,
        tags=["test"],
    )


@pytest.fixture
def sample_insight(sample_session):
    """Create a sample trace insight for testing."""
    session_digest = SessionDigest(
        session_id=sample_session.id,
        agent_name=sample_session.agent_name,
        framework=sample_session.framework,
        started_at=sample_session.started_at.isoformat(),
        ended_at=sample_session.ended_at.isoformat(),
        status=str(sample_session.status),
        total_tokens=sample_session.total_tokens,
        total_cost_usd=sample_session.total_cost_usd,
        tool_calls=sample_session.tool_calls,
        llm_calls=sample_session.llm_calls,
        errors=sample_session.errors,
        replay_value=sample_session.replay_value,
        retention_tier="standard",
        failure_count=1,
        behavior_alert_count=0,
        highlights_count=2,
        tags=sample_session.tags,
        fix_note=None,
    )

    failure_patterns = [
        FailurePattern(
            fingerprint="tool:search:RuntimeError",
            count=3,
            first_seen_at="2026-04-03T10:01:00Z",
            last_seen_at="2026-04-03T10:04:00Z",
            sample_error_types=["RuntimeError", "ValueError"],
            representative_event_id="event-1",
            severity=0.8,
        )
    ]

    entity_summaries = [
        EntitySummary(
            entity_type="tool_name",
            total_unique=5,
            top_entities=[
                {"value": "search", "count": 10, "session_count": 3},
                {"value": "lookup", "count": 5, "session_count": 2},
            ],
        )
    ]

    return TraceInsight(
        session_digest=session_digest,
        failure_patterns=failure_patterns,
        entity_summaries=entity_summaries,
    )


def test_session_digest_creation(sample_session):
    """Test SessionDigest dataclass creation."""
    digest = SessionDigest(
        session_id=sample_session.id,
        agent_name=sample_session.agent_name,
        framework=sample_session.framework,
        started_at=sample_session.started_at.isoformat(),
        ended_at=sample_session.ended_at.isoformat(),
        status=str(sample_session.status),
        total_tokens=sample_session.total_tokens,
        total_cost_usd=sample_session.total_cost_usd,
        tool_calls=sample_session.tool_calls,
        llm_calls=sample_session.llm_calls,
        errors=sample_session.errors,
        replay_value=sample_session.replay_value,
        retention_tier="standard",
        failure_count=1,
        behavior_alert_count=0,
        highlights_count=2,
        tags=sample_session.tags,
        fix_note=None,
    )

    assert digest.session_id == "test-session-1"
    assert digest.agent_name == "test-agent"
    assert digest.errors == 1
    assert digest.replay_value == 0.75


def test_failure_pattern_creation():
    """Test FailurePattern dataclass creation."""
    pattern = FailurePattern(
        fingerprint="tool:search:RuntimeError",
        count=3,
        first_seen_at="2026-04-03T10:01:00Z",
        last_seen_at="2026-04-03T10:04:00Z",
        sample_error_types=["RuntimeError", "ValueError"],
        representative_event_id="event-1",
        severity=0.8,
    )

    assert pattern.fingerprint == "tool:search:RuntimeError"
    assert pattern.count == 3
    assert len(pattern.sample_error_types) == 2
    assert pattern.severity == 0.8


def test_entity_summary_creation():
    """Test EntitySummary dataclass creation."""
    summary = EntitySummary(
        entity_type="tool_name",
        total_unique=5,
        top_entities=[
            {"value": "search", "count": 10, "session_count": 3},
            {"value": "lookup", "count": 5, "session_count": 2},
        ],
    )

    assert summary.entity_type == "tool_name"
    assert summary.total_unique == 5
    assert len(summary.top_entities) == 2


def test_trace_insight_creation(sample_session):
    """Test TraceInsight dataclass creation."""
    session_digest = SessionDigest(
        session_id=sample_session.id,
        agent_name=sample_session.agent_name,
        framework=sample_session.framework,
        started_at=sample_session.started_at.isoformat(),
        ended_at=sample_session.ended_at.isoformat(),
        status=str(sample_session.status),
        total_tokens=sample_session.total_tokens,
        total_cost_usd=sample_session.total_cost_usd,
        tool_calls=sample_session.tool_calls,
        llm_calls=sample_session.llm_calls,
        errors=sample_session.errors,
        replay_value=sample_session.replay_value,
        retention_tier="standard",
        failure_count=1,
        behavior_alert_count=0,
        highlights_count=2,
        tags=sample_session.tags,
        fix_note=None,
    )

    insight = TraceInsight(
        session_digest=session_digest,
        failure_patterns=[],
        entity_summaries=[],
    )

    assert insight.session_digest.session_id == "test-session-1"
    assert insight.generated_at is not None
    assert isinstance(insight.metadata, dict)


def test_trace_insight_to_dict(sample_insight):
    """Test TraceInsight serialization to dict."""
    insight_dict = sample_insight.to_dict()

    assert "session_digest" in insight_dict
    assert "failure_patterns" in insight_dict
    assert "entity_summaries" in insight_dict
    assert "generated_at" in insight_dict
    assert insight_dict["session_digest"]["session_id"] == "test-session-1"
    assert len(insight_dict["failure_patterns"]) == 1


@pytest.mark.asyncio
async def test_file_exporter_export(temp_exporter, sample_insight):
    """Test FileExporter.export() method."""
    await temp_exporter.export(sample_insight)

    # Check that session file was created
    session_file = temp_exporter.sessions_dir / f"{sample_insight.session_digest.session_id}.json"
    assert session_file.exists()

    # Check file contents
    data = temp_exporter._read_json(session_file)
    assert data["session_digest"]["session_id"] == "test-session-1"
    assert len(data["failure_patterns"]) == 1


@pytest.mark.asyncio
async def test_file_exporter_query_similar(temp_exporter, sample_insight):
    """Test FileExporter.query_similar() method."""
    # Export the insight
    await temp_exporter.export(sample_insight)

    # Create a similar session digest
    similar_digest = SessionDigest(
        session_id="test-session-2",
        agent_name="test-agent",  # Same agent
        framework="pytest",
        started_at="2026-04-03T11:00:00Z",
        ended_at="2026-04-03T11:05:00Z",
        status="completed",
        total_tokens=150,
        total_cost_usd=0.015,
        tool_calls=7,
        llm_calls=3,
        errors=2,  # Similar error count
        replay_value=0.8,
        retention_tier="standard",
        failure_count=2,
        behavior_alert_count=0,
        highlights_count=1,
        tags=[],
        fix_note=None,
    )

    # Query for similar sessions
    similar = await temp_exporter.query_similar(similar_digest, limit=10)

    # Should find the original session
    assert len(similar) >= 1
    assert any(s.session_id == "test-session-1" for s in similar)


@pytest.mark.asyncio
async def test_file_exporter_get_failure_patterns(temp_exporter, sample_insight):
    """Test FileExporter.get_failure_patterns() method."""
    await temp_exporter.export(sample_insight)

    patterns = await temp_exporter.get_failure_patterns(limit=10)

    assert len(patterns) >= 1
    assert patterns[0].fingerprint == "tool:search:RuntimeError"
    assert patterns[0].count == 3


@pytest.mark.asyncio
async def test_file_exporter_health_check(temp_exporter, sample_insight):
    """Test FileExporter.health_check() method."""
    await temp_exporter.export(sample_insight)

    health = await temp_exporter.health_check()

    assert health["status"] == "healthy"
    assert health["exporter_type"] == "file"
    assert health["session_count"] == 1
    assert health["failure_pattern_count"] >= 1


@pytest.mark.asyncio
async def test_file_exporter_error_handling(temp_exporter, sample_insight):
    """Test FileExporter error handling."""
    # Import ExportError from the same module as FileExporter to avoid scoping issues
    from agent_debugger_sdk.core.exporters.file import ExportError as FileExporterError

    # Create an invalid insight that will cause export to fail
    invalid_insight = TraceInsight(
        session_digest=None,  # Invalid: None
        failure_patterns=[],
        entity_summaries=[],
    )

    with pytest.raises(FileExporterError):
        await temp_exporter.export(invalid_insight)


@pytest.mark.asyncio
async def test_file_exporter_incremental_patterns(temp_exporter, sample_insight):
    """Test that FileExporter correctly increments pattern counts."""
    # Export the same insight twice
    await temp_exporter.export(sample_insight)
    await temp_exporter.export(sample_insight)

    patterns = await temp_exporter.get_failure_patterns(limit=10)

    # The pattern should have count = 3 + 3 = 6
    assert patterns[0].count == 6


@pytest.mark.asyncio
async def test_file_exporter_entity_summary_merge(temp_exporter, sample_insight):
    """Test that FileExporter correctly merges entity summaries."""
    await temp_exporter.export(sample_insight)

    # Export again with updated entity data
    updated_insight = TraceInsight(
        session_digest=sample_insight.session_digest,
        failure_patterns=[],
        entity_summaries=[
            EntitySummary(
                entity_type="tool_name",
                total_unique=7,
                top_entities=[
                    {"value": "search", "count": 15, "session_count": 5},
                    {"value": "write", "count": 3, "session_count": 1},
                ],
            )
        ],
    )
    await temp_exporter.export(updated_insight)

    health = await temp_exporter.health_check()
    assert health["entity_summary_count"] >= 1
