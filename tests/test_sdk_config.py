import os
import pytest
from unittest.mock import patch


def test_init_returns_config():
    from agent_debugger_sdk.config import init, get_config
    config = init()
    assert config is not None
    assert config.enabled is True


def test_init_with_api_key_sets_cloud_mode():
    from agent_debugger_sdk.config import init
    config = init(api_key="ad_live_test123")
    assert config.mode == "cloud"
    assert config.api_key == "ad_live_test123"


def test_init_without_api_key_sets_local_mode():
    from agent_debugger_sdk.config import init
    with patch.dict(os.environ, {}, clear=True):
        config = init()
        assert config.mode == "local"


def test_env_var_api_key():
    from agent_debugger_sdk.config import init
    with patch.dict(os.environ, {"AGENT_DEBUGGER_API_KEY": "ad_live_env123"}):
        config = init()
        assert config.api_key == "ad_live_env123"
        assert config.mode == "cloud"


def test_init_disabled():
    from agent_debugger_sdk.config import init
    config = init(enabled=False)
    assert config.enabled is False


def test_get_config_before_init_returns_defaults():
    from agent_debugger_sdk import config as cfg_mod
    cfg_mod._global_config = None  # reset
    config = cfg_mod.get_config()
    assert config.mode == "local"