"""Tests for Hindsight memory integration adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.adapters.hindsight import HindsightConfig, HindsightMemoryAdapter
from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.exporters import (
    EntitySummary,
    FailurePattern,
    SessionDigest,
    TraceInsight,
)


@pytest.fixture
def hindsight_config():
    """Create test Hindsight configuration."""
    return HindsightConfig(
        endpoint="http://test-hindsight.local",
        bank_id="test_bank",
        api_key="test_key",
        enabled=True,
    )


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return Session(
        id="hindsight-session-1",
        agent_name="hindsight-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 3, 12, 5, tzinfo=timezone.utc),
        status="completed",
        total_tokens=200,
        total_cost_usd=0.02,
        tool_calls=8,
        llm_calls=3,
        errors=2,
        replay_value=0.8,
        tags=["hindsight-test"],
    )


@pytest.fixture
def sample_insight(sample_session):
    """Create a sample trace insight for Hindsight testing."""
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
        failure_count=2,
        behavior_alert_count=1,
        highlights_count=3,
        tags=sample_session.tags,
        fix_note=None,
    )

    failure_patterns = [
        FailurePattern(
            fingerprint="tool:api_call:ConnectionError",
            count=5,
            first_seen_at="2026-04-03T12:01:00Z",
            last_seen_at="2026-04-03T12:04:00Z",
            sample_error_types=["ConnectionError", "TimeoutError"],
            representative_event_id="event-api-1",
            severity=0.9,
        )
    ]

    entity_summaries = [
        EntitySummary(
            entity_type="tool_name",
            total_unique=8,
            top_entities=[
                {"value": "api_call", "count": 15, "session_count": 4},
                {"value": "database_query", "count": 8, "session_count": 2},
            ],
        )
    ]

    return TraceInsight(
        session_digest=session_digest,
        failure_patterns=failure_patterns,
        entity_summaries=entity_summaries,
    )


class MockHindsightClient:
    """Mock Hindsight API client for testing."""

    def __init__(self):
        self.memories = []
        self.health_status = "ok"

    async def create_memory(self, memory: dict) -> dict:
        """Create a memory in Hindsight."""
        memory["id"] = f"memory-{len(self.memories)}"
        self.memories.append(memory)
        return memory

    async def retrieve_memories(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve memories using TEMPR."""
        # Return memories matching the query
        results = []
        for memory in self.memories:
            content = memory.get("content", {})
            # Simple matching logic
            if any(
                term in str(content.values())
                for term in query.split()
            ):
                results.append(memory)
                if len(results) >= top_k:
                    break
        return results

    async def get_health(self) -> dict:
        """Get Hindsight health status."""
        return {"status": self.health_status}


@pytest.mark.asyncio
async def test_hindsight_config_defaults():
    """Test HindsightConfig default values."""
    config = HindsightConfig()

    assert config.endpoint == "http://localhost:9000"
    assert config.bank_id == "agent_debugger"
    assert config.api_key is None
    assert config.enabled is True
    assert config.tempr_enabled is True


@pytest.mark.asyncio
async def test_hindsight_adapter_initialization(hindsight_config):
    """Test HindsightMemoryAdapter initialization."""
    adapter = HindsightMemoryAdapter(hindsight_config)

    assert adapter.config == hindsight_config
    assert adapter.config.endpoint == "http://test-hindsight.local"
    assert adapter.config.bank_id == "test_bank"


@pytest.mark.asyncio
async def test_hindsight_adapter_close(hindsight_config):
    """Test closing the Hindsight adapter."""
    adapter = HindsightMemoryAdapter(hindsight_config)

    # Should not raise even if no client was created
    await adapter.close()


@pytest.mark.asyncio
async def test_hindsight_health_check_healthy(hindsight_config, respx_mock):
    """Test health check with healthy Hindsight service."""
    import respx

    adapter = HindsightMemoryAdapter(hindsight_config)

    # Mock health check endpoint
    health_route = respx.route(
        "http://test-hindsight.local/api/v1/health"
    ).get(mock_return_json={"status": "ok", "version": "1.0"})

    health = await adapter.health_check()

    assert health["status"] == "healthy"
    assert health["exporter_type"] == "hindsight"
    assert health["bank_id"] == "test_bank"
    assert health["hindsight_status"] == "ok"

    health_route.side_effect = None


