"""Test application configuration modes and health endpoint."""

import os
from unittest.mock import patch


def test_create_app_local_mode():
    """App should start in local mode by default."""
    with patch.dict(os.environ, {}, clear=True):
        from api.main import create_app
        app = create_app()
        assert app is not None


def test_create_app_has_health_endpoint():
    from api.main import create_app
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/api/health" in routes or "/health" in routes
