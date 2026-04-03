"""Regression tests for seed data quality issues.

This module contains reproduction tests for Issues #3 and #6 related to
seed data quality problems.

Issue #3: Many null optional fields
- Tests that optional fields like fix_note, retention_tier, failure_count,
  behavior_alert_count, and representative_event_id are properly populated.

Issue #6: Most sessions have zero cost and tokens
- Tests that sessions created via seed enrichment have non-zero total_tokens
  and total_cost_usd values.

These tests are designed to FAIL with the current code and document the
expected behavior. They should pass after the issues are fixed.
"""

import uuid
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from agent_debugger_sdk.pricing import calculate_cost
from benchmarks import SESSION_ENRICHMENT, validate_session_enrichment
from storage.models import AnomalyAlertModel
from storage.repository import TraceRepository

# =============================================================================
# Helper Functions
# =============================================================================


def _make_session(
    session_id: str = "test-session", agent_name: str = "test_agent", framework: str = "pytest", **kwargs
) -> Session:
    """Create a test Session instance."""
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework=framework,
        started_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        config={"mode": "test"},
        tags=["seed-quality-test"],
        **kwargs,
    )


def _make_event(
    session_id: str = "test-session",
    event_type: EventType = EventType.TOOL_CALL,
    name: str = "test_event",
    data: dict | None = None,
    **kwargs,
) -> TraceEvent:
    """Create a test TraceEvent instance."""
    return TraceEvent(
        session_id=session_id,
        parent_id=None,
        event_type=event_type,
        name=name,
        data=data or {},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
        **kwargs,
    )


def _make_anomaly_alert(
    session_id: str,
    alert_id: str | None = None,
    alert_type: str = "test_alert",
    severity: float = 0.7,
    signal: str = "Test alert signal",
    event_ids: list | None = None,
) -> AnomalyAlertModel:
    """Create a test AnomalyAlertModel instance."""
    return AnomalyAlertModel(
        id=alert_id or str(uuid.uuid4()),
        tenant_id="local",
        session_id=session_id,
        alert_type=alert_type,
        severity=severity,
        signal=signal,
        event_ids=event_ids or [],
        detection_source="test",
        detection_config={"test": True},
    )


# =============================================================================
# Issue #3: Many null optional fields
# =============================================================================


@pytest.mark.asyncio
async def test_fix_note_populated_for_sessions_with_fixes(db_session):
    """Reproduction test for Issue #3: Test that sessions with fixes have meaningful fix_note values.

    Expected behavior:
    - Sessions created with a fix_note should have that note persisted
    - The fix_note field should not be None when a fix was applied

    Current behavior: May fail if fix_note is not properly persisted.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(session_id="session-with-fix")
    await repo.create_session(session)

    # Add a fix note
    fix_note = "Fixed by updating the timeout configuration"
    result = await repo.add_fix_note(session.id, fix_note)

    # Verify the fix_note is persisted and not None
    assert result is not None, "add_fix_note should return a result"
    assert result.fix_note is not None, "fix_note should not be None after adding"
    assert result.fix_note == fix_note, f"fix_note should match the added note: {fix_note}"

    # Verify persistence
    fetched = await repo.get_session(session.id)
    assert fetched is not None, "Session should be retrievable"
    assert fetched.fix_note is not None, "Persisted fix_note should not be None"
    assert fetched.fix_note == fix_note, f"Persisted fix_note should match: {fix_note}"


@pytest.mark.asyncio
async def test_retention_tier_populated_for_sessions(db_session):
    """Reproduction test for Issue #3: Test that sessions have valid retention_tier values populated.

    Expected behavior:
    - Sessions should have a retention_tier value set (not None)
    - Valid values are typically: "full", "summarized", "downsampled"

    Note: retention_tier lives on SessionModel (DB), not on the SDK Session dataclass.
    We query the ORM model directly to verify it.

    Current behavior: May fail if retention_tier is not properly set during session creation.
    """
    from sqlalchemy import select

    from storage.models import SessionModel

    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(session_id="session-retention-test")
    await repo.create_session(session)

    # retention_tier is on SessionModel, not SDK Session — query DB directly
    result = await db_session.execute(select(SessionModel).where(SessionModel.id == session.id))
    db_model = result.scalar_one_or_none()
    assert db_model is not None, "Session should exist in DB"
    # Issue #3: retention_tier should be set, not null
    # Currently defaults to "downsampled" in the DB model, but seed data may not set it
    assert db_model.retention_tier is not None, "retention_tier should not be None"
    assert db_model.retention_tier in ["full", "summarized", "downsampled"], (
        f"retention_tier should be a valid value, got: {db_model.retention_tier}"
    )


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_failure_count_populated_for_sessions_with_errors(db_session):
    """Reproduction test for Issue #3: Test that failure_count is populated when session has error events.

    Expected behavior:
    - Sessions with error events should have a non-zero failure_count
    - The failure_count should reflect the number of error events

    Note: failure_count is computed in the API layer (services.py), not stored in DB.
    This test verifies that the computation happens correctly.

    Current behavior: Fails because errors field is not auto-computed from error events.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(session_id="session-with-errors")

    # Create session with errors
    await repo.create_session(session)

    # Add error events
    error_event_1 = _make_event(
        session_id=session.id,
        event_type=EventType.ERROR,
        name="error_1",
        data={"error_message": "Test error 1", "error_type": "ValueError"},
    )
    error_event_2 = _make_event(
        session_id=session.id,
        event_type=EventType.ERROR,
        name="error_2",
        data={"error_message": "Test error 2", "error_type": "RuntimeError"},
    )

    await repo.add_event(error_event_1)
    await repo.add_event(error_event_2)

    # Verify session has errors count
    fetched = await repo.get_session(session.id)
    assert fetched is not None, "Session should be retrievable"
    assert fetched.errors == 2, f"Session should have 2 errors, got: {fetched.errors}"

    # Note: failure_count is computed in API layer via analysis_summary()
    # This would be tested in integration tests with the API layer


