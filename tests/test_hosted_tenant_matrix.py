"""Two-tenant hosted-mode regression matrix (roadmap W10, first slice).

Provisions two tenants with real (bcrypt-hashed) API keys, flips the server
into cloud mode, and drives the in-process ASGI app over HTTP the way a
hosted deployment would. For every route family named in the W10 gate —
session listing/creation, event ingestion, checkpoint write+read, replay,
SSE stream, cross-session clustering, analytics — the matrix asserts
positive isolation: tenant A cannot see or attach to tenant B's session
ids (404 with no mutation).

Routes that remain local-only by design (the analytics store behind the
routes) carry an explicit test documenting that limitation, and the negative
auth gates — absent API key in cloud mode, unauthenticated analytics access
— are enforced here (see docs/hosted-route-inventory.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient


def _uid(prefix: str) -> str:
    """Unique id per seeding; the shared test DB persists across a run."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    api_key: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


@pytest.fixture
def hosted_app():
    """Build the app with cloud-mode config and collector storage wired.

    The autouse ``reset_global_config`` fixture in tests/conftest.py clears
    the SDK config and collector storage before each test, so both must be
    (re)installed here. ``Config._create_unvalidated`` keeps mode="cloud"
    without rewriting the SDK endpoint, matching the pattern used by
    tests/collector/test_collector_server_regressions.py.
    """
    from agent_debugger_sdk import config as cfg_mod
    from api import app_context
    from api.main import create_app
    from collector.server import configure_storage

    cfg_mod._global_config = cfg_mod.Config._create_unvalidated(mode="cloud")
    configure_storage(app_context.require_session_maker())
    return create_app()


@pytest.fixture
def isolated_analytics_db(tmp_path):
    """Point the local-only analytics store at a temp file for this test."""
    import api.analytics_db

    api.analytics_db._set_test_db_path(tmp_path / "analytics.db")
    api.analytics_db.init_analytics_db()
    yield
    api.analytics_db._set_test_db_path(None)


@pytest.fixture
async def tenants(hosted_app):
    """Provision two tenants by inserting API keys directly into the DB.

    Mirrors the server-side key layout used by tests/e2e/conftest.py:
    bcrypt hash plus the raw key's prefix for indexed lookup.
    """
    from api import app_context
    from auth.api_keys import generate_api_key
    from auth.models import APIKeyModel
    from storage import Base

    session_maker = app_context.require_session_maker()
    # Covers the (theoretical) case of this module running before the
    # session-wide schema fixture has registered the auth tables.
    async with app_context.require_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[APIKeyModel.__table__])

    # Keys accumulate in the shared test DB across this run and every
    # authenticated request bcrypt-verifies each ad_test_-prefixed candidate,
    # so default-cost (round 12) hashes would make later tests quadratic.
    # Round-4 hashes keep verification on the real bcrypt path at ~1ms.
    import bcrypt

    def _cheap_hash(raw: str) -> str:
        return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=4)).decode()

    provisioned: list[Tenant] = []
    async with session_maker() as db:
        for label in ("alpha", "beta"):
            raw_key = generate_api_key(environment="test")
            tenant_id = _uid(f"hosted-tenant-{label}")
            db.add(
                APIKeyModel(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    key_hash=_cheap_hash(raw_key),
                    key_prefix=raw_key[:12],
                    environment="test",
                    name=f"tenant-matrix-{label}",
                    is_active=True,
                )
            )
            await db.commit()
            provisioned.append(Tenant(tenant_id=tenant_id, api_key=raw_key))
    yield tuple(provisioned)


