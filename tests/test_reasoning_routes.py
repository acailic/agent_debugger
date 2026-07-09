"""Tests for reasoning editing API routes (#192)."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_debugger_sdk.core import (
    DecisionEvent,
    EditOperation,
    EventType,
    TraceEvent,
)
from agent_debugger_sdk.core.reasoning_editor import ReasoningEdit, ScenarioBranch
from api.main import app

__all__ = ["TestReasoningRoutesIntegration", "TestReasoningRoutesUnit"]


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_session_id():
    """Create a sample session ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_events(sample_session_id):
    """Create sample events for testing."""
    # Create a decision event with reasoning
    decision = DecisionEvent(
        session_id=sample_session_id,
        name="analyze_request",
        reasoning="1. Parse user input\n2. Identify intent\n3. Choose appropriate tool",
        confidence=0.8,
        chosen_action="call_tool:search",
    )

    # Create an LLM request event
    llm_request = TraceEvent(
        session_id=sample_session_id,
        parent_id=decision.id,
        event_type=EventType.LLM_REQUEST,
        name="llm_request",
        data={"model": "gpt-4", "messages": [{"role": "user", "content": "test"}]},
    )

    # Create another decision
    decision2 = DecisionEvent(
        session_id=sample_session_id,
        parent_id=llm_request.id,
        name="process_response",
        reasoning="Evaluate response quality\ndetermine next action",
        confidence=0.9,
        chosen_action="return_result",
    )

    return [decision, llm_request, decision2]


@pytest.fixture
def mock_repository(sample_events):
    """Create a mock repository with sample data."""
    mock_repo = MagicMock()

    # Mock get_session
    mock_session = MagicMock()
    mock_session.id = sample_events[0].session_id
    mock_session.agent_name = "test_agent"
    mock_session.status = "completed"
    mock_repo.get_session = MagicMock(return_value=mock_session)

    # Mock get_event_tree
    mock_repo.get_event_tree = MagicMock(return_value=sample_events)

    # Mock list_checkpoints
    mock_repo.list_checkpoints = MagicMock(return_value=[])

    return mock_repo


class TestReasoningRoutesIntegration:
    """Integration tests for reasoning routes."""

    def test_edit_reasoning_endpoint(self, test_client, mock_repository, sample_events):
        """Test the edit reasoning endpoint."""
        # This is a placeholder for actual integration testing
        # In real testing, we'd use dependency overrides to inject the mock repository

    def test_create_scenario_branch_endpoint(self, test_client, mock_repository):
        """Test the create scenario branch endpoint."""
        # Placeholder for integration testing

    def test_get_replay_events_endpoint(self, test_client, mock_repository):
        """Test the get replay events endpoint."""
        # Placeholder for integration testing


class TestReasoningRoutesUnit:
    """Unit tests for reasoning route helpers."""

    def test_reasoning_edit_to_response(self):
        """Test converting ReasoningEdit to response schema."""
        from api.reasoning_routes import _reasoning_edit_to_response

        edit = ReasoningEdit(
            operation=EditOperation.MODIFY,
            event_id="event_123",
            field_name="reasoning",
            old_value="old reasoning",
            new_value="new reasoning",
        )

        response = _reasoning_edit_to_response(edit)

        assert response.edit_id == edit.edit_id
        assert response.operation == "modify"
        assert response.event_id == "event_123"
        assert response.old_value == "old reasoning"
        assert response.new_value == "new reasoning"

    def test_scenario_branch_to_response(self):
        """Test converting ScenarioBranch to response schema."""
        from api.reasoning_routes import _scenario_branch_to_response

        branch = ScenarioBranch(
            name="Test branch",
            description="Test scenario",
            parent_event_id="event_123",
            original_session_id="session_456",
        )

        response = _scenario_branch_to_response(branch)

        assert response.branch_id == branch.branch_id
        assert response.name == "Test branch"
        assert response.description == "Test scenario"
        assert response.parent_event_id == "event_123"
        assert response.original_session_id == "session_456"

    def test_event_to_dict(self, sample_events):
        """Test converting TraceEvent to dict."""
        from api.reasoning_routes import _event_to_dict

        event = sample_events[0]
        event_dict = _event_to_dict(event)

        assert "id" in event_dict
        assert "name" in event_dict
        assert "timestamp" in event_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
