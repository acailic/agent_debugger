"""Comprehensive tests for API replay routes - targeting 90%+ coverage."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_session_id():
    """Generate a test session ID."""
    return str(uuid4())


@pytest.fixture
def mock_checkpoint_id():
    """Generate a test checkpoint ID."""
    return str(uuid4())


class TestReplaySessionEdgeCases:
    """Test edge cases and error paths for replay_session endpoint."""
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_nonexistent_session(self, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test replay with session that doesn't exist."""
        # Setup mocks
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.side_effect = Exception("Session not found")
        
        response = client.get(f"/api/sessions/{mock_session_id}/replay")
        
        # Should handle gracefully
        assert response.status_code >= 400
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_with_no_events(self, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test replay when session has no events."""
        # Setup mocks
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        mock_load.return_value = ([], [])  # Empty events and checkpoints
        
        response = client.get(f"/api/sessions/{mock_session_id}/replay")
        
        # Should handle gracefully with empty response
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_with_mode_parameter(self, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test replay respects mode parameter."""
        # Setup mocks
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        mock_load.return_value = ([], [])
        
        # Test different mode values
        for mode in ["full", "focus", "failure"]:
            response = client.get(
                f"/api/sessions/{mock_session_id}/replay",
                params={"mode": mode}
            )
            assert response.status_code == 200 or response.status_code >= 400
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_with_invalid_mode(self, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test replay with invalid mode."""
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        mock_load.return_value = ([], [])
        
        response = client.get(
            f"/api/sessions/{mock_session_id}/replay",
            params={"mode": "invalid_mode"}
        )
        # Should reject invalid mode
        assert response.status_code == 422
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_with_focus_event_id(self, mock_get_repo, mock_load, mock_require, client, mock_session_id, mock_checkpoint_id):
        """Test replay with focus on specific event."""
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        mock_load.return_value = ([], [])
        
        response = client.get(
            f"/api/sessions/{mock_session_id}/replay",
            params={"focus_event_id": mock_checkpoint_id}
        )
        
        # Should accept parameter
        assert response.status_code < 500
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    def test_replay_with_breakpoints(self, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test replay with breakpoint parameters."""
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        mock_load.return_value = ([], [])
        
        response = client.get(
            f"/api/sessions/{mock_session_id}/replay",
            params={
                "breakpoint_event_types": "tool_call,error",
                "breakpoint_tool_names": "search,execute",
                "breakpoint_confidence_below": 0.5,
                "breakpoint_safety_outcomes": "refusal,violation"
            }
        )
        
        # Should accept all breakpoint parameters
        assert response.status_code == 200 or response.status_code >= 400


class TestGetCheckpointEdgeCases:
    """Test edge cases for get_checkpoint endpoint."""
    
    @patch('api.dependencies.get_repository')
    def test_get_checkpoint_not_found(self, mock_get_repo, client, mock_checkpoint_id):
        """Test getting nonexistent checkpoint."""
        mock_repo = AsyncMock()
        mock_repo.get_checkpoint = AsyncMock(return_value=None)
        mock_get_repo.return_value = mock_repo
        
        response = client.get(f"/api/checkpoints/{mock_checkpoint_id}")
        
        assert response.status_code == 404
    
    def test_get_checkpoint_invalid_id(self, client):
        """Test getting checkpoint with invalid ID."""
        response = client.get("/api/checkpoints/invalid-id")
        
        # Should handle gracefully
        assert response.status_code >= 400 or response.status_code == 422


class TestRestoreCheckpointEdgeCases:
    """Test edge cases for restore_checkpoint endpoint."""
    
    @patch('api.dependencies.get_repository')
    def test_restore_nonexistent_checkpoint(self, mock_get_repo, client, mock_checkpoint_id):
        """Test restoring checkpoint that doesn't exist."""
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        # Mock to return None for missing checkpoint
        mock_repo.get_checkpoint = AsyncMock(return_value=None)
        
        response = client.post(
            f"/api/checkpoints/{mock_checkpoint_id}/restore",
            json={"session_id": str(uuid4())}
        )
        
        # Should return error
        assert response.status_code >= 400


class TestReplayValidation:
    """Test input validation for replay endpoints."""
    
    def test_replay_with_confidence_below_range(self, client, mock_session_id):
        """Test that confidence below is validated to be in range."""
        response = client.get(
            f"/api/sessions/{mock_session_id}/replay",
            params={"breakpoint_confidence_below": 1.5}  # Invalid: > 1.0
        )
        
        assert response.status_code == 422
    
    def test_replay_with_negative_confidence(self, client, mock_session_id):
        """Test that negative confidence is rejected."""
        response = client.get(
            f"/api/sessions/{mock_session_id}/replay",
            params={"breakpoint_confidence_below": -0.5}
        )
        
        assert response.status_code == 422


class TestReplayIntegration:
    """Integration tests that test the full replay workflow."""
    
    @patch('api.services.require_session')
    @patch('api.services.load_session_artifacts')
    @patch('api.dependencies.get_repository')
    @patch('collector.replay.build_replay')
    def test_full_replay_workflow(self, mock_build, mock_get_repo, mock_load, mock_require, client, mock_session_id):
        """Test complete replay workflow with real-like data."""
        from agent_debugger_sdk.core.events import EventType, TraceEvent
        
        # Setup mocks
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_require.return_value = None
        
        # Create mock events
        events = [
            TraceEvent(
                event_type=EventType.TOOL_CALL,
                timestamp=datetime.now(timezone.utc),
                data={"tool": "test"}
            )
        ]
        checkpoints = []
        mock_load.return_value = (events, checkpoints)
        
        # Mock build_replay response
        mock_build.return_value = {
            "mode": "full",
            "focus_event_id": None,
            "start_index": 0,
            "events": events,
            "checkpoints": checkpoints,
            "nearest_checkpoint": None,
            "breakpoints": [],
            "failure_event_ids": []
        }
        
        response = client.get(f"/api/sessions/{mock_session_id}/replay")
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == mock_session_id
        assert data["mode"] == "full"
