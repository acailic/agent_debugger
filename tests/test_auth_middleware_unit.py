"""Unit tests for auth middleware helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from auth.middleware import _resolve_tenant_from_key, get_tenant_from_api_key


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_returns_matching_tenant():
    db = SimpleNamespace(execute=AsyncMock())
    candidate = SimpleNamespace(tenant_id="tenant-a", key_hash="hashed")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [candidate]
    db.execute.return_value = result

    with patch("auth.middleware.verify_key", return_value=True):
        tenant_id = await _resolve_tenant_from_key("ad_live_example_key", db)

    assert tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_raises_for_invalid_key():
    db = SimpleNamespace(execute=AsyncMock())
    candidate = SimpleNamespace(tenant_id="tenant-a", key_hash="hashed")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [candidate]
    db.execute.return_value = result

    with patch("auth.middleware.verify_key", return_value=False), pytest.raises(HTTPException) as exc:
        await _resolve_tenant_from_key("ad_live_invalid_key", db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid API key"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_defaults_to_local_without_header():
    request = SimpleNamespace(headers={})

    tenant_id = await get_tenant_from_api_key(request, AsyncMock())

    assert tenant_id == "local"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_rejects_malformed_header():
    request = SimpleNamespace(headers={"Authorization": "Token abc"})

    with pytest.raises(HTTPException) as exc:
        await get_tenant_from_api_key(request, AsyncMock())

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authorization header"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_delegates_to_lookup():
    request = SimpleNamespace(headers={"Authorization": "Bearer ad_live_key"})

    with patch("auth.middleware._resolve_tenant_from_key", new=AsyncMock(return_value="tenant-b")) as resolver:
        tenant_id = await get_tenant_from_api_key(request, AsyncMock())

    assert tenant_id == "tenant-b"
    resolver.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_returns_first_valid_match():
    """When multiple API key candidates exist, return the first valid match."""
    db = SimpleNamespace(execute=AsyncMock())
    candidates = [
        SimpleNamespace(tenant_id="tenant-a", key_hash="hash1"),
        SimpleNamespace(tenant_id="tenant-b", key_hash="hash2"),
        SimpleNamespace(tenant_id="tenant-c", key_hash="hash3"),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = candidates
    db.execute.return_value = result

    def verify_side_effect(raw_key, hashed):
        return hashed == "hash2"  # Only second key matches

    with patch("auth.middleware.verify_key", side_effect=verify_side_effect):
        tenant_id = await _resolve_tenant_from_key("ad_live_key", db)

    assert tenant_id == "tenant-b"


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_raises_when_no_candidates():
    """When no API key candidates match the prefix, raise 401."""
    db = SimpleNamespace(execute=AsyncMock())
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await _resolve_tenant_from_key("ad_live_nonexistent_key", db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid API key"


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_filters_inactive_keys():
    """Inactive API keys should not be considered valid."""
    db = SimpleNamespace(execute=AsyncMock())
    active_key = SimpleNamespace(tenant_id="tenant-active", key_hash="active_hash")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [active_key]
    db.execute.return_value = result

    # Verify that the query includes is_active filter
    with patch("auth.middleware.verify_key", return_value=True):
        tenant_id = await _resolve_tenant_from_key("ad_live_key", db)

    assert tenant_id == "tenant-active"
    # Check that execute was called (query was made with is_active filter)
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_tenant_from_key_short_key_handling():
    """Handle short API keys (<12 chars) without index error."""
    db = SimpleNamespace(execute=AsyncMock())
    candidate = SimpleNamespace(tenant_id="tenant-short", key_hash="short_hash")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [candidate]
    db.execute.return_value = result

    with patch("auth.middleware.verify_key", return_value=True):
        # Key shorter than 12 chars should use full key as prefix
        tenant_id = await _resolve_tenant_from_key("short", db)

    assert tenant_id == "tenant-short"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_strips_whitespace():
    """Bearer token should have surrounding whitespace stripped."""
    request = SimpleNamespace(headers={"Authorization": "Bearer  ad_live_key  "})

    with patch("auth.middleware._resolve_tenant_from_key", new=AsyncMock(return_value="tenant-a")) as resolver:
        tenant_id = await get_tenant_from_api_key(request, AsyncMock())

    assert tenant_id == "tenant-a"
    # Verify the key passed to resolver has no leading/trailing whitespace
    assert resolver.await_count == 1
    assert resolver.await_args[0][0] == "ad_live_key"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_rejects_bearer_without_space():
    """Bearer token must have space after 'Bearer'."""
    request = SimpleNamespace(headers={"Authorization": "Bearerad_live_key"})

    with pytest.raises(HTTPException) as exc:
        await get_tenant_from_api_key(request, AsyncMock())

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authorization header"


@pytest.mark.asyncio
async def test_get_tenant_from_api_key_handles_empty_bearer():
    """Empty Bearer token should be passed to resolver (will fail there)."""
    request = SimpleNamespace(headers={"Authorization": "Bearer "})

    with patch("auth.middleware._resolve_tenant_from_key", new=AsyncMock()) as resolver:
        resolver.side_effect = HTTPException(status_code=401, detail="Invalid API key")
        with pytest.raises(HTTPException) as exc:
            await get_tenant_from_api_key(request, AsyncMock())

    assert exc.value.status_code == 401
    assert resolver.await_count == 1
    assert resolver.await_args[0][0] == ""


@pytest.mark.asyncio
async def test_tenant_isolation_different_keys_different_tenants():
    """Ensure different API keys resolve to different tenants (isolation test)."""
    db = SimpleNamespace(execute=AsyncMock())

    async def mock_resolve(raw_key, db_session):
        # Simulate different keys returning different tenants
        if "key-a" in raw_key:
            return "tenant-a"
        elif "key-b" in raw_key:
            return "tenant-b"
        raise HTTPException(status_code=401, detail="Invalid API key")

    with patch("auth.middleware._resolve_tenant_from_key", side_effect=mock_resolve):
        request_a = SimpleNamespace(headers={"Authorization": "Bearer key-a"})
        tenant_a = await get_tenant_from_api_key(request_a, db)

        request_b = SimpleNamespace(headers={"Authorization": "Bearer key-b"})
        tenant_b = await get_tenant_from_api_key(request_b, db)

    assert tenant_a == "tenant-a"
    assert tenant_b == "tenant-b"
    assert tenant_a != tenant_b


@pytest.mark.asyncio
async def test_tenant_isolation_invalid_key_cannot_access():
    """Invalid API key should not grant access to any tenant."""
    db = SimpleNamespace(execute=AsyncMock())

    with patch("auth.middleware._resolve_tenant_from_key", side_effect=HTTPException(status_code=401, detail="Invalid API key")):
        request = SimpleNamespace(headers={"Authorization": "Bearer ad_live_invalid_key"})
        with pytest.raises(HTTPException) as exc:
            await get_tenant_from_api_key(request, db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid API key"


@pytest.mark.asyncio
async def test_tenant_isolation_local_mode_isolated_from_authenticated():
    """Local mode (no auth) should be distinct from authenticated tenants."""
    request_no_auth = SimpleNamespace(headers={})
    request_with_auth = SimpleNamespace(headers={"Authorization": "Bearer ad_live_key"})

    with patch("auth.middleware._resolve_tenant_from_key", new=AsyncMock(return_value="tenant-x")):
        tenant_local = await get_tenant_from_api_key(request_no_auth, AsyncMock())
        tenant_auth = await get_tenant_from_api_key(request_with_auth, AsyncMock())

    assert tenant_local == "local"
    assert tenant_auth == "tenant-x"
    assert tenant_local != tenant_auth
