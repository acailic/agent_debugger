"""SDK configuration and initialization."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    api_key: str | None = None
    endpoint: str = "http://localhost:8000"
    enabled: bool = True
    redact_prompts: bool = False
    max_payload_kb: int = 100
    mode: str = "local"  # "local" or "cloud"

    def __post_init__(self):
        if self.api_key:
            self.mode = "cloud"
            if self.endpoint == "http://localhost:8000":
                self.endpoint = "https://api.agentdebugger.dev"


_global_config: Config | None = None


def init(
    api_key: str | None = None,
    endpoint: str | None = None,
    enabled: bool = True,
    redact_prompts: bool = False,
    max_payload_kb: int = 100,
) -> Config:
    """Initialize the Agent Debugger SDK.

    Call once at application startup. If no api_key is provided,
    falls back to AGENT_DEBUGGER_API_KEY env var. If still no key,
    runs in local mode.
    """
    global _global_config

    resolved_key = api_key or os.environ.get("AGENT_DEBUGGER_API_KEY")
    resolved_endpoint = (
        endpoint
        or os.environ.get("AGENT_DEBUGGER_URL")
        or ("https://api.agentdebugger.dev" if resolved_key else "http://localhost:8000")
    )

    resolved_enabled = enabled and os.environ.get("AGENT_DEBUGGER_ENABLED", "true").lower() != "false"

    _global_config = Config(
        api_key=resolved_key,
        endpoint=resolved_endpoint,
        enabled=resolved_enabled,
        redact_prompts=os.environ.get("AGENT_DEBUGGER_REDACT_PROMPTS", str(redact_prompts)).lower() == "true",
        max_payload_kb=int(os.environ.get("AGENT_DEBUGGER_MAX_PAYLOAD_KB", max_payload_kb)),
    )
    return _global_config


def get_config() -> Config:
    """Get current config. Returns defaults if init() was not called."""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config
