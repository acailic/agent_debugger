"""Tests for analytics API routes."""

import pytest


@pytest.fixture(autouse=True)
def isolated_analytics_db(tmp_path, monkeypatch):
    """Use a temporary analytics database for each test."""
    import api.analytics_db
    import api.analytics_routes

    db_path = tmp_path / "analytics.db"
    api.analytics_db._set_test_db_path(db_path)
    # Also reset the imported function in routes module
    monkeypatch.setattr(api.analytics_routes, "get_aggregates", api.analytics_db.get_aggregates)
    monkeypatch.setattr(api.analytics_routes, "get_daily_breakdown", api.analytics_db.get_daily_breakdown)
    monkeypatch.setattr(api.analytics_routes, "record_event", api.analytics_db.record_event)

    # Initialize the database
    api.analytics_db.init_analytics_db()
    yield db_path
    api.analytics_db._set_test_db_path(None)  # Reset


@pytest.mark.asyncio
async def test_get_analytics_default_range(api_client):
    """Test GET /api/analytics with default 30d range."""
    resp = await api_client.get("/api/analytics")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["range"] == "30d"
    assert "period_start" in data
    assert "period_end" in data
    assert "metrics" in data
    assert "derived" in data
    assert "daily_breakdown" in data


@pytest.mark.asyncio
async def test_get_analytics_with_7d_range(api_client):
    """Test GET /api/analytics with 7d range."""
    resp = await api_client.get("/api/analytics?range=7d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["range"] == "7d"


@pytest.mark.asyncio
async def test_get_analytics_with_90d_range(api_client):
    """Test GET /api/analytics with 90d range."""
    resp = await api_client.get("/api/analytics?range=90d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["range"] == "90d"


@pytest.mark.asyncio
async def test_get_analytics_invalid_range(api_client):
    """Test GET /api/analytics with invalid range returns 422."""
    resp = await api_client.get("/api/analytics?range=invalid")
    assert resp.status_code == 422, f"Expected 422 for invalid range, got {resp.status_code}"


@pytest.mark.asyncio
async def test_get_analytics_response_structure(api_client):
    """Test that response has the expected structure."""
    resp = await api_client.get("/api/analytics")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()

    # Check top-level keys
    assert "range" in data
    assert "period_start" in data
    assert "period_end" in data
    assert "metrics" in data
    assert "derived" in data
    assert "daily_breakdown" in data

    # Check metrics structure
    metrics = data["metrics"]
    assert "sessions_created" in metrics
    assert "why_button_clicks" in metrics
    assert "failures_matched" in metrics
    assert "replay_highlights_used" in metrics
    assert "nl_queries_made" in metrics
    assert "searches_performed" in metrics

    # Check derived structure
    derived = data["derived"]
    assert "adoption_rate" in derived
    assert "estimated_time_saved_minutes" in derived

    # Check adoption_rate structure
    adoption = derived["adoption_rate"]
    assert "why_button" in adoption
    assert "failure_memory" in adoption
    assert "replay_highlights" in adoption


@pytest.mark.asyncio
async def test_record_event_success(api_client):
    """Test POST /api/analytics/events records an event."""
    resp = await api_client.post(
        "/api/analytics/events",
        json={
            "event_type": "session_created",
            "session_id": "test-session-123",
            "agent_name": "test-agent",
        },
    )
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["recorded"] is True
    assert data["event_type"] == "session_created"


@pytest.mark.asyncio
async def test_record_event_with_properties(api_client):
    """Test POST /api/analytics/events with optional properties."""
    resp = await api_client.post(
        "/api/analytics/events",
        json={
            "event_type": "why_button_clicked",
            "session_id": "test-session-456",
            "properties": {"source": "trace_view", "duration_ms": 150},
        },
    )
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["recorded"] is True
    assert data["event_type"] == "why_button_clicked"


@pytest.mark.asyncio
async def test_record_event_minimal(api_client):
    """Test POST /api/analytics/events with only required fields."""
    resp = await api_client.post(
        "/api/analytics/events",
        json={"event_type": "search_performed"},
    )
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()
    assert data["recorded"] is True


@pytest.mark.asyncio
async def test_derived_metrics_calculation(api_client):
    """Test that derived metrics are calculated correctly after recording events."""
    # Record some events
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "session_created"},
    )
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "session_created"},
    )
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "why_button_clicked"},
    )
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "failure_matched"},
    )

    # Get analytics
    resp = await api_client.get("/api/analytics?range=7d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()

    # Check raw metrics
    assert data["metrics"]["sessions_created"] == 2
    assert data["metrics"]["why_button_clicks"] == 1
    assert data["metrics"]["failures_matched"] == 1

    # Check adoption rates
    # why_button = 1 / 2 = 0.5
    assert data["derived"]["adoption_rate"]["why_button"] == 0.5
    # failure_memory = 1 / 2 = 0.5
    assert data["derived"]["adoption_rate"]["failure_memory"] == 0.5

    # Check time saved calculation
    # 1 * 14.5 + 1 * 18 = 32.5
    assert data["derived"]["estimated_time_saved_minutes"] == 32.5


@pytest.mark.asyncio
async def test_adoption_rate_zero_sessions(api_client):
    """Test that adoption rates are 0 when there are no sessions."""
    resp = await api_client.get("/api/analytics?range=7d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()

    # With no sessions, all adoption rates should be 0
    assert data["metrics"]["sessions_created"] == 0
    assert data["derived"]["adoption_rate"]["why_button"] == 0.0
    assert data["derived"]["adoption_rate"]["failure_memory"] == 0.0
    assert data["derived"]["adoption_rate"]["replay_highlights"] == 0.0


@pytest.mark.asyncio
async def test_time_saved_calculation(api_client):
    """Test that time saved is calculated correctly for all event types."""
    # Record one of each time-saving event
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "why_button_clicked"},
    )  # 14.5 min
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "failure_matched"},
    )  # 18 min
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "replay_highlights_used"},
    )  # 8.5 min

    resp = await api_client.get("/api/analytics?range=7d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()

    # Total: 14.5 + 18 + 8.5 = 41
    assert data["derived"]["estimated_time_saved_minutes"] == 41.0


@pytest.mark.asyncio
async def test_daily_breakdown_structure(api_client):
    """Test that daily breakdown has the expected structure."""
    # Record an event to ensure we have data
    await api_client.post(
        "/api/analytics/events",
        json={"event_type": "session_created"},
    )

    resp = await api_client.get("/api/analytics?range=7d")
    assert resp.status_code == 200, f"Unexpected status: {resp.text}"

    data = resp.json()

    # Daily breakdown should be a list
    assert isinstance(data["daily_breakdown"], list)

    # For 7d range, should have 7 days
    assert len(data["daily_breakdown"]) == 7

    # Each day should have date, sessions, and clicks
    for day in data["daily_breakdown"]:
        assert "date" in day
        assert "sessions" in day
        assert "clicks" in day
