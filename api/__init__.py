"""API module for Agent Debugger.

This module provides the FastAPI application factory and endpoints
for the Agent Debugger service.
"""

from .main import app, create_app

__all__ = ["app", "create_app"]
