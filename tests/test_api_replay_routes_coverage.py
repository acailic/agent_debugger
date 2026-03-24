"""Tests for API replay routes - targeting 90%+ coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from api.dependencies import get_repository
from api.main import app


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Create a mock repository."""
    repo = AsyncMock()
    repo.get_checkpoint = AsyncMock(return_value=None)
    repo.get_session = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def client(mock_repo) -> TestClient:
    """Create test client with repository dependency overridden."""
    app.dependency_overrides[get_repository] = lambda: mock_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_repository, None)


class TestReplaySessionValidation:
    """Test query parameter validation for the replay endpoint."""

    def test_replay_invalid_mode_returns_422(self, client):
        """Unsupported mode value is rejected."""
        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"mode": "invalid_mode"},
        )
        assert response.status_code == 422

    def test_replay_confidence_above_1_returns_422(self, client):
        """Confidence value > 1.0 is rejected."""
        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"breakpoint_confidence_below": 1.5},
        )
        assert response.status_code == 422

    def test_replay_negative_confidence_returns_422(self, client):
        """Negative confidence value is rejected."""
        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"breakpoint_confidence_below": -0.5},
        )
        assert response.status_code == 422

    def test_replay_confidence_at_zero_is_accepted(self, client, mock_repo):
        """Confidence value 0.0 is a valid edge case (validation only, route may 404)."""
        mock_repo.get_session = AsyncMock(return_value=None)
        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"breakpoint_confidence_below": 0.0},
        )
        # 404 is fine — validation passed, session just doesn't exist
        assert response.status_code in (200, 404, 422)
        assert response.status_code != 422  # 422 would mean validation rejected it

    def test_replay_confidence_at_one_is_accepted(self, client, mock_repo):
        """Confidence value 1.0 is a valid edge case."""
        mock_repo.get_session = AsyncMock(return_value=None)
        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"breakpoint_confidence_below": 1.0},
        )
        assert response.status_code != 422


class TestReplaySessionBehavior:
    """Test replay endpoint behavior."""

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_session_not_found_returns_404(self, mock_load, mock_require, client):
        """Replay on a missing session returns 404."""
        mock_require.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
        response = client.get(f"/api/sessions/{uuid4()}/replay")
        assert response.status_code == 404

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_with_no_events_returns_empty(self, mock_load, mock_require, client):
        """Replay with no events returns 200 with empty events list."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        session_id = str(uuid4())
        response = client.get(f"/api/sessions/{session_id}/replay")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["session_id"] == session_id
        assert data["mode"] == "full"

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_mode_full(self, mock_load, mock_require, client):
        """Replay accepts mode=full."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(f"/api/sessions/{uuid4()}/replay", params={"mode": "full"})
        assert response.status_code == 200
        assert response.json()["mode"] == "full"

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_mode_focus(self, mock_load, mock_require, client):
        """Replay accepts mode=focus."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(f"/api/sessions/{uuid4()}/replay", params={"mode": "focus"})
        assert response.status_code == 200

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_mode_failure(self, mock_load, mock_require, client):
        """Replay accepts mode=failure."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(f"/api/sessions/{uuid4()}/replay", params={"mode": "failure"})
        assert response.status_code == 200

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_with_focus_event_id_parameter(self, mock_load, mock_require, client):
        """Replay accepts focus_event_id parameter."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={"focus_event_id": str(uuid4())},
        )
        assert response.status_code == 200

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_with_breakpoint_parameters(self, mock_load, mock_require, client):
        """Replay accepts breakpoint filter parameters."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(
            f"/api/sessions/{uuid4()}/replay",
            params={
                "breakpoint_event_types": "tool_call,error",
                "breakpoint_tool_names": "search",
                "breakpoint_confidence_below": 0.5,
                "breakpoint_safety_outcomes": "refusal",
            },
        )
        assert response.status_code == 200

    @patch("api.replay_routes.require_session", new_callable=AsyncMock)
    @patch("api.replay_routes.load_session_artifacts", new_callable=AsyncMock)
    def test_replay_default_mode_is_full(self, mock_load, mock_require, client):
        """Default mode is 'full' when not specified."""
        mock_require.return_value = MagicMock()
        mock_load.return_value = ([], [])

        response = client.get(f"/api/sessions/{uuid4()}/replay")
        assert response.json()["mode"] == "full"


class TestGetCheckpointEndpoint:
    """Test the GET /api/checkpoints/{id} endpoint."""

    def test_get_checkpoint_not_found_returns_404(self, client, mock_repo):
        """Missing checkpoint returns 404."""
        mock_repo.get_checkpoint = AsyncMock(return_value=None)

        response = client.get(f"/api/checkpoints/{uuid4()}")
        assert response.status_code == 404

    def test_get_checkpoint_not_found_has_detail(self, client, mock_repo):
        """404 response includes error detail."""
        mock_repo.get_checkpoint = AsyncMock(return_value=None)

        response = client.get("/api/checkpoints/nonexistent-id")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_checkpoint_returns_checkpoint_data(self, client, mock_repo):
        """Existing checkpoint returns checkpoint data."""
        from agent_debugger_sdk.core.events import Checkpoint

        checkpoint = Checkpoint(
            id=str(uuid4()),
            session_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence=1,
            state={"key": "value"},
            memory={},
            timestamp=datetime.now(timezone.utc),
            importance=0.7,
        )
        mock_repo.get_checkpoint = AsyncMock(return_value=checkpoint)

        response = client.get(f"/api/checkpoints/{checkpoint.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == checkpoint.id
        assert data["session_id"] == checkpoint.session_id


class TestRestoreCheckpointEndpoint:
    """Test the POST /api/checkpoints/{id}/restore endpoint."""

    def test_restore_nonexistent_checkpoint_returns_404(self, client, mock_repo):
        """Restoring a missing checkpoint returns 404."""
        mock_repo.get_checkpoint = AsyncMock(return_value=None)

        response = client.post(
            f"/api/checkpoints/{uuid4()}/restore",
            json={"session_id": str(uuid4())},
        )
        assert response.status_code == 404

    def test_restore_returns_restore_response(self, client, mock_repo):
        """Successful restore returns restore response with new session info."""
        from agent_debugger_sdk.core.events import Checkpoint

        checkpoint = Checkpoint(
            id=str(uuid4()),
            session_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence=2,
            state={"agent_state": "active"},
            memory={},
            timestamp=datetime.now(timezone.utc),
            importance=0.9,
        )
        mock_repo.get_checkpoint = AsyncMock(return_value=checkpoint)

        new_session_id = str(uuid4())
        response = client.post(
            f"/api/checkpoints/{checkpoint.id}/restore",
            json={"session_id": new_session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_session_id"] == new_session_id
        assert data["checkpoint_id"] == checkpoint.id
        assert "restore_token" in data

    def test_restore_generates_session_id_when_not_provided(self, client, mock_repo):
        """Restore generates a new session ID when none is provided."""
        from agent_debugger_sdk.core.events import Checkpoint

        checkpoint = Checkpoint(
            id=str(uuid4()),
            session_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence=1,
            state={},
            memory={},
            timestamp=datetime.now(timezone.utc),
            importance=0.5,
        )
        mock_repo.get_checkpoint = AsyncMock(return_value=checkpoint)

        response = client.post(
            f"/api/checkpoints/{checkpoint.id}/restore",
            json={},  # no session_id provided
        )
        assert response.status_code == 200
        data = response.json()
        assert "new_session_id" in data
        assert data["new_session_id"]  # non-empty string
