"""E2E — REAL hosted (cloud-mode) server startup and its auth gates.

The other e2e scenarios run the server in local mode (keyless loopback), so
they prove transport, not auth enforcement; the in-process hosted fixture in
tests/test_hosted_tenant_matrix.py covers the ASGI layer only. This module
starts a genuine uvicorn subprocess in hosted mode — selected purely by the
``AGENT_DEBUGGER_MODE=cloud`` environment variable, the same knob a
deployment would set — with its own temporary database, provisions two
tenants by inserting API keys directly into that database, and asserts over
real HTTP:

- a valid key lists and creates sessions (200/201),
- an ABSENT key on a protected route is rejected with 401 (the negative-auth
  gate at real startup, not just in-process),
- an absent key on the analytics routes is rejected with 401,
- tenant A cannot read tenant B's session (404, no leak),
- and the control case: the plain local-mode server (the suite's shared
  ``e2e_server`` fixture, started WITHOUT cloud mode) still works keyless.

Fixtures are built in-file; tests/e2e/conftest.py is intentionally untouched.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class HostedTenant:
    tenant_id: str
    api_key: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


@dataclass(frozen=True)
class HostedServer:
    base_url: str
    db_url: str
    tenants: tuple[HostedTenant, HostedTenant]
    process: subprocess.Popen

    @property
    def alpha(self) -> HostedTenant:
        return self.tenants[0]

    @property
    def beta(self) -> HostedTenant:
        return self.tenants[1]


@pytest.fixture(scope="session")
def hosted_server(tmp_path_factory: pytest.TempPathFactory) -> HostedServer:
    """Start a real uvicorn subprocess in cloud/hosted mode with two tenants.

    Mode selection is environment-only (``AGENT_DEBUGGER_MODE=cloud``): the
    bootstrap lives in api/main.py ``_bootstrap_server_mode`` and leaves the
    default local-mode behavior unchanged for every other value. The server
    gets its own temporary SQLite database; the two tenants' keys are inserted
    directly into it (auth/api_keys + auth/models layout, as in the e2e
    conftest) because the hosted deployment would provision keys out-of-band.
    """
    tmp = tmp_path_factory.mktemp("e2e-hosted")
    db_url = f"sqlite+aiosqlite:///{tmp}/hosted.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = {
        **os.environ,
        "AGENT_DEBUGGER_DB_URL": db_url,
        "AGENT_DEBUGGER_MODE": "cloud",
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(tmp),  # analytics db and other relative-path side effects stay in tmp
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for the server to come up (tables are created in its lifespan).
    # /api/health is unauthenticated by design in both modes.
    deadline = time.monotonic() + 60
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode(errors="replace") if process.stdout else ""
            raise RuntimeError(f"hosted e2e server died during startup:\n{output[-4000:]}")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if response.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001 - retry until deadline
            last_error = exc
        time.sleep(0.3)
    else:
        process.terminate()
        raise RuntimeError(f"hosted e2e server never became healthy: {last_error}")

    # Provision two tenants straight into the server's database.
    from auth.api_keys import generate_api_key, hash_key
    from auth.models import APIKeyModel
    from storage.engine import create_db_engine

    labels = ("alpha", "beta")
    provisioned: list[HostedTenant] = []
    for label in labels:
        raw_key = generate_api_key(environment="test")
        tenant_id = f"e2e-hosted-tenant-{label}-{uuid.uuid4().hex[:8]}"
        provisioned.append(HostedTenant(tenant_id=tenant_id, api_key=raw_key))

    async def _insert_keys() -> None:
        engine = create_db_engine(db_url)
        try:
            from storage import Base

            async with engine.begin() as conn:
                # Tables were created by the server lifespan; this covers the
                # race where the health endpoint beat schema creation.
                await conn.run_sync(
                    Base.metadata.create_all, tables=[APIKeyModel.__table__]
                )
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine) as session:
                for tenant in provisioned:
                    session.add(
                        APIKeyModel(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant.tenant_id,
                            key_hash=hash_key(tenant.api_key),
                            key_prefix=tenant.api_key[:12],
                            environment="test",
                            name=f"hosted-startup-e2e-{tenant.tenant_id}",
                            is_active=True,
                        )
                    )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_insert_keys())

    yield HostedServer(
        base_url=base_url,
        db_url=db_url,
        tenants=(provisioned[0], provisioned[1]),
        process=process,
    )

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


async def _create_session(base_url: str, tenant: HostedTenant, agent_name: str) -> str:
    """Create a session as a tenant over real HTTP; hosted mode picks the id."""
    async with httpx.AsyncClient(base_url=base_url, headers=tenant.headers, timeout=30.0) as client:
        resp = await client.post(
            "/api/sessions", json={"agent_name": agent_name, "framework": "pytest"}
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]


# ---------------------------------------------------------------------------
# (a) Positive path with a valid key
# ---------------------------------------------------------------------------


async def test_hosted_startup_valid_key_lists_and_creates_sessions(hosted_server):
    async with httpx.AsyncClient(
        base_url=hosted_server.base_url, headers=hosted_server.alpha.headers, timeout=30.0
    ) as client:
        listing = await client.get("/api/sessions")
        assert listing.status_code == 200, listing.text
        assert "sessions" in listing.json()

        created = await client.post(
            "/api/sessions",
            json={"agent_name": "hosted-startup-agent", "framework": "pytest"},
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        assert session_id

        # The created session is readable by its own tenant.
        read = await client.get(f"/api/sessions/{session_id}")
        assert read.status_code == 200
        assert read.json()["session"]["id"] == session_id


# ---------------------------------------------------------------------------
# (b) Negative-auth gate at real startup: ABSENT key on protected routes
# ---------------------------------------------------------------------------


async def test_hosted_startup_absent_key_rejected_on_protected_routes(hosted_server):
    async with httpx.AsyncClient(base_url=hosted_server.base_url, timeout=30.0) as client:
        anonymous_read = await client.get("/api/sessions")
        assert anonymous_read.status_code == 401, anonymous_read.text

        anonymous_create = await client.post(
            "/api/sessions", json={"agent_name": "anon-agent", "framework": "pytest"}
        )
        assert anonymous_create.status_code == 401, (
            "unauthenticated session creation must be rejected at real hosted startup"
        )

        anonymous_trace = await client.post(
            "/api/traces",
            json={"session_id": "any", "event_type": "tool_call", "name": "x"},
        )
        assert anonymous_trace.status_code == 401


# ---------------------------------------------------------------------------
# (c) Analytics routes stay behind the hosted auth gate
# ---------------------------------------------------------------------------


async def test_hosted_startup_absent_key_rejected_on_analytics(hosted_server):
    async with httpx.AsyncClient(base_url=hosted_server.base_url, timeout=30.0) as client:
        assert (await client.get("/api/analytics")).status_code == 401
        anonymous_write = await client.post(
            "/api/analytics/events", json={"event_type": "why_button_click"}
        )
        assert anonymous_write.status_code == 401

    # A valid key does reach the (still shared, local-only) analytics store.
    async with httpx.AsyncClient(
        base_url=hosted_server.base_url, headers=hosted_server.alpha.headers, timeout=30.0
    ) as client:
        authed = await client.get("/api/analytics")
        assert authed.status_code == 200, authed.text


# ---------------------------------------------------------------------------
# (d) Tenant isolation over real HTTP
# ---------------------------------------------------------------------------


async def test_hosted_startup_tenant_cannot_read_other_tenants_session(hosted_server):
    beta_session = await _create_session(
        hosted_server.base_url, hosted_server.beta, "beta-agent"
    )

    async with httpx.AsyncClient(
        base_url=hosted_server.base_url, headers=hosted_server.alpha.headers, timeout=30.0
    ) as client:
        denied = await client.get(f"/api/sessions/{beta_session}")
        assert denied.status_code == 404, "cross-tenant session read must 404, never leak"

    # Beta still sees its own session.
    async with httpx.AsyncClient(
        base_url=hosted_server.base_url, headers=hosted_server.beta.headers, timeout=30.0
    ) as client:
        own = await client.get(f"/api/sessions/{beta_session}")
        assert own.status_code == 200
        assert own.json()["session"]["id"] == beta_session


# ---------------------------------------------------------------------------
# (e) Control: local-mode loopback server stays keyless
# ---------------------------------------------------------------------------


async def test_local_mode_server_still_works_keyless(e2e_server):
    """The suite's plain local-mode server (no AGENT_DEBUGGER_MODE) is the control.

    If hosted-mode gating ever bled into default startup, this keyless
    request would start failing.
    """
    async with httpx.AsyncClient(base_url=e2e_server.base_url, timeout=30.0) as client:
        listing = await client.get("/api/sessions")
        assert listing.status_code == 200, listing.text

        analytics = await client.get("/api/analytics")
        assert analytics.status_code == 200, analytics.text
        assert analytics.json()["range"] == "30d"
