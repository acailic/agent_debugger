from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from agent_debugger_sdk.config import Config
from api import app_context
from collector import server as collector_server


@pytest.mark.asyncio
async def test_get_tenant_id_rejects_remote_clients_in_local_mode():
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))

    with pytest.raises(HTTPException) as exc_info:
        await collector_server._get_tenant_id(request, SimpleNamespace())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Local mode only accepts requests from localhost"


@pytest.mark.asyncio
async def test_create_session_returns_conflict_for_duplicate_id():
    dependencies = collector_server.CollectorDependencies(
        session_maker=app_context.require_session_maker(),
        buffer=SimpleNamespace(),
        scorer=SimpleNamespace(),
        tenant_resolver=AsyncMock(return_value="local"),
        redaction_pipeline_factory=collector_server._get_redaction_pipeline,
    )
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    session_data = collector_server.SessionCreate(
        id="collector-duplicate-session",
        agent_name="agent",
        framework="pytest",
    )

    first = await collector_server._create_session(session_data, request, dependencies=dependencies)
    assert first.id == "collector-duplicate-session"

    with pytest.raises(HTTPException) as exc_info:
        await collector_server._create_session(session_data, request, dependencies=dependencies)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Session collector-duplicate-session already exists"


def test_resolve_session_id_rejects_explicit_ids_in_cloud_mode():
    with patch.object(collector_server, "get_config", return_value=Config._create_unvalidated(mode="cloud")):
        with pytest.raises(HTTPException) as exc_info:
            collector_server._resolve_session_id("cross-tenant-session")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Explicit session IDs are only supported in local mode"