@pytest.fixture
async def matrix(hosted_app):
    """Unauthenticated HTTP client; tests pass tenant headers explicitly."""
    transport = ASGITransport(app=hosted_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_session(client: AsyncClient, tenant: Tenant, agent_name: str) -> str:
    """Create a session as a tenant; hosted mode lets the server pick the id."""
    resp = await client.post(
        "/api/sessions",
        json={"agent_name": agent_name, "framework": "pytest"},
        headers=tenant.headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _ingest_event(
    client: AsyncClient,
    tenant: Tenant,
    session_id: str,
    *,
    event_type: str = "tool_call",
    name: str = "matrix_event",
    event_id: str | None = None,
):
    payload: dict = {"session_id": session_id, "event_type": event_type, "name": name}
    if event_id is not None:
        payload["id"] = event_id
    return await client.post("/api/traces", json=payload, headers=tenant.headers)


# ---------------------------------------------------------------------------
# Session listing / creation
# ---------------------------------------------------------------------------


async def test_hosted_session_create_and_listing_isolated(matrix, tenants):
    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")
    beta_session = await _create_session(matrix, beta, "beta-agent")
    assert alpha_session != beta_session

    alpha_list = (await matrix.get("/api/sessions", headers=alpha.headers)).json()
    beta_list = (await matrix.get("/api/sessions", headers=beta.headers)).json()
    alpha_ids = {s["id"] for s in alpha_list["sessions"]}
    beta_ids = {s["id"] for s in beta_list["sessions"]}
    assert alpha_session in alpha_ids and beta_session not in alpha_ids
    assert beta_session in beta_ids and alpha_session not in beta_ids

    # Cross-tenant direct reads must 404, never leak.
    assert (await matrix.get(f"/api/sessions/{beta_session}", headers=alpha.headers)).status_code == 404
    assert (await matrix.get(f"/api/sessions/{alpha_session}", headers=beta.headers)).status_code == 404
    assert (await matrix.get(f"/api/sessions/{alpha_session}", headers=alpha.headers)).status_code == 200


async def test_hosted_explicit_session_id_rejected(matrix, tenants):
    alpha, _ = tenants
    resp = await matrix.post(
        "/api/sessions",
        json={"id": _uid("hosted-explicit"), "agent_name": "a", "framework": "pytest"},
        headers=alpha.headers,
    )
    # Hosted mode forbids caller-chosen session ids (anti-spoofing), so a
    # tenant cannot pre-claim another tenant's session id.
    assert resp.status_code == 400


async def test_hosted_invalid_and_absent_key_behavior(matrix, tenants):
    alpha, _ = tenants
    # A well-formed but unknown key is rejected outright.
    resp = await matrix.get(
        "/api/sessions", headers={"Authorization": "Bearer ad_test_unknown_key_value"}
    )
    assert resp.status_code == 401

    # Closed gap (auth/middleware.py get_tenant_from_api_key): an absent
    # Authorization header in cloud mode is rejected with 401 instead of
    # falling back to the implicit "local" tenant. Reads and writes alike.
    assert (await matrix.get("/api/sessions")).status_code == 401
    anonymous_create = await matrix.post(
        "/api/sessions", json={"agent_name": "anon-agent", "framework": "pytest"}
    )
    assert anonymous_create.status_code == 401, "unauthenticated session creation must be rejected"

    # The collector ingestion path resolves tenants through the same helper
    # and must reject unauthenticated writes too.
    anonymous_trace = await matrix.post(
        "/api/traces", json={"session_id": "any", "event_type": "tool_call", "name": "x"}
    )
    assert anonymous_trace.status_code == 401


# ---------------------------------------------------------------------------
# Event ingestion
# ---------------------------------------------------------------------------


async def test_hosted_event_ingestion_isolated_no_mutation(matrix, tenants):
    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")

    ok = await _ingest_event(matrix, alpha, alpha_session, event_id=_uid("hosted-ev"))
    assert ok.status_code == 202, ok.text

    # Beta tries to attach an event to alpha's session: 404, no mutation.
    hostile_id = _uid("hosted-ev-hostile")
    denied = await _ingest_event(matrix, beta, alpha_session, event_id=hostile_id)
    assert denied.status_code == 404, denied.text

    traces = (await matrix.get(f"/api/sessions/{alpha_session}/traces", headers=alpha.headers)).json()
    stored_ids = {t["id"] for t in traces["traces"]}
    assert hostile_id not in stored_ids, "rejected cross-tenant event must not persist"
    assert len(stored_ids) == 1

    # Beta cannot list alpha's session traces either.
    assert (
        await matrix.get(f"/api/sessions/{alpha_session}/traces", headers=beta.headers)
    ).status_code == 404


# ---------------------------------------------------------------------------
# Checkpoint write + read
# ---------------------------------------------------------------------------


async def test_hosted_checkpoint_write_and_read_isolated_no_mutation(matrix, tenants):
    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")

    anchor_id = _uid("hosted-ev")
    anchored = await _ingest_event(matrix, alpha, alpha_session, event_id=anchor_id)
    assert anchored.status_code == 202, anchored.text

    checkpoint_id = _uid("hosted-cp")
    stored = await matrix.post(
        "/api/checkpoints",
        json={
            "id": checkpoint_id,
            "session_id": alpha_session,
            "event_id": anchor_id,
            "sequence": 1,
            "state": {"step": 1},
            "memory": {},
        },
        headers=alpha.headers,
    )
    assert stored.status_code == 202, stored.text
    assert stored.json()["status"] == "stored"

    # Ownership gate on checkpoint writes (mirrors the event path): beta
    # cannot checkpoint alpha's session, and nothing may persist.
    hostile_checkpoint = _uid("hosted-cp-hostile")
    denied = await matrix.post(
        "/api/checkpoints",
        json={
            "id": hostile_checkpoint,
            "session_id": alpha_session,
            "event_id": "",
            "sequence": 2,
            "state": {"step": 2},
            "memory": {},
        },
        headers=beta.headers,
    )
    assert denied.status_code == 404, denied.text

    alpha_checkpoints = (
        await matrix.get(f"/api/sessions/{alpha_session}/checkpoints", headers=alpha.headers)
    ).json()["checkpoints"]
    assert {cp["id"] for cp in alpha_checkpoints} == {checkpoint_id}, "rejected checkpoint must not persist"

    # Checkpoint reads are tenant-scoped too.
    assert (
        await matrix.get(f"/api/checkpoints/{checkpoint_id}", headers=beta.headers)
    ).status_code == 404
    read = await matrix.get(f"/api/checkpoints/{checkpoint_id}", headers=alpha.headers)
    assert read.status_code == 200
    assert read.json()["id"] == checkpoint_id


async def _store_checkpoint(
    client: AsyncClient,
    tenant: Tenant,
    *,
    session_id: str,
    event_id: str,
    checkpoint_id: str,
):
    return await client.post(
        "/api/checkpoints",
        json={
            "id": checkpoint_id,
            "session_id": session_id,
            "event_id": event_id,
            "sequence": 1,
            "state": {"step": 1},
            "memory": {},
        },
        headers=tenant.headers,
    )


async def test_hosted_checkpoint_event_reference_must_match_session(matrix, tenants):
    """Same-tenant event/session consistency at the HTTP ingest boundary.

    A checkpoint may only reference an event that exists AND belongs to the
    checkpoint's session (platform-audit gap). An anchor event from another
    session of the SAME tenant is a 422 with no rows written; a nonexistent
    event id is a 404 with no rows written.
    """
    alpha, _beta = tenants
    session_a = await _create_session(matrix, alpha, "alpha-agent")
    session_b = await _create_session(matrix, alpha, "alpha-agent")  # same tenant

    anchor_b = _uid("hosted-ev")
    anchored = await _ingest_event(matrix, alpha, session_b, event_id=anchor_b)
    assert anchored.status_code == 202, anchored.text

    # Same-tenant valid pair passes.
    anchor_a = _uid("hosted-ev")
    anchored_a = await _ingest_event(matrix, alpha, session_a, event_id=anchor_a)
    assert anchored_a.status_code == 202, anchored_a.text
    ok = await _store_checkpoint(
        matrix, alpha, session_id=session_a, event_id=anchor_a, checkpoint_id=_uid("hosted-cp")
    )
    assert ok.status_code == 202, ok.text

    # Event from ANOTHER session of the same tenant: rejected, no mutation.
    mismatched = await _store_checkpoint(
        matrix, alpha, session_id=session_a, event_id=anchor_b, checkpoint_id=_uid("hosted-cp")
    )
    assert mismatched.status_code == 422, mismatched.text
    assert anchor_b in mismatched.json()["detail"]

    # Nonexistent event id: rejected, no mutation.
    missing = await _store_checkpoint(
        matrix,
        alpha,
        session_id=session_a,
        event_id=_uid("hosted-ev-never"),
        checkpoint_id=_uid("hosted-cp"),
    )
    assert missing.status_code == 404, missing.text

    stored = (
        await matrix.get(f"/api/sessions/{session_a}/checkpoints", headers=alpha.headers)
    ).json()["checkpoints"]
    assert len(stored) == 1, "only the consistent checkpoint may persist"
    assert stored[0]["event_id"] == anchor_a

    # The anchor event's own session is unaffected too.
    other_session_checkpoints = (
        await matrix.get(f"/api/sessions/{session_b}/checkpoints", headers=alpha.headers)
    ).json()["checkpoints"]
    assert other_session_checkpoints == []


async def test_hosted_checkpoint_cannot_reference_other_tenants_event(matrix, tenants):
    """An event id owned by another tenant is invisible: 404, nothing stored."""
    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")
    beta_session = await _create_session(matrix, beta, "beta-agent")

    beta_event = _uid("hosted-ev")
    ok = await _ingest_event(matrix, beta, beta_session, event_id=beta_event)
    assert ok.status_code == 202, ok.text

    denied = await _store_checkpoint(
        matrix, alpha, session_id=alpha_session, event_id=beta_event, checkpoint_id=_uid("hosted-cp")
    )
    assert denied.status_code == 404, denied.text

    stored = (
        await matrix.get(f"/api/sessions/{alpha_session}/checkpoints", headers=alpha.headers)
    ).json()["checkpoints"]
    assert stored == [], "checkpoint anchored on another tenant's event must not persist"


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


async def test_hosted_replay_route_isolated(matrix, tenants):
    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")
    ok = await _ingest_event(
        matrix,
        alpha,
        alpha_session,
        event_type="error",
        name=_uid("hosted-replay-error"),
    )
    assert ok.status_code == 202, ok.text

    denied = await matrix.get(f"/api/sessions/{alpha_session}/replay", headers=beta.headers)
    assert denied.status_code == 404

    replay = await matrix.get(f"/api/sessions/{alpha_session}/replay", headers=alpha.headers)
    assert replay.status_code == 200
    body = replay.json()
    assert body["session_id"] == alpha_session
    assert body["events"], "own-tenant replay must include the ingested events"


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


async def test_hosted_sse_stream_isolated(matrix, tenants, monkeypatch):
    import api.services.ingestion as ingestion_service

    # Bound the SSE generator so the positive case terminates with a close
    # event instead of holding the connection for the default 300s.
    monkeypatch.setattr(ingestion_service, "DEFAULT_SSE_TIMEOUT", 1)

    alpha, beta = tenants
    alpha_session = await _create_session(matrix, alpha, "alpha-agent")

    denied = await matrix.get(f"/api/sessions/{alpha_session}/stream", headers=beta.headers)
    assert denied.status_code == 404, "cross-tenant stream attach must be rejected before SSE starts"

    streamed = await matrix.get(f"/api/sessions/{alpha_session}/stream", headers=alpha.headers)
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: close" in streamed.text


# ---------------------------------------------------------------------------
# Cross-session clustering
# ---------------------------------------------------------------------------


async def _seed_failure_cluster(client: AsyncClient, tenant: Tenant, error_name: str) -> set[str]:
    """Two sessions sharing one error fingerprint -> one cluster per tenant."""
    session_ids = set()
    for _ in range(2):
        session_id = await _create_session(client, tenant, f"{tenant.tenant_id}-agent")
        resp = await _ingest_event(
            client, tenant, session_id, event_type="error", name=error_name
        )
        assert resp.status_code == 202, resp.text
        session_ids.add(session_id)
    return session_ids


async def test_hosted_cross_session_clustering_isolated(matrix, tenants):
    alpha, beta = tenants
    alpha_error = _uid("hosted-alpha-failure")
    beta_error = _uid("hosted-beta-failure")
    alpha_sessions = await _seed_failure_cluster(matrix, alpha, alpha_error)
    beta_sessions = await _seed_failure_cluster(matrix, beta, beta_error)

    alpha_clusters = (
        await matrix.get("/api/clusters", params={"min_count": 2}, headers=alpha.headers)
    ).json()
    beta_clusters = (
        await matrix.get("/api/clusters", params={"min_count": 2}, headers=beta.headers)
    ).json()

    # This assertion is the gap-1 regression gate: /api/clusters previously
    # hard-coded tenant_id="local", which would have returned zero hosted
    # clusters for either tenant.
    assert alpha_clusters["total"] >= 1, "clusters must be scoped to the caller's tenant"
    assert beta_clusters["total"] >= 1

    alpha_cluster_sessions = {sid for c in alpha_clusters["clusters"] for sid in c["sessions"]}
    beta_cluster_sessions = {sid for c in beta_clusters["clusters"] for sid in c["sessions"]}
    assert alpha_sessions <= alpha_cluster_sessions
    assert beta_sessions <= beta_cluster_sessions
    assert not (alpha_cluster_sessions & beta_sessions), "alpha clusters must not include beta sessions"
    assert not (beta_cluster_sessions & alpha_sessions), "beta clusters must not include alpha sessions"

    alpha_fingerprint = next(
        c["fingerprint"] for c in alpha_clusters["clusters"] if alpha_error in c["fingerprint"]
    )

    # Per-fingerprint cluster lookup inherits the tenant scope.
    denied = await matrix.get(
        f"/api/clusters/{alpha_fingerprint}/sessions", headers=beta.headers
    )
    assert denied.status_code == 404
    allowed = await matrix.get(
        f"/api/clusters/{alpha_fingerprint}/sessions", headers=alpha.headers
    )
    assert allowed.status_code == 200
    assert {s["id"] for s in allowed.json()["sessions"]} == alpha_sessions


# ---------------------------------------------------------------------------
# Analytics — route exposure authenticated in hosted mode (store stays
# local-only by design; that limitation is documented, not fixed here)
# ---------------------------------------------------------------------------


async def test_hosted_analytics_routes_require_a_key(matrix, tenants, isolated_analytics_db):
    alpha, _ = tenants
    # Closed gap: GET/POST /api/analytics* carried no auth dependency. They
    # now share the hosted-mode gate (api.dependencies.require_hosted_auth),
    # so a missing or invalid key is rejected with 401 in cloud mode.
    assert (await matrix.get("/api/analytics")).status_code == 401
    assert (
        await matrix.post(
            "/api/analytics/events", json={"event_type": "why_button_click"}
        )
    ).status_code == 401
    assert (
        await matrix.get("/api/analytics", headers={"Authorization": "Bearer ad_test_unknown"})
    ).status_code == 401

    # A valid key reaches the routes (the underlying store remains the
    # shared local analytics.db — a documented, separate limitation).
    authed_read = await matrix.get("/api/analytics", headers=alpha.headers)
    assert authed_read.status_code == 200
    assert authed_read.json()["range"] == "30d"

    authed_write = await matrix.post(
        "/api/analytics/events",
        json={"event_type": "why_button_click"},
        headers=alpha.headers,
    )
    assert authed_write.status_code == 200
    assert authed_write.json()["recorded"] is True


async def test_local_mode_analytics_stay_fully_open(isolated_analytics_db):
    """Loopback/local mode keeps the analytics routes keyless, as before."""
    from httpx import ASGITransport, AsyncClient

    from agent_debugger_sdk import config as cfg_mod
    from api.main import create_app

    cfg_mod._global_config = cfg_mod.Config._create_unvalidated(mode="local")
    transport = ASGITransport(app=create_app())  # loopback client by default
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        read = await client.get("/api/analytics")
        assert read.status_code == 200, read.text
        assert read.json()["range"] == "30d"

        write = await client.post("/api/analytics/events", json={"event_type": "nl_query"})
        assert write.status_code == 200
        assert write.json()["recorded"] is True
