"""Session completeness metadata (roadmap W02).

Covers the pure computation in collector/completeness.py, the
GET /api/sessions/{id}/completeness route (200/404 plus tenant scoping)
and the SDK-side best-effort delivery diagnostics on HttpTransport /
TraceContext.delivery_summary().
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agent_debugger_sdk import config as cfg_mod
from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.context import vars as sdk_vars
from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from agent_debugger_sdk.transport import HttpTransport, RetryConfig
from api.main import create_app
from collector.completeness import compute_session_completeness
from storage import TraceRepository

BASE_TS = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _uid(prefix: str) -> str:
    """Unique id per test; the shared test DB persists across a run."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _event(
    event_id: str,
    *,
    parent_id: str | None = None,
    seq: int | None = None,
    ts: datetime | None = None,
    data: dict | None = None,
    metadata: dict | None = None,
) -> TraceEvent:
    md = dict(metadata or {})
    if seq is not None:
        md.setdefault("sequence", seq)
    return TraceEvent(
        id=event_id,
        session_id="s1",
        parent_id=parent_id,
        event_type=EventType.TOOL_CALL,
        name="completeness_probe",
        timestamp=ts if ts is not None else BASE_TS,
        data=data or {},
        metadata=md,
    )


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------


def test_clean_session_is_all_clear():
    root = _event("e1", seq=1, ts=BASE_TS)
    child_a = _event("e2", parent_id="e1", seq=2, ts=BASE_TS + timedelta(seconds=1))
    child_b = _event("e3", parent_id="e1", seq=3, ts=BASE_TS + timedelta(seconds=2))

    report = compute_session_completeness([root, child_a, child_b])

    assert report.total_events == 3
    assert report.received_event_count == 3
    assert report.expected_event_count == 3
    assert report.expected_source == "sequence_markers"
    assert report.count_match is True
    assert report.missing_parents_count == 0
    assert report.duplicate_id_count == 0
    assert report.truncated is False
    assert report.redaction_applied is False
    assert report.non_monotonic_timestamp_count == 0
    assert report.warnings == []
    assert report.complete is True


def test_missing_parent_is_flagged():
    orphan = _event("orphan-1", parent_id="ghost-parent", seq=2)
    root = _event("root-1", seq=1)

    report = compute_session_completeness([root, orphan])

    assert report.missing_parents_count == 1
    assert report.missing_parent_event_ids == ["orphan-1"]
    assert report.complete is False
    assert any("parent" in warning for warning in report.warnings)


def test_duplicate_ids_are_flagged():
    first = _event("dup-1", ts=BASE_TS)
    second = _event("dup-1", ts=BASE_TS + timedelta(seconds=1))
    other = _event("ok-1", ts=BASE_TS + timedelta(seconds=2))

    report = compute_session_completeness([first, second, other])

    assert report.duplicate_id_count == 1
    assert report.duplicate_ids == ["dup-1"]
    assert report.complete is False
    assert any("duplicate" in warning for warning in report.warnings)


def test_truncation_markers_are_surfaced():
    flagged = _event("trunc-1", metadata={"_truncated": True})
    embedded = _event("trunc-2", data={"content": "partial[TRUNCATED]"})
    clean = _event("trunc-3")

    report = compute_session_completeness([flagged, embedded, clean])

    assert report.truncated is True
    assert report.truncated_event_count == 2
    assert sorted(report.truncated_event_ids) == ["trunc-1", "trunc-2"]
    assert report.complete is False
    assert any("truncated" in warning for warning in report.warnings)


def test_redaction_markers_are_surfaced():
    whole_field = _event("redact-1", data={"content": "[REDACTED]"})
    pii_token = _event("redact-2", data={"messages": ["contact [EMAIL] for details"]})
    secret_token = _event("redact-3", metadata={"auth": "[AWS_ACCESS_KEY]"})
    clean = _event("redact-4")

    report = compute_session_completeness([whole_field, pii_token, secret_token, clean])

    assert report.redaction_applied is True
    assert report.redacted_event_count == 3
    assert "redact-4" not in report.redacted_event_ids
    assert any("redaction" in warning for warning in report.warnings)
    # Redaction alone is a policy notice, not data loss: the session stays
    # complete when everything else is clean.
    assert report.complete is True


def test_sequence_gap_reports_expected_vs_received():
    present = [_event("seq-1", seq=1), _event("seq-2", seq=2), _event("seq-4", seq=4)]

    report = compute_session_completeness(present)

    assert report.expected_event_count == 4
    assert report.received_event_count == 3
    assert report.count_match is False
    assert report.missing_sequence_count == 1
    assert report.missing_sequence_values == [3]
    assert report.complete is False


