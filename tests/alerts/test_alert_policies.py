"""Tests for alert policy repository and API endpoints."""

from __future__ import annotations

import pytest

from storage import AlertPolicyRepository


@pytest.mark.asyncio
async def test_create_policy(db_session):
    """Test creating a new alert policy."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    policy = await repo.create_policy(
        agent_name="test-agent",
        alert_type="tool_loop",
        threshold_value=3.0,
        severity_threshold="high",
        enabled=True,
    )

    assert policy.id is not None
    assert policy.agent_name == "test-agent"
    assert policy.alert_type == "tool_loop"
    assert policy.threshold_value == 3.0
    assert policy.severity_threshold == "high"
    assert policy.enabled is True
    assert policy.tenant_id == "test-tenant"


@pytest.mark.asyncio
async def test_create_global_policy(db_session):
    """Test creating a global policy (agent_name is None)."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    policy = await repo.create_policy(
        agent_name=None,
        alert_type="high_error_rate",
        threshold_value=0.5,
        enabled=True,
    )

    assert policy.agent_name is None
    assert policy.alert_type == "high_error_rate"


@pytest.mark.asyncio
async def test_get_policy(db_session):
    """Test retrieving a policy by ID."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    created = await repo.create_policy(
        agent_name="test-agent",
        alert_type="tool_loop",
        threshold_value=3.0,
    )
    await db_session.commit()

    retrieved = await repo.get_policy(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.alert_type == "tool_loop"


@pytest.mark.asyncio
async def test_get_policy_not_found(db_session):
    """Test retrieving a non-existent policy returns None."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    retrieved = await repo.get_policy("non-existent-id")

    assert retrieved is None


@pytest.mark.asyncio
async def test_list_policies(db_session):
    """Test listing all policies."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    # Create multiple policies
    await repo.create_policy(agent_name="agent-1", alert_type="tool_loop", threshold_value=3.0)
    await repo.create_policy(agent_name="agent-2", alert_type="high_error_rate", threshold_value=0.5)
    await repo.create_policy(agent_name=None, alert_type="global_policy", threshold_value=1.0)
    await db_session.commit()

    policies = await repo.list_policies()

    assert len(policies) == 3
    alert_types = {p.alert_type for p in policies}
    assert "tool_loop" in alert_types
    assert "high_error_rate" in alert_types
    assert "global_policy" in alert_types


@pytest.mark.asyncio
async def test_list_policies_filtered_by_agent(db_session):
    """Test listing policies filtered by agent_name."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    # Create policies for different agents
    await repo.create_policy(agent_name="agent-1", alert_type="tool_loop", threshold_value=3.0)
    await repo.create_policy(agent_name="agent-1", alert_type="high_error_rate", threshold_value=0.5)
    await repo.create_policy(agent_name="agent-2", alert_type="tool_loop", threshold_value=5.0)
    await repo.create_policy(agent_name=None, alert_type="tool_loop", threshold_value=2.0)
    await db_session.commit()

    # List policies for agent-1 (should include agent-1 specific and global policies)
    policies = await repo.list_policies(agent_name="agent-1")

    assert len(policies) == 3  # 2 agent-1 specific + 1 global
    agent_names = {p.agent_name for p in policies}
    assert "agent-1" in agent_names
    assert None in agent_names  # Global policy


@pytest.mark.asyncio
async def test_update_policy(db_session):
    """Test updating an existing policy."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    created = await repo.create_policy(
        agent_name="test-agent",
        alert_type="tool_loop",
        threshold_value=3.0,
        severity_threshold="high",
        enabled=True,
    )
    await db_session.commit()

    updated = await repo.update_policy(
        created.id,
        threshold_value=5.0,
        severity_threshold="critical",
        enabled=False,
    )
    await db_session.commit()

    assert updated is not None
    assert updated.threshold_value == 5.0
    assert updated.severity_threshold == "critical"
    assert updated.enabled is False
    # Unchanged fields
    assert updated.agent_name == "test-agent"
    assert updated.alert_type == "tool_loop"


@pytest.mark.asyncio
async def test_update_policy_not_found(db_session):
    """Test updating a non-existent policy returns None."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    updated = await repo.update_policy("non-existent-id", threshold_value=5.0)

    assert updated is None


@pytest.mark.asyncio
async def test_delete_policy(db_session):
    """Test deleting a policy."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    created = await repo.create_policy(
        agent_name="test-agent",
        alert_type="tool_loop",
        threshold_value=3.0,
    )
    await db_session.commit()

    deleted = await repo.delete_policy(created.id)
    await db_session.commit()

    assert deleted is True

    # Verify policy is gone
    retrieved = await repo.get_policy(created.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_delete_policy_not_found(db_session):
    """Test deleting a non-existent policy returns False."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    deleted = await repo.delete_policy("non-existent-id")

    assert deleted is False


@pytest.mark.asyncio
async def test_get_active_policy_for_agent_specific(db_session):
    """Test getting active policy prefers agent-specific over global."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    # Create both agent-specific and global policies
    await repo.create_policy(agent_name="test-agent", alert_type="tool_loop", threshold_value=5.0)
    await repo.create_policy(agent_name=None, alert_type="tool_loop", threshold_value=2.0)
    await db_session.commit()

    # Should return agent-specific policy
    policy = await repo.get_active_policy_for("tool_loop", agent_name="test-agent")

    assert policy is not None
    assert policy.threshold_value == 5.0
    assert policy.agent_name == "test-agent"


@pytest.mark.asyncio
async def test_get_active_policy_falls_back_to_global(db_session):
    """Test getting active policy falls back to global if no agent-specific policy."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    # Create only global policy
    await repo.create_policy(agent_name=None, alert_type="tool_loop", threshold_value=2.0)
    await db_session.commit()

    # Should return global policy
    policy = await repo.get_active_policy_for("tool_loop", agent_name="test-agent")

    assert policy is not None
    assert policy.threshold_value == 2.0
    assert policy.agent_name is None


@pytest.mark.asyncio
async def test_get_active_policy_disabled_not_returned(db_session):
    """Test that disabled policies are not returned by get_active_policy_for."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    # Create disabled policy
    await repo.create_policy(
        agent_name=None, alert_type="tool_loop", threshold_value=2.0, enabled=False
    )
    await db_session.commit()

    policy = await repo.get_active_policy_for("tool_loop", agent_name="test-agent")

    assert policy is None


@pytest.mark.asyncio
async def test_get_active_policy_no_policy_found(db_session):
    """Test get_active_policy_for returns None when no policy exists."""
    repo = AlertPolicyRepository(db_session, tenant_id="test-tenant")

    policy = await repo.get_active_policy_for("non_existent_alert", agent_name="test-agent")

    assert policy is None


@pytest.mark.asyncio
async def test_policy_tenant_isolation(db_session):
    """Test that policies are isolated by tenant_id."""
    repo1 = AlertPolicyRepository(db_session, tenant_id="tenant-1")
    repo2 = AlertPolicyRepository(db_session, tenant_id="tenant-2")

    # Create policy in tenant-1
    await repo1.create_policy(agent_name="test-agent", alert_type="tool_loop", threshold_value=3.0)
    await db_session.commit()

    # tenant-2 should not see tenant-1's policy
    policies = await repo2.list_policies()
    assert len(policies) == 0

    # tenant-1 should see their policy
    policies = await repo1.list_policies()
    assert len(policies) == 1
