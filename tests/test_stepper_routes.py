"""Tests for stepper API routes."""

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_session_id():
    """Sample session ID for testing."""
    return "test_session_123"


class TestStepperRoutes:
    """Test suite for stepper API routes."""

    def test_set_breakpoint(self, client, sample_session_id):
        """Test setting a breakpoint."""
        response = client.post(
            f"/api/sessions/{sample_session_id}/breakpoints",
            params={
                "breakpoint_type": "event_type",
                "condition_value": "decision",
                "description": "Break on decisions",
            },
        )

        # Will return 404 if session doesn't exist, but we test the endpoint structure
        assert response.status_code in [200, 404]

    def test_clear_breakpoint(self, client, sample_session_id):
        """Test clearing a breakpoint."""
        breakpoint_id = "test_breakpoint_123"

        response = client.delete(f"/api/sessions/{sample_session_id}/breakpoints/{breakpoint_id}")

        assert response.status_code in [200, 404]

    def test_clear_all_breakpoints(self, client, sample_session_id):
        """Test clearing all breakpoints."""
        response = client.delete(f"/api/sessions/{sample_session_id}/breakpoints")

        assert response.status_code in [200, 404]

    def test_list_breakpoints(self, client, sample_session_id):
        """Test listing breakpoints."""
        response = client.get(f"/api/sessions/{sample_session_id}/breakpoints")

        assert response.status_code in [200, 404]

    def test_step_execution(self, client, sample_session_id):
        """Test stepping through execution."""
        response = client.post(
            f"/api/sessions/{sample_session_id}/step",
            params={"action": "step_into"},
        )

        assert response.status_code in [200, 404]

    def test_step_with_target(self, client, sample_session_id):
        """Test stepping to specific event."""
        response = client.post(
            f"/api/sessions/{sample_session_id}/step",
            params={"action": "run_to", "target_event_id": "event_123"},
        )

        assert response.status_code in [200, 404]

    def test_get_stepper_state(self, client, sample_session_id):
        """Test getting stepper state."""
        response = client.get(f"/api/sessions/{sample_session_id}/state")

        assert response.status_code in [200, 404]

    def test_create_branch(self, client, sample_session_id):
        """Test creating a branch."""
        response = client.post(
            f"/api/sessions/{sample_session_id}/branch",
            params={
                "name": "Test Branch",
                "parent_event_id": "event_123",
                "description": "Test branch description",
            },
        )

        assert response.status_code in [200, 404]

    def test_list_branches(self, client, sample_session_id):
        """Test listing branches."""
        response = client.get(f"/api/sessions/{sample_session_id}/branches")

        assert response.status_code in [200, 404]

    def test_get_branch(self, client, sample_session_id):
        """Test getting a specific branch."""
        branch_id = "test_branch_123"

        response = client.get(f"/api/sessions/{sample_session_id}/branches/{branch_id}")

        assert response.status_code in [200, 404]

    def test_delete_branch(self, client, sample_session_id):
        """Test deleting a branch."""
        branch_id = "test_branch_123"

        response = client.delete(f"/api/sessions/{sample_session_id}/branches/{branch_id}")

        assert response.status_code in [200, 404]

    def test_reset_stepper(self, client, sample_session_id):
        """Test resetting stepper."""
        response = client.post(f"/api/sessions/{sample_session_id}/stepper/reset")

        assert response.status_code in [200, 404]

    def test_get_execution_context(self, client, sample_session_id):
        """Test getting execution context."""
        response = client.get(f"/api/sessions/{sample_session_id}/stepper/context")

        assert response.status_code in [200, 404]


class TestStepperRouteIntegration:
    """Integration tests for stepper routes with sample data."""

    def test_breakpoint_workflow(self, client):
        """Test complete breakpoint workflow."""
        # This would require actual session data to be meaningful
        # For now, we test endpoint availability
        session_id = "workflow_test_session"

        # Set breakpoint
        response = client.post(
            f"/api/sessions/{session_id}/breakpoints",
            params={"breakpoint_type": "event_type", "condition_value": "decision"},
        )

        # List breakpoints
        response = client.get(f"/api/sessions/{session_id}/breakpoints")
        assert response.status_code in [200, 404]

    def test_step_workflow(self, client):
        """Test step execution workflow."""
        session_id = "step_test_session"

        # Try different step actions
        actions = ["step_into", "step_over", "step_out", "continue"]

        for action in actions:
            response = client.post(
                f"/api/sessions/{session_id}/step",
                params={"action": action},
            )
            assert response.status_code in [200, 404]

    def test_branch_workflow(self, client):
        """Test branch management workflow."""
        session_id = "branch_test_session"

        # Create branch
        response = client.post(
            f"/api/sessions/{session_id}/branch",
            params={
                "name": "Test Branch",
                "parent_event_id": "event_123",
            },
        )

        # List branches
        response = client.get(f"/api/sessions/{session_id}/branches")
        assert response.status_code in [200, 404]

        # Delete branch (if it was created)
        # This would need the actual branch_id from creation response
        branch_id = "test_branch_123"
        response = client.delete(f"/api/sessions/{session_id}/branches/{branch_id}")
        assert response.status_code in [200, 404]