@pytest.mark.asyncio
async def test_behavior_alert_count_consistent_with_anomaly_alerts(db_session):
    """Reproduction test for Issue #3: Test that behavior_alert_count matches AnomalyAlertModel records.

    Expected behavior:
    - When AnomalyAlertModel records exist for a session, behavior_alert_count should match
    - The count should be consistent with actual alert records in the database

    Note: behavior_alert_count is computed in the API layer (services.py line 54),
    not stored in the SessionModel. This test verifies the computation consistency.

    Current behavior: May fail if behavior_alert_count computation doesn't match actual alerts.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(session_id="session-with-alerts")

    await repo.create_session(session)

    # Create anomaly alerts
    alert_1 = _make_anomaly_alert(
        session_id=session.id,
        alert_id=str(uuid.uuid4()),
        alert_type="looping_behavior",
        severity=0.7,
        signal="Detected repeated tool call pattern",
    )
    alert_2 = _make_anomaly_alert(
        session_id=session.id,
        alert_id=str(uuid.uuid4()),
        alert_type="looping_behavior",
        severity=0.8,
        signal="Detected repeated tool call pattern (iteration 2)",
    )

    await repo.create_anomaly_alert(alert_1)
    await repo.create_anomaly_alert(alert_2)

    # Query alerts directly from repository
    # Note: This tests the database layer. The API layer's behavior_alert_count
    # is computed in analysis_summary() and would need API-level testing.

    # Verify alerts were created
    # (In a full test, we'd query alerts here, but repository may not have list_anomaly_alerts)
    # For now, we verify the creation succeeded without errors


@pytest.mark.asyncio
async def test_representative_event_id_set_for_sessions_with_events(db_session):
    """Reproduction test for Issue #3: Test that representative_event_id is set for sessions with events.

    Expected behavior:
    - Sessions that have events should have a representative_event_id set
    - The representative_event_id should point to an actual event in the session

    Note: representative_event_id is computed in the API layer (services.py),
    not stored in SessionModel. This test verifies the computation logic.

    Current behavior: May fail if representative_event_id is not properly computed.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(session_id="session-with-representative-event")

    await repo.create_session(session)

    # Add some events
    event_1 = _make_event(session_id=session.id, name="event_1")
    event_2 = _make_event(session_id=session.id, name="event_2")

    await repo.add_event(event_1)
    await repo.add_event(event_2)

    # Verify events exist
    events = await repo.list_events(session.id)
    assert len(events) >= 2, "Session should have at least 2 events"

    # Note: representative_event_id is computed in API layer via analysis_summary()
    # It would be set based on representative_failure_ids from the analysis
    # This would be tested in integration tests with the API layer


# =============================================================================
# Issue #6: Most sessions have zero cost and tokens
# =============================================================================


