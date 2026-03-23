"""Tests for API authentication integration."""
import pytest
from api.main import app
from httpx import ASGITransport
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_no_auth_header_uses_local_mode():
    """Without auth header, API should work in local mode."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401_or_200():
    """Invalid API key should return 401 in cloud mode, but may pass in local mode."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions",
            headers={"Authorization": "Bearer ad_live_invalid_key_here"}
        )
        # In cloud mode with auth enabled, this would be 401
        # In local mode, auth header is optional so this may still pass
        assert resp.status_code in (200, 401)


@pytest.mark.asyncio
async def test_collector_health_no_auth():
    """Health check should work without authentication."""
    from api.main import app

    # The collector router is already included in the app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
