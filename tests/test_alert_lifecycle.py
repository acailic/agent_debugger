"""Tests for alert lifecycle management API."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk.core.events import Session
from api.main import create_app
from storage import TraceRepository
from storage.repository import AnomalyAlertCreate


def _make_session(session_id: str, agent_name: str = "test-agent") -> Session:
    """Create a test session."""
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=datetime.now(timezone.utc),
        config={"mode": "test"},
    )


def _make_alert(
    alert_id: str,
    session_id: str,
    alert_type: str = "error_spike",
    severity: float = 0.8,
) -> AnomalyAlertCreate:
    """Create a test alert."""
    return AnomalyAlertCreate(
        id=alert_id,
        session_id=session_id,
        alert_type=alert_type,
        severity=severity,
        signal=f"Test alert {alert_id}",
        event_ids=[f"event-{alert_id}"],
        detection_source="test_detector",
        detection_config={"test": True},
    )


@pytest.mark.asyncio
async def test_update_alert_status_acknowledge():
    """Test updating an alert status to acknowledged."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-ack"))
            alert = await repo.create_anomaly_alert(
                _make_alert("test-alert-ack", session.id, severity=0.8)
            )
            alert_id = alert.id
            await db_session.commit()

        response = await client.put(
            f"/api/alerts/{alert_id}/status",
            json={"status": "acknowledged", "note": "Investigating this issue"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
        assert data["resolution_note"] == "Investigating this issue"
        assert data["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_update_alert_status_resolve():
    """Test updating an alert status to resolved."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-resolve"))
            alert = await repo.create_anomaly_alert(
                _make_alert("test-alert-resolve", session.id, severity=0.7)
            )
            alert_id = alert.id
            await db_session.commit()

        response = await client.put(
            f"/api/alerts/{alert_id}/status",
            json={"status": "resolved", "note": "Fixed the root cause"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"
        assert data["resolution_note"] == "Fixed the root cause"
        assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_update_alert_status_dismiss():
    """Test updating an alert status to dismissed."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-dismiss"))
            alert = await repo.create_anomaly_alert(
                _make_alert("test-alert-dismiss", session.id, severity=0.6)
            )
            alert_id = alert.id
            await db_session.commit()

        response = await client.put(
            f"/api/alerts/{alert_id}/status",
            json={"status": "dismissed", "note": "False alarm"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dismissed"
        assert data["resolution_note"] == "False alarm"
        assert data["dismissed_at"] is not None


@pytest.mark.asyncio
async def test_update_alert_status_not_found():
    """Test updating a non-existent alert."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/alerts/nonexistent-id/status",
            json={"status": "acknowledged"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_update_alert_status():
    """Test bulk updating alert statuses."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-bulk"))
            alert_ids = []
            for i in range(3):
                alert = await repo.create_anomaly_alert(
                    _make_alert(f"test-alert-bulk-{i}", session.id, severity=0.5 + i * 0.1)
                )
                alert_ids.append(alert.id)
            await db_session.commit()

        response = await client.post(
            "/api/alerts/bulk-status",
            json={"alert_ids": alert_ids, "status": "acknowledged"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 3
        assert data["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_get_alert_summary():
    """Test getting alert summary statistics."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Get baseline
        baseline_resp = await client.get("/api/alerts/summary")
        assert baseline_resp.status_code == 200
        baseline = baseline_resp.json()

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-summary"))
            for i in range(3):
                await repo.create_anomaly_alert(
                    _make_alert(f"test-alert-summary-{i}", session.id, severity=0.5 + i * 0.1)
                )
            await db_session.commit()

        response = await client.get("/api/alerts/summary")

        assert response.status_code == 200
        data = response.json()
        assert "by_status" in data
        assert "by_type" in data
        assert "by_severity" in data
        assert "total" in data
        assert data["total"] >= baseline["total"]


@pytest.mark.asyncio
async def test_get_alert_trending():
    """Test getting alert trending data."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/alerts/trending?days=7")

        assert response.status_code == 200
        data = response.json()
        assert "trending" in data
        assert "days" in data
        assert data["days"] == 7
        assert isinstance(data["trending"], list)


@pytest.mark.asyncio
async def test_list_alerts_filtered_by_status():
    """Test filtering alerts by status."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-filter-status"))
            alert_ids = []
            for i in range(3):
                alert = await repo.create_anomaly_alert(
                    _make_alert(f"test-alert-filter-{i}", session.id, severity=0.5 + i * 0.1)
                )
                alert_ids.append(alert.id)
            await db_session.commit()

        # Acknowledge some alerts
        await client.post(
            "/api/alerts/bulk-status",
            json={"alert_ids": alert_ids[:2], "status": "acknowledged"},
        )

        # Now filter by status
        response = await client.get("/api/alerts?status=active")

        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "total" in data
        assert data["filters"]["status"] == "active"


@pytest.mark.asyncio
async def test_list_alerts_filtered_by_severity():
    """Test filtering alerts by minimum severity."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-filter-severity"))
            for i in range(3):
                await repo.create_anomaly_alert(
                    _make_alert(f"test-alert-sev-{i}", session.id, severity=0.4 + i * 0.2)
                )
            await db_session.commit()

        response = await client.get("/api/alerts?severity=0.7")

        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert data["filters"]["severity"] == 0.7
        # All returned alerts should have severity >= 0.7
        for alert in data["alerts"]:
            assert alert["severity"] >= 0.7


@pytest.mark.asyncio
async def test_list_alerts_filtered_by_type():
    """Test filtering alerts by alert type."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-filter-type"))
            await repo.create_anomaly_alert(
                _make_alert("test-alert-type-1", session.id, alert_type="error_spike")
            )
            await repo.create_anomaly_alert(
                _make_alert("test-alert-type-2", session.id, alert_type="confidence_drop")
            )
            await db_session.commit()

        response = await client.get("/api/alerts?alert_type=error_spike")

        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert data["filters"]["alert_type"] == "error_spike"
        # All returned alerts should have the specified type
        for alert in data["alerts"]:
            assert alert["alert_type"] == "error_spike"


@pytest.mark.asyncio
async def test_alert_status_transitions():
    """Test alert status transitions: active -> acknowledged -> resolved."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        # Seed database with test data
        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            session = await repo.create_session(_make_session("test-session-transitions"))
            alert = await repo.create_anomaly_alert(
                _make_alert("test-alert-transition", session.id, severity=0.8)
            )
            alert_id = alert.id
            await db_session.commit()

        # Transition to acknowledged
        response = await client.put(
            f"/api/alerts/{alert_id}/status",
            json={"status": "acknowledged", "note": "Looking into it"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
        assert data["acknowledged_at"] is not None

        # Transition to resolved
        response = await client.put(
            f"/api/alerts/{alert_id}/status",
            json={"status": "resolved", "note": "Fixed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"
        assert data["resolved_at"] is not None
        # Previous timestamp should still be present
        assert data["acknowledged_at"] is not None