@pytest.mark.asyncio
async def test_hindsight_health_check_unhealthy(hindsight_config, respx_mock):
    """Test health check with unhealthy Hindsight service."""
    import respx

    adapter = HindsightMemoryAdapter(hindsight_config)

    # Mock failing health check endpoint
    health_route = respx.route(
        "http://test-hindsight.local/api/v1/health"
    ).get(side_effect=Exception("Connection refused"))

    health = await adapter.health_check()

    assert health["status"] == "unhealthy"
    assert "error" in health

    health_route.side_effect = None


@pytest.mark.asyncio
async def test_hindsight_health_check_disabled():
    """Test health check when Hindsight is disabled."""
    config = HindsightConfig(enabled=False)
    adapter = HindsightMemoryAdapter(config)

    health = await adapter.health_check()

    assert health["status"] == "disabled"
    assert health["exporter_type"] == "hindsight"


@pytest.mark.asyncio
async def test_hindsight_export_disabled(sample_insight):
    """Test export when Hindsight is disabled."""
    config = HindsightConfig(enabled=False)
    adapter = HindsightMemoryAdapter(config)

    # Should not raise, just skip
    await adapter.export(sample_insight)


@pytest.mark.asyncio
async def test_hindsight_build_tempr_query(hindsight_config):
    """Test TEMPR query building from session digest."""
    adapter = HindsightMemoryAdapter(hindsight_config)

    digest = SessionDigest(
        session_id="test-1",
        agent_name="test-agent",
        framework="test-framework",
        started_at="2026-04-03T12:00:00Z",
        ended_at="2026-04-03T12:05:00Z",
        status="completed",
        total_tokens=100,
        total_cost_usd=0.01,
        tool_calls=5,
        llm_calls=2,
        errors=3,
        replay_value=0.7,
        retention_tier="standard",
        failure_count=2,
        behavior_alert_count=1,
        highlights_count=2,
        tags=["test", "debug"],
        fix_note=None,
    )

    query = adapter._build_tempr_query(digest)

    assert "agent:test-agent" in query
    assert "framework:test-framework" in query
    assert "errors:3" in query
    assert "failures:2" in query
    assert "tags:test,debug" in query


@pytest.mark.asyncio
async def test_hindsight_query_similar_disabled(hindsight_config):
    """Test query_similar when TEMPR is disabled."""
    config = HindsightConfig(enabled=False)
    adapter = HindsightMemoryAdapter(config)

    digest = SessionDigest(
        session_id="test-1",
        agent_name="test-agent",
        framework="test",
        started_at="2026-04-03T12:00:00Z",
        ended_at=None,
        status="running",
        total_tokens=0,
        total_cost_usd=0.0,
        tool_calls=0,
        llm_calls=0,
        errors=0,
        replay_value=0.0,
        retention_tier="downsampled",
        failure_count=0,
        behavior_alert_count=0,
        highlights_count=0,
        tags=[],
        fix_note=None,
    )

    results = await adapter.query_similar(digest)

    assert results == []


@pytest.mark.asyncio
async def test_hindsight_get_failure_patterns_disabled():
    """Test get_failure_patterns when Hindsight is disabled."""
    config = HindsightConfig(enabled=False)
    adapter = HindsightMemoryAdapter(config)

    patterns = await adapter.get_failure_patterns()

    assert patterns == []


def test_hindsight_config_custom():
    """Test HindsightConfig with custom values."""
    config = HindsightConfig(
        endpoint="https://custom-hindsight.example.com",
        bank_id="custom_bank",
        api_key="custom_key",
        timeout_seconds=60.0,
        enabled=False,
        tempr_enabled=False,
        tempr_top_k=10,
        tempr_threshold=0.5,
    )

    assert config.endpoint == "https://custom-hindsight.example.com"
    assert config.bank_id == "custom_bank"
    assert config.api_key == "custom_key"
    assert config.timeout_seconds == 60.0
    assert config.enabled is False
    assert config.tempr_enabled is False
    assert config.tempr_top_k == 10
    assert config.tempr_threshold == 0.5


# Apply respx_mock fixture to tests that need it
@pytest.fixture
def respx_mock():
    """Fixture for respx mock - only available if respx is installed."""
    try:
        import respx
    except ImportError:
        pytest.skip("respx not installed")
        return None

    with respx.mock as mock:
        yield mock