def test_explicit_hint_overrides_sequence_derivation():
    present = [_event("hint-1", seq=1), _event("hint-2", seq=2), _event("hint-4", seq=4)]

    report = compute_session_completeness(present, expected_event_count=5)

    assert report.expected_event_count == 5
    assert report.expected_source == "hint"
    assert report.count_match is False


def test_without_markers_or_hint_expected_is_unknown():
    events = [_event("plain-1"), _event("plain-2")]

    report = compute_session_completeness(events)

    assert report.expected_event_count is None
    assert report.expected_source is None
    assert report.count_match is None
    assert report.complete is True


def test_non_monotonic_timestamps_counted_in_emission_order():
    # Provided out of order; sequence markers must restore emission order
    # before the timestamp regression check runs.
    first = _event("order-1", seq=1, ts=BASE_TS)
    second = _event("order-2", seq=2, ts=BASE_TS - timedelta(seconds=5))
    third = _event("order-3", seq=3, ts=BASE_TS - timedelta(seconds=10))

    report = compute_session_completeness([third, first, second])

    assert report.non_monotonic_timestamp_count == 2
    assert report.complete is False
    assert any("timestamp" in warning for warning in report.warnings)


def test_id_samples_are_capped_while_counts_stay_full():
    orphans = [_event(f"orphan-{i:02d}", parent_id=f"ghost-{i}") for i in range(25)]
    root = _event("cap-root")

    report = compute_session_completeness([root, *orphans])

    assert report.missing_parents_count == 25
    assert len(report.missing_parent_event_ids) == 20


# ---------------------------------------------------------------------------
# Route: GET /api/sessions/{session_id}/completeness
# ---------------------------------------------------------------------------


def _make_session(session_id: str) -> Session:
    return Session(id=session_id, agent_name="completeness_agent", framework="pytest")


@pytest.mark.asyncio
async def test_completeness_route_reports_clean_session(shared_app):
    """200 with an all-clear report for a well-formed session."""
    session_id = _uid("complete-clean")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session(session_id))
            root = TraceEvent(
                id=_uid("ev"),
                session_id=session_id,
                event_type=EventType.AGENT_START,
                name="session_start",
                timestamp=BASE_TS,
                metadata={"sequence": 1},
            )
            child = TraceEvent(
                id=_uid("ev"),
                session_id=session_id,
                parent_id=root.id,
                event_type=EventType.TOOL_CALL,
                name="search",
                timestamp=BASE_TS + timedelta(seconds=1),
                metadata={"sequence": 2},
            )
            await repo.add_event(root)
            await repo.add_event(child)
            await db_session.commit()

        resp = await client.get(f"/api/sessions/{session_id}/completeness")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["session_id"] == session_id
        assert body["total_events"] == 2
        assert body["expected_event_count"] == 2
        assert body["count_match"] is True
        assert body["missing_parents_count"] == 0
        assert body["duplicate_id_count"] == 0
        assert body["truncated"] is False
        assert body["redaction_applied"] is False
        assert body["warnings"] == []
        assert body["complete"] is True


@pytest.mark.asyncio
async def test_completeness_route_flags_missing_parent_and_gap(shared_app):
    """Persisted markers surface through the route: orphan parent + lost event."""
    session_id = _uid("complete-gap")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_session(_make_session(session_id))
            # Sequences 1 and 3 persisted: emission position 2 was lost.
            first = TraceEvent(
                id=_uid("ev"),
                session_id=session_id,
                event_type=EventType.AGENT_START,
                name="session_start",
                timestamp=BASE_TS,
                metadata={"sequence": 1},
            )
            orphan = TraceEvent(
                id=_uid("ev"),
                session_id=session_id,
                parent_id=_uid("ghost"),
                event_type=EventType.TOOL_RESULT,
                name="search_result",
                timestamp=BASE_TS + timedelta(seconds=1),
                metadata={"sequence": 3},
            )
            await repo.add_event(first)
            await repo.add_event(orphan)
            await db_session.commit()

        resp = await client.get(f"/api/sessions/{session_id}/completeness")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["missing_parents_count"] == 1
        assert body["missing_parent_event_ids"] == [orphan.id]
        assert body["expected_event_count"] == 3
        assert body["received_event_count"] == 2
        assert body["count_match"] is False
        assert body["missing_sequence_values"] == [2]
        assert body["complete"] is False
        assert len(body["warnings"]) >= 2


