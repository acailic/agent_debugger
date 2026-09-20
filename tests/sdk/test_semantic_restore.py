"""SDK semantic checkpoint restore (W04/Q10).

``SessionManager.restore_from_checkpoint`` / ``TraceContext.restore`` must
use the authenticated semantic restore contract
(``POST /api/checkpoints/{id}/restore``): the POST carries the configured
Authorization header (or none in no-key local mode), the returned
session/checkpoint/marker ids are adopted onto the restored object, the
provenance is exposed for callers and the UI, and the restore starts NO
execution. Old servers without the semantic route (404/405) fall back to the
legacy GET-based local reconstruction, marked ``restore_mode="legacy-get"``.

All HTTP here is mocked at the ``session_manager.httpx.AsyncClient`` seam.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from agent_debugger_sdk import config as cfg_mod
from agent_debugger_sdk.core.context.session_manager import (
    RESTORE_MODE_LEGACY,
    RESTORE_MODE_SEMANTIC,
    RestoreProvenance,
    SessionManager,
    _CheckpointRestoreError,
)
from agent_debugger_sdk.core.context.trace_context import TraceContext
from agent_debugger_sdk.core.emitter import EventEmitter

SERVER = "http://restore-mock:8901"


class _FakeResponse:
    """Minimal httpx.Response stand-in (json + raise_for_status)."""

    def __init__(self, status_code: int = 200, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def json(self) -> Any:
        if self._json_data is _NO_JSON:
            raise ValueError("no JSON body")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("POST", f"{SERVER}/api/checkpoints/x/restore"),
                response=httpx.Response(self.status_code),
            )


_NO_JSON = object()


class _ScriptedClient:
    """AsyncClient double that records requests and replays scripted results.

    ``scripted`` is a list of per-request outcomes in call order: a
    ``_FakeResponse`` to return, or an exception to raise. Any request beyond
    the script fails the test, so unexpected HTTP traffic (execution side
    effects) is caught.
    """

    def __init__(self, scripted: list[Any]) -> None:
        self.requests: list[dict[str, Any]] = []
        self._scripted = list(scripted)

    async def __aenter__(self) -> _ScriptedClient:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    def _consume(self, method: str, url: str, **kwargs: Any) -> Any:
        self.requests.append({"method": method, "url": url, **kwargs})
        assert self._scripted, f"unexpected HTTP request: {method} {url} {kwargs}"
        outcome = self._scripted.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def get(self, url: str, **kwargs: Any) -> Any:
        return self._consume("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        return self._consume("POST", url, **kwargs)


def _install_client(monkeypatch: pytest.MonkeyPatch, scripted: list[Any]) -> _ScriptedClient:
    client = _ScriptedClient(scripted)
    monkeypatch.setattr(
        "agent_debugger_sdk.core.context.session_manager.httpx.AsyncClient",
        lambda *args, **kwargs: client,
    )
    return client


def _set_config(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> None:
    monkeypatch.setattr(
        cfg_mod,
        "_global_config",
        cfg_mod.Config(
            api_key=api_key,
            endpoint=SERVER,
            enabled=True,
            _skip_validation=True,
        ),
    )


def _restore_payload(
    *,
    checkpoint_id: str = "sr-cp-111",
    original_session_id: str = "sr-src-111",
    new_session_id: str = "sr-new-111",
) -> dict[str, Any]:
    """A well-formed RestoreResponse body with unique ids."""
    return {
        "checkpoint_id": checkpoint_id,
        "original_session_id": original_session_id,
        "new_session_id": new_session_id,
        "restored_at": "2026-09-20T10:00:00+00:00",
        "state": {"framework": "custom", "data": {"stage": 2}},
        "restore_token": "sr-token-111",
        "replayed_events_count": None,
        "drift_detected": None,
        "copied_event_count": 5,
        "new_checkpoint_id": "sr-newcp-111",
        "restore_event_id": "sr-marker-111",
    }


def _legacy_checkpoint_payload() -> dict[str, Any]:
    return {
        "id": "sr-cp-222",
        "session_id": "sr-src-222",
        "event_id": "sr-anchor-222",
        "sequence": 3,
        "state": {"framework": "custom", "data": {"stage": 1}},
        "memory": {},
        "timestamp": "2026-09-20T09:00:00+00:00",
        "importance": 0.7,
    }


def _post_of(client: _ScriptedClient) -> dict[str, Any]:
    posts = [r for r in client.requests if r["method"] == "POST"]
    assert len(posts) == 1, f"expected exactly one POST, saw {[r['url'] for r in client.requests]}"
    return posts[0]


# ---------------------------------------------------------------------------
# Semantic POST: URL, auth, body
# ---------------------------------------------------------------------------


async def test_semantic_restore_posts_to_restore_url_with_auth_header(monkeypatch):
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    session, state = await SessionManager.restore_from_checkpoint("sr-cp-111", server_url=SERVER)

    post = _post_of(client)
    assert post["url"] == f"{SERVER}/api/checkpoints/sr-cp-111/restore"
    assert post["headers"] == {"Authorization": "Bearer sr-key-123"}
    assert post["json"] == {"session_id": None, "label": ""}

    # The semantic path is a single POST: no GET fallback, no other traffic.
    assert [r["method"] for r in client.requests] == ["POST"]

    # Server-minted ids adopted verbatim.
    assert session.id == "sr-new-111"
    assert state is not None
    assert state.framework == "custom"


async def test_semantic_restore_without_api_key_sends_no_authorization(monkeypatch):
    """No-key local mode: endpoint set, key unset -> POST goes out unauthenticated."""
    _set_config(monkeypatch, api_key=None)
    client = _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    await SessionManager.restore_from_checkpoint("sr-cp-111", server_url=SERVER)

    post = _post_of(client)
    assert "headers" not in post  # no Authorization header anywhere


async def test_semantic_restore_passes_requested_session_id_in_body(monkeypatch):
    _set_config(monkeypatch, api_key="sr-key-123")
    payload = _restore_payload(new_session_id="sr-requested-333")
    client = _install_client(monkeypatch, [_FakeResponse(200, payload)])

    session, _ = await SessionManager.restore_from_checkpoint(
        "sr-cp-111", session_id="sr-requested-333", label="resume run", server_url=SERVER
    )

    post = _post_of(client)
    assert post["json"] == {"session_id": "sr-requested-333", "label": "resume run"}
    assert session.id == "sr-requested-333"  # server echo adopted
    assert session.agent_name == "resume run"


# ---------------------------------------------------------------------------
# Provenance surface
# ---------------------------------------------------------------------------


async def test_session_carries_semantic_provenance(monkeypatch):
    _set_config(monkeypatch, api_key="sr-key-123")
    _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    session, _ = await SessionManager.restore_from_checkpoint("sr-cp-111", server_url=SERVER)

    provenance = session.restore_provenance
    assert isinstance(provenance, RestoreProvenance)
    assert provenance.restore_mode == RESTORE_MODE_SEMANTIC
    assert provenance.source_checkpoint_id == "sr-cp-111"
    assert provenance.source_session_id == "sr-src-111"
    assert provenance.new_session_id == "sr-new-111"
    assert provenance.new_checkpoint_id == "sr-newcp-111"
    assert provenance.restore_event_id == "sr-marker-111"
    assert provenance.copied_event_count == 5
    assert provenance.restore_token == "sr-token-111"
    assert provenance.restored_at == "2026-09-20T10:00:00+00:00"

    # JSON-safe mirror for the UI / delivery path.
    assert session.config["restore_provenance"] == provenance.to_dict()
    assert session.config["restored_from_checkpoint"] == "sr-cp-111"
    assert session.config["original_session_id"] == "sr-src-111"
    assert session.config["restore_token"] == "sr-token-111"


async def test_trace_context_restore_adopts_ids_and_exposes_provenance(monkeypatch):
    _set_config(monkeypatch, api_key="sr-key-123")
    _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    ctx = await TraceContext.restore("sr-cp-111")

    # The context adopts the server-assigned session id.
    assert ctx.session_id == "sr-new-111"
    assert ctx.session.id == "sr-new-111"
    assert ctx.restored_state is not None
    assert ctx.restored_state.data == {"stage": 2}

    provenance = ctx.restore_provenance
    assert provenance is not None
    assert provenance.restore_mode == RESTORE_MODE_SEMANTIC
    assert provenance.new_session_id == ctx.session_id
    assert provenance.new_checkpoint_id == "sr-newcp-111"
    assert provenance.restore_event_id == "sr-marker-111"
    assert provenance.copied_event_count == 5
    assert provenance.source_checkpoint_id == "sr-cp-111"
    assert provenance.source_session_id == "sr-src-111"

    # Config mirror survives for the UI.
    assert ctx.session.config["restore_provenance"]["restore_mode"] == RESTORE_MODE_SEMANTIC


def test_fresh_context_has_no_provenance():
    ctx = TraceContext(session_id="sr-fresh-1")
    assert ctx.restore_provenance is None


# ---------------------------------------------------------------------------
# No execution side effects
# ---------------------------------------------------------------------------


async def test_semantic_restore_starts_no_execution(monkeypatch):
    """Restore is read/copy only: no events, no transport, no context entry."""
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    async def _fail_emit(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("restore must not emit trace events")

    with patch.object(EventEmitter, "emit", _fail_emit):
        ctx = await TraceContext.restore("sr-cp-111")

    # Exactly one HTTP request total (the restore POST): no session-create,
    # no trace deliveries, no checkpoint fetch.
    assert [r["method"] for r in client.requests] == ["POST"]

    assert ctx._entered is False
    assert ctx._transport is None
    assert await ctx.get_events() == []
    assert ctx.replayed_events == []


async def test_semantic_restore_preserves_source_state(monkeypatch):
    """The restore only POSTs; source-side data is never mutated client-side."""
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(monkeypatch, [_FakeResponse(200, _restore_payload())])

    session, _ = await SessionManager.restore_from_checkpoint("sr-cp-111", server_url=SERVER)

    # Nothing deletional or mutational was sent (only the restore POST).
    assert [r["method"] for r in client.requests] == ["POST"]
    assert not any("delete" in r["url"] for r in client.requests)
    # Provenance still points back at the untouched source.
    assert session.restore_provenance.source_session_id == "sr-src-111"


# ---------------------------------------------------------------------------
# Legacy fallback (404/405) and error propagation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fallback_status", [404, 405])
async def test_legacy_fallback_on_missing_semantic_route(monkeypatch, fallback_status):
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(
        monkeypatch,
        [
            _FakeResponse(fallback_status, {"detail": "not found"}),
            _FakeResponse(200, _legacy_checkpoint_payload()),
        ],
    )

    session, state = await SessionManager.restore_from_checkpoint("sr-cp-222", server_url=SERVER)

    # POST first (with auth), then the legacy GET.
    assert [(r["method"], r["url"]) for r in client.requests] == [
        ("POST", f"{SERVER}/api/checkpoints/sr-cp-222/restore"),
        ("GET", f"{SERVER}/api/checkpoints/sr-cp-222"),
    ]
    assert client.requests[1]["headers"] == {"Authorization": "Bearer sr-key-123"}

    # Legacy reconstruction: fresh local id, source referenced, marked as such.
    assert session.id and session.id != "sr-src-222" and len(session.id) == 36
    assert state is not None
    assert state.data == {"stage": 1}
    provenance = session.restore_provenance
    assert provenance.restore_mode == RESTORE_MODE_LEGACY
    assert provenance.source_checkpoint_id == "sr-cp-222"
    assert provenance.source_session_id == "sr-src-222"
    assert provenance.new_session_id == session.id
    assert provenance.new_checkpoint_id is None
    assert provenance.restore_event_id is None
    assert provenance.copied_event_count is None
    assert session.config["restore_provenance"]["restore_mode"] == RESTORE_MODE_LEGACY


async def test_legacy_fallback_without_key_gets_no_auth_header(monkeypatch):
    _set_config(monkeypatch, api_key=None)
    client = _install_client(
        monkeypatch,
        [_FakeResponse(405, None), _FakeResponse(200, _legacy_checkpoint_payload())],
    )

    await SessionManager.restore_from_checkpoint("sr-cp-222", server_url=SERVER)

    assert all("headers" not in r for r in client.requests)


async def test_trace_context_legacy_fallback_marks_provenance(monkeypatch):
    _set_config(monkeypatch, api_key="sr-key-123")
    _install_client(
        monkeypatch,
        [_FakeResponse(404, None), _FakeResponse(200, _legacy_checkpoint_payload())],
    )

    ctx = await TraceContext.restore("sr-cp-222")

    assert ctx.restore_provenance is not None
    assert ctx.restore_provenance.restore_mode == RESTORE_MODE_LEGACY
    assert ctx.session_id == ctx.restore_provenance.new_session_id
    assert ctx.restored_state is not None


async def test_transport_error_on_post_falls_back_to_legacy(monkeypatch):
    """Server unreachable on the semantic route: legacy GET decides the outcome."""
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(
        monkeypatch,
        [
            httpx.ConnectError("connection refused", request=httpx.Request("POST", SERVER)),
            httpx.ConnectError("connection refused", request=httpx.Request("GET", SERVER)),
        ],
    )

    with pytest.raises(_CheckpointRestoreError, match="Network error"):
        await SessionManager.restore_from_checkpoint("sr-cp-222", server_url=SERVER)
    assert len(client.requests) == 2  # POST attempted, then GET failed loudly


@pytest.mark.parametrize("error_status", [401, 409, 500])
async def test_other_http_errors_propagate_clearly(monkeypatch, error_status):
    _set_config(monkeypatch, api_key="sr-key-123")
    client = _install_client(monkeypatch, [_FakeResponse(error_status, {"detail": "boom"})])

    with pytest.raises(_CheckpointRestoreError, match=f"from {SERVER}: {error_status}"):
        await SessionManager.restore_from_checkpoint("sr-cp-222", server_url=SERVER)

    # No silent legacy fallback for real server errors: only the POST ran.
    assert [r["method"] for r in client.requests] == ["POST"]


async def test_non_contract_success_body_falls_back(monkeypatch):
    """A 2xx body that is not a restore response (foreign server) -> legacy."""
    _set_config(monkeypatch, api_key=None)
    client = _install_client(
        monkeypatch,
        [
            _FakeResponse(200, {"unexpected": "shape"}),
            _FakeResponse(200, _legacy_checkpoint_payload()),
        ],
    )

    session, _ = await SessionManager.restore_from_checkpoint("sr-cp-222", server_url=SERVER)

    assert session.restore_provenance.restore_mode == RESTORE_MODE_LEGACY
    assert [r["method"] for r in client.requests] == ["POST", "GET"]
