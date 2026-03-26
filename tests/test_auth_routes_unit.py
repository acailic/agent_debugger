"""Unit tests for standalone auth route handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth_routes import CreateKeyRequest, create_key, list_keys, revoke_key


@pytest.mark.asyncio
async def test_create_key_persists_model_and_returns_raw_key():
    db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())

    with (
        patch("api.auth_routes.generate_api_key", return_value="ad_test_example_secret"),
        patch("api.auth_routes.hash_key", return_value="hashed-secret"),
    ):
        response = await create_key(
            CreateKeyRequest(name="dev", environment="test"),
            db=db,
            tenant_id="tenant-a",
        )

    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    assert response.key == "ad_test_example_secret"
    assert response.key_prefix == "ad_test_exam..."
    assert response.name == "dev"
    assert response.environment == "test"


@pytest.mark.asyncio
async def test_list_keys_returns_active_key_payloads():
    db = SimpleNamespace(execute=AsyncMock())
    keys = [
        SimpleNamespace(
            id="key-1",
            key_prefix="ad_live_abcd...",
            name="primary",
            environment="live",
            created_at="2026-03-23 10:00:00",
            last_used_at=None,
        )
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = keys
    db.execute.return_value = result

    items = await list_keys(db=db, tenant_id="tenant-a")

    assert len(items) == 1
    assert items[0].id == "key-1"
    assert items[0].key_prefix == "ad_live_abcd..."
    assert items[0].environment == "live"
    assert items[0].last_used_at is None


@pytest.mark.asyncio
async def test_revoke_key_marks_key_inactive_and_commits():
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    key = SimpleNamespace(is_active=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = key
    db.execute.return_value = result

    response = await revoke_key("key-1", db=db, tenant_id="tenant-a")

    assert response is None
    assert key.is_active is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_key_raises_not_found_for_missing_key():
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await revoke_key("missing", db=db, tenant_id="tenant-a")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Key not found"
