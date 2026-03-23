"""Pytest fixtures for test isolation."""
import pytest


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global SDK config before and after each test to ensure isolation."""
    from agent_debugger_sdk import config as cfg_mod
    original_config = cfg_mod._global_config
    cfg_mod._global_config = None
    yield
    cfg_mod._global_config = original_config