@pytest.mark.asyncio
async def test_completeness_route_unknown_session_404(shared_app):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{_uid('complete-missing')}/completeness")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_completeness_route_is_tenant_scoped(shared_app):
    """A session persisted under another tenant is invisible: 404, no leak."""
    session_id = _uid("complete-other-tenant")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from api import app_context

        async with app_context.require_session_maker()() as db_session:
            other_repo = TraceRepository(db_session, tenant_id="tenant_other")
            await other_repo.create_session(_make_session(session_id))
            await db_session.commit()

        # Local-mode request resolves tenant "local": the other tenant's
        # session must answer 404 exactly like an unknown id.
        resp = await client.get(f"/api/sessions/{session_id}/completeness")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# SDK delivery diagnostics (HttpTransport counters, TraceContext summary)
# ---------------------------------------------------------------------------


def _sdk_event() -> TraceEvent:
    return TraceEvent(
        session_id="delivery-session",
        event_type=EventType.TOOL_CALL,
        name="probe",
        data={},
        metadata={},
    )


def _sdk_checkpoint():
    from agent_debugger_sdk.core.events import Checkpoint

    return Checkpoint(
        id="cp-1",
        session_id="delivery-session",
        event_id="",
        sequence=1,
        state={},
        memory={},
    )


@pytest.mark.asyncio
async def test_transport_counters_increment_on_success():
    transport = HttpTransport(endpoint="http://localhost:8000")
    with patch.object(transport, "_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_response)

        await transport.send_event(_sdk_event())
        await transport.send_event(_sdk_event())
        await transport.send_checkpoint(_sdk_checkpoint())

    summary = transport.delivery_summary()
    assert summary["events_accepted"] == 2
    assert summary["checkpoints_accepted"] == 1
    assert summary["events_failed"] == 0
    assert summary["checkpoints_failed"] == 0
    assert summary["last_error"] is None

    # The summary is a snapshot: mutating it must not corrupt the counters.
    summary["events_accepted"] = 999
    assert transport.delivery_summary()["events_accepted"] == 2


@pytest.mark.asyncio
async def test_transport_counters_increment_on_failure():
    transport = HttpTransport(endpoint="http://localhost:8000")
    with patch.object(transport, "_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 404  # permanent error: no retries, no sleeps
        mock_client.post = AsyncMock(return_value=mock_response)

        await transport.send_event(_sdk_event())

    summary = transport.delivery_summary()
    assert summary["events_accepted"] == 0
    assert summary["events_failed"] == 1
    assert summary["last_error"] is not None
    assert "not found" in summary["last_error"].lower()


@pytest.mark.asyncio
async def test_context_delivery_summary_is_explicitly_inert_without_transport():
    ctx = TraceContext(session_id=_uid("inert"), agent_name="inert_agent")
    summary = ctx.delivery_summary()

    assert summary["transport_installed"] is False
    assert summary["accepted"] == 0
    assert summary["failed"] == 0
    assert summary["events_accepted"] == 0
    assert summary["checkpoints_accepted"] == 0
    assert summary["last_error"] is None


# Pipeline ContextVars that other tests in this process may have configured;
# a leaked hook would suppress the HTTP transport and break the wiring below.
_PIPELINE_VARS = (
    "_default_event_buffer",
    "_default_event_persister",
    "_default_checkpoint_persister",
    "_default_session_start_hook",
    "_default_session_update_hook",
)


async def _with_clean_pipeline(coro):
    variables = [getattr(sdk_vars, name) for name in _PIPELINE_VARS]
    tokens = [var.set(None) for var in variables]
    try:
        return await coro()
    finally:
        for var, token in zip(variables, tokens):
            var.reset(token)


@pytest.mark.asyncio
async def test_context_delivery_summary_survives_exit_and_reports_failures(monkeypatch):
    """Counters stay readable after __aexit__ closed the transport."""

    class _FastFailTransport(HttpTransport):
        """HttpTransport with retries disabled: unreachable endpoint fails fast."""

        def __init__(self, *args, **kwargs):
            kwargs["retry_config"] = RetryConfig(max_retries=0)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("agent_debugger_sdk.transport.HttpTransport", _FastFailTransport)
    # Port 9 (discard) has nothing listening: every delivery fails.
    cfg_mod.init(endpoint="http://127.0.0.1:9")

    async def scenario():
        async with TraceContext(session_id=_uid("failing"), agent_name="failing_agent") as ctx:
            await ctx.record_tool_call("search", {"query": "probe"})
        return ctx

    ctx = await _with_clean_pipeline(scenario)

    summary = ctx.delivery_summary()
    assert summary["transport_installed"] is True
    assert summary["accepted"] == 0
    # Session start + at least the agent start/end events all failed.
    assert summary["sessions_failed"] >= 1
    assert summary["events_failed"] >= 2
    assert summary["failed"] == summary["sessions_failed"] + summary["events_failed"]
    assert summary["last_error"]