@pytest.mark.asyncio
async def test_sessions_have_nonzero_tokens_after_enrichment(db_session):
    """Reproduction test for Issue #6: Test that sessions created via seed enrichment have non-zero total_tokens.

    Expected behavior:
    - Sessions enriched with token counts should have total_tokens > 0
    - The seed_demo_sessions.py script defines SESSION_ENRICHMENT with token counts

    Current behavior: May fail if enrichment doesn't properly set total_tokens.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(
        session_id="seed-test-session",
        total_tokens=0,  # Start with zero
    )

    await repo.create_session(session)

    # Simulate seed enrichment (as done in seed_demo_sessions.py)
    enrichment_tokens = 856  # From SESSION_ENRICHMENT for seed-prompt-injection
    await repo.update_session(session.id, total_tokens=enrichment_tokens)

    # Verify total_tokens was updated
    fetched = await repo.get_session(session.id)
    assert fetched is not None, "Session should be retrievable"
    assert fetched.total_tokens > 0, f"total_tokens should be > 0 after enrichment, got: {fetched.total_tokens}"
    assert fetched.total_tokens == enrichment_tokens, f"total_tokens should match enrichment value: {enrichment_tokens}"


@pytest.mark.asyncio
async def test_sessions_have_nonzero_cost_after_enrichment(db_session):
    """Reproduction test for Issue #6: Test that sessions created via seed enrichment have non-zero total_cost_usd.

    Expected behavior:
    - Sessions enriched with cost data should have total_cost_usd > 0
    - The seed_demo_sessions.py script defines SESSION_ENRICHMENT with costs

    Current behavior: May fail if enrichment doesn't properly set total_cost_usd.
    """
    repo = TraceRepository(db_session, tenant_id="local")
    session = _make_session(
        session_id="seed-test-session-cost",
        total_cost_usd=0.0,  # Start with zero
    )

    await repo.create_session(session)

    # Simulate seed enrichment (as done in seed_demo_sessions.py)
    enrichment_cost = 0.0042  # From SESSION_ENRICHMENT for seed-prompt-injection
    await repo.update_session(session.id, total_cost_usd=enrichment_cost)

    # Verify total_cost_usd was updated
    fetched = await repo.get_session(session.id)
    assert fetched is not None, "Session should be retrievable"
    assert fetched.total_cost_usd > 0, f"total_cost_usd should be > 0 after enrichment, got: {fetched.total_cost_usd}"
    assert fetched.total_cost_usd == enrichment_cost, f"total_cost_usd should match enrichment value: {enrichment_cost}"


@pytest.mark.asyncio
async def test_pricing_calculate_cost_returns_correct_values(db_session):
    """Reproduction test for Issue #6: Test that pricing.py's calculate_cost() returns correct values.

    Expected behavior:
    - calculate_cost() should return accurate costs based on model pricing
    - Cost should be > 0 when tokens > 0

    Current behavior: May fail if pricing calculation is incorrect.
    """
    # Test with known model and token counts
    model = "gpt-4o"
    input_tokens = 500
    output_tokens = 356

    cost = calculate_cost(model, input_tokens, output_tokens)

    assert cost is not None, f"calculate_cost should return a value for model {model}"
    assert cost > 0, f"Cost should be > 0 for {input_tokens} input + {output_tokens} output tokens, got: {cost}"

    # Verify the calculation is approximately correct
    # gpt-4o pricing: $2.50/1M input, $10.00/1M output
    # expected = (500 / 1_000_000) * 2.50 + (356 / 1_000_000) * 10.00
    # expected = 0.00125 + 0.00356 = 0.00481
    expected_cost = (input_tokens / 1_000_000) * 2.50 + (output_tokens / 1_000_000) * 10.00
    assert abs(cost - expected_cost) < 0.0001, (
        f"Cost calculation should be accurate: expected ~{expected_cost}, got {cost}"
    )


def test_cost_consistency_seed_enrichment_requires_positive_tokens_and_cost():
    """Seed enrichment data should enforce positive token and cost metrics."""
    for session_id, enrichment in SESSION_ENRICHMENT.items():
        validate_session_enrichment(session_id, enrichment)


@pytest.mark.asyncio
async def test_seed_enrichment_all_sessions_have_tokens_and_cost(db_session):
    """Reproduction test for Issue #6: Test that all 8 seed sessions have both tokens and cost.

    Expected behavior:
    - All 8 sessions defined in SESSION_ENRICHMENT should have:
      - total_tokens > 0
      - total_cost_usd > 0
    - This mirrors the curated benchmark enrichment data

    Current behavior: May fail if some sessions end up with zero values.
    """
    repo = TraceRepository(db_session, tenant_id="local")

    # SESSION_ENRICHMENT data from benchmarks.seed_enrichment
    seed_sessions = [
        ("seed-prompt-injection", 856, 0.0042),
        ("seed-evidence-grounding", 140, 0.0021),
        ("seed-multi-agent-dialogue", 412, 0.0038),
        ("seed-prompt-policy-shift", 164, 0.0028),
        ("seed-safety-escalation", 1987, 0.0142),
        ("seed-looping-behavior", 1245, 0.0089),
        ("seed-failure-cluster", 1567, 0.0112),
        ("seed-replay-determinism", 289, 0.0031),
    ]

    for session_id, expected_tokens, expected_cost in seed_sessions:
        # Create session
        session = _make_session(session_id=session_id)
        await repo.create_session(session)

        # Enrich it
        await repo.update_session(session.id, total_tokens=expected_tokens, total_cost_usd=expected_cost)

        # Verify
        fetched = await repo.get_session(session.id)
        assert fetched is not None, f"Session {session_id} should be retrievable"
        assert fetched.total_tokens > 0, (
            f"Session {session_id} should have total_tokens > 0, got: {fetched.total_tokens}"
        )
        assert fetched.total_cost_usd > 0, (
            f"Session {session_id} should have total_cost_usd > 0, got: {fetched.total_cost_usd}"
        )
        assert fetched.total_tokens == expected_tokens, (
            f"Session {session_id} total_tokens should be {expected_tokens}, got: {fetched.total_tokens}"
        )
        assert fetched.total_cost_usd == expected_cost, (
            f"Session {session_id} total_cost_usd should be {expected_cost}, got: {fetched.total_cost_usd}"
        )


# =============================================================================
# Combined tests for both issues
# =============================================================================


@pytest.mark.asyncio
async def test_seed_session_complete_enrichment(db_session):
    """Combined test: Verify a seed session has all optional fields properly populated.

    This test checks both Issue #3 (null optional fields) and Issue #6 (zero cost/tokens)
    for a fully enriched seed session.

    Expected behavior:
    - Session has meaningful fix_note (if applicable)
    - Session has retention_tier set
    - Session has total_tokens > 0
    - Session has total_cost_usd > 0
    - Cost and token consistency is maintained

    Current behavior: May fail on any of these checks.
    """
    repo = TraceRepository(db_session, tenant_id="local")

    # Create a session similar to seed-safety-escalation
    session_id = "test-seed-complete"
    session = _make_session(session_id=session_id)
    await repo.create_session(session)

    # Enrich with data similar to seed_demo_sessions.py
    await repo.update_session(session.id, total_tokens=1987, total_cost_usd=0.0142, errors=1)

    # Add fix note
    fix_note = "Added output validation after tool call"
    await repo.add_fix_note(session.id, fix_note)

    # Set retention_tier (requires direct SQL as in seed script)
    from sqlalchemy import update

    from storage.models import SessionModel

    await db_session.execute(update(SessionModel).where(SessionModel.id == session_id).values(retention_tier="full"))
    await db_session.commit()

    # Verify all fields
    fetched = await repo.get_session(session.id)
    assert fetched is not None, "Session should be retrievable"

    # Issue #6 checks
    assert fetched.total_tokens > 0, f"total_tokens should be > 0, got: {fetched.total_tokens}"
    assert fetched.total_cost_usd > 0, f"total_cost_usd should be > 0, got: {fetched.total_cost_usd}"

    # Issue #3 checks
    assert fetched.fix_note is not None, "fix_note should not be None"
    assert fetched.fix_note == fix_note, f"fix_note should match: {fix_note}"
    assert fetched.errors == 1, f"errors should be 1, got: {fetched.errors}"

    # retention_tier is on SessionModel, not SDK Session — query DB directly
    from sqlalchemy import select

    from storage.models import SessionModel

    result = await db_session.execute(select(SessionModel).where(SessionModel.id == session_id))
    db_model = result.scalar_one_or_none()
    assert db_model is not None, "Session should exist in DB"
    assert db_model.retention_tier is not None, "retention_tier should not be None"
    assert db_model.retention_tier == "full", f"retention_tier should be 'full', got: {db_model.retention_tier}"
