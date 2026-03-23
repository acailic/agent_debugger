import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    """Test health check endpoint returns status."""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "database" in data


@pytest.mark.asyncio
async def test_health_includes_mode():
    """Test health check includes mode information."""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data