"""Unit tests for auth middleware helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from auth.middleware import _resolve_tenant_from_key
from auth.middleware import get_tenant_from_api_key


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

    with patch("auth.middleware.verify_key", return_value=False):
        with pytest.raises(HTTPException) as exc:
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
