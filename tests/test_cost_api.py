"""Tests for cost summary aggregation queries."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import Session, SessionStatus
from storage.repository import TraceRepository


def _make_session(
    session_id: str,
    framework: str = "pytest",
    total_cost_usd: float = 0.0,
) -> Session:
    return Session(
        id=session_id,
        agent_name="agent",
        framework=framework,
        started_at=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        total_cost_usd=total_cost_usd,
        config={"mode": "test"},
        tags=["cost-test"],
    )


@pytest.mark.asyncio
async def test_get_cost_summary(db_session):
    """Test cost summary with multiple sessions of known costs."""
    repo = TraceRepository(db_session, tenant_id="tenant-cost")

    # Create sessions with known costs: 0.50, 1.25, 0.10
    await repo.create_session(_make_session("session-1", total_cost_usd=0.50))
    await repo.create_session(_make_session("session-2", total_cost_usd=1.25))
    await repo.create_session(_make_session("session-3", total_cost_usd=0.10))
    await repo.commit()

    summary = await repo.get_cost_summary()

    assert summary["session_count"] == 3
    assert summary["total_cost_usd"] == round(0.50 + 1.25 + 0.10, 6)
    assert summary["avg_cost_per_session"] == round((0.50 + 1.25 + 0.10) / 3, 6)
    assert len(summary["by_framework"]) == 1
    assert summary["by_framework"][0]["framework"] == "pytest"
    assert summary["by_framework"][0]["session_count"] == 3
    assert summary["by_framework"][0]["total_cost_usd"] == round(0.50 + 1.25 + 0.10, 6)


@pytest.mark.asyncio
async def test_get_cost_summary_empty(db_session):
    """Test cost summary with no sessions."""
    repo = TraceRepository(db_session, tenant_id="tenant-empty")

    summary = await repo.get_cost_summary()

    assert summary["session_count"] == 0
    assert summary["total_cost_usd"] == 0.0
    assert summary["avg_cost_per_session"] == 0.0
    assert summary["by_framework"] == []


@pytest.mark.asyncio
async def test_get_cost_summary_by_framework(db_session):
    """Test cost summary with sessions from different frameworks."""
    repo = TraceRepository(db_session, tenant_id="tenant-fw")

    # Create sessions across different frameworks
    await repo.create_session(_make_session("session-1", framework="pydantic-ai", total_cost_usd=0.50))
    await repo.create_session(_make_session("session-2", framework="langchain", total_cost_usd=1.25))
    await repo.create_session(_make_session("session-3", framework="pydantic-ai", total_cost_usd=0.10))
    await repo.create_session(_make_session("session-4", framework="autogen", total_cost_usd=2.00))
    await repo.commit()

    summary = await repo.get_cost_summary()

    assert summary["session_count"] == 4
    assert summary["total_cost_usd"] == round(0.50 + 1.25 + 0.10 + 2.00, 6)
    assert summary["avg_cost_per_session"] == round((0.50 + 1.25 + 0.10 + 2.00) / 4, 6)

    # Verify framework breakdown
    by_framework = {fw["framework"]: fw for fw in summary["by_framework"]}
    assert len(by_framework) == 3

    assert by_framework["pydantic-ai"]["session_count"] == 2
    assert by_framework["pydantic-ai"]["total_cost_usd"] == round(0.50 + 0.10, 6)

    assert by_framework["langchain"]["session_count"] == 1
    assert by_framework["langchain"]["total_cost_usd"] == round(1.25, 6)

    assert by_framework["autogen"]["session_count"] == 1
    assert by_framework["autogen"]["total_cost_usd"] == round(2.00, 6)


@pytest.mark.asyncio
async def test_get_session_cost_breakdown(db_session):
    """Test that total_cost_usd is accessible on a fetched session."""
    repo = TraceRepository(db_session, tenant_id="tenant-breakdown")

    # Create a session with a known cost
    await repo.create_session(_make_session("session-cost", total_cost_usd=0.123456))
    await repo.commit()

    # Fetch the session back
    fetched = await repo.get_session("session-cost")
    assert fetched is not None
    assert fetched.total_cost_usd == 0.123456


@pytest.mark.asyncio
async def test_get_cost_summary_tenant_isolation(db_session):
    """Test that cost summary respects tenant isolation."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    # Create sessions in different tenants
    await repo_a.create_session(_make_session("session-a1", total_cost_usd=1.00))
    await repo_a.create_session(_make_session("session-a2", total_cost_usd=2.00))
    await repo_b.create_session(_make_session("session-b1", total_cost_usd=0.50))
    await repo_a.commit()
    await repo_b.commit()

    # Check tenant A summary
    summary_a = await repo_a.get_cost_summary()
    assert summary_a["session_count"] == 2
    assert summary_a["total_cost_usd"] == round(1.00 + 2.00, 6)

    # Check tenant B summary
    summary_b = await repo_b.get_cost_summary()
    assert summary_b["session_count"] == 1
    assert summary_b["total_cost_usd"] == round(0.50, 6)


@pytest.mark.asyncio
async def test_get_cost_summary_with_zero_cost_sessions(db_session):
    """Test cost summary when sessions have zero cost."""
    repo = TraceRepository(db_session, tenant_id="tenant-zero")

    # Create sessions with zero cost
    await repo.create_session(_make_session("zero-1", total_cost_usd=0.0))
    await repo.create_session(_make_session("zero-2", total_cost_usd=0.0))
    await repo.commit()

    summary = await repo.get_cost_summary()
    assert summary["session_count"] == 2
    assert summary["total_cost_usd"] == 0.0
    assert summary["avg_cost_per_session"] == 0.0


@pytest.mark.asyncio
async def test_get_session_cost_with_zero_values(db_session):
    """Test session cost when all values are zero."""
    repo = TraceRepository(db_session, tenant_id="tenant-zero-detail")

    session = _make_session("zero-detail", total_cost_usd=0.0)
    session.total_tokens = 0
    session.llm_calls = 0
    session.tool_calls = 0
    await repo.create_session(session)
    await repo.commit()

    fetched = await repo.get_session("zero-detail")
    assert fetched is not None
    assert fetched.total_cost_usd == 0.0
    assert fetched.total_tokens == 0
    assert fetched.llm_calls == 0
    assert fetched.tool_calls == 0


@pytest.mark.asyncio
async def test_get_cost_summary_single_session(db_session):
    """Test cost summary with exactly one session."""
    repo = TraceRepository(db_session, tenant_id="tenant-single")

    await repo.create_session(_make_session("single", total_cost_usd=3.14))
    await repo.commit()

    summary = await repo.get_cost_summary()
    assert summary["session_count"] == 1
    assert summary["total_cost_usd"] == 3.14
    assert summary["avg_cost_per_session"] == 3.14
    assert len(summary["by_framework"]) == 1


@pytest.mark.asyncio
async def test_get_cost_summary_large_values(db_session):
    """Test cost summary with large cost values (floating point precision)."""
    repo = TraceRepository(db_session, tenant_id="tenant-large")

    await repo.create_session(_make_session("large-1", total_cost_usd=9999.99))
    await repo.create_session(_make_session("large-2", total_cost_usd=0.01))
    await repo.commit()

    summary = await repo.get_cost_summary()
    assert summary["session_count"] == 2
    assert summary["total_cost_usd"] == round(9999.99 + 0.01, 6)
    assert summary["avg_cost_per_session"] == round((9999.99 + 0.01) / 2, 6)
