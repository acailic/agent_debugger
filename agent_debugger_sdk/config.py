"""SDK configuration and initialization."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean value from a string.

    Handles: true/false, 1/0, yes/no, on/off (case-insensitive).
    Returns default if value is None or cannot be parsed.
    """
    if value is None:
        return default
    normalized = value.strip().lower()
    true_values = {"true", "1", "yes", "on"}
    false_values = {"false", "0", "no", "off"}
    if normalized in true_values:
        return True
    if normalized in false_values:
        return False
    return default


@dataclass
class Config:
    api_key: str | None = None
    endpoint: str = "http://localhost:8000"
    enabled: bool = True
    redact_prompts: bool = False
    max_payload_kb: int = 100
    mode: str = "local"  # "local" or "cloud"

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        if not self.endpoint:
            raise ValueError("endpoint_url must be non-empty")

        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError(
                f"endpoint_url must start with http:// or https://, got: {self.endpoint}"
            )

        if not isinstance(self.max_payload_kb, int) or self.max_payload_kb <= 0:
            raise ValueError(
                f"max_payload_kb must be a positive integer, got: {self.max_payload_kb}"
            )

        if self.max_payload_kb > 10000:
            raise ValueError(
                f"max_payload_kb must be at most 10000, got: {self.max_payload_kb}"
            )

        if not isinstance(self.enabled, bool):
            raise ValueError(f"enabled must be a boolean, got: {type(self.enabled).__name__}")

    def __post_init__(self):
        self.validate()
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

    resolved_enabled = enabled and _parse_bool(os.environ.get("AGENT_DEBUGGER_ENABLED"), default=True)

    _global_config = Config(
        api_key=resolved_key,
        endpoint=resolved_endpoint,
        enabled=resolved_enabled,
        redact_prompts=_parse_bool(os.environ.get("AGENT_DEBUGGER_REDACT_PROMPTS"), default=redact_prompts),
        max_payload_kb=int(os.environ.get("AGENT_DEBUGGER_MAX_PAYLOAD_KB", max_payload_kb)),
    )
    return _global_config


def get_config() -> Config:
    """Get current config. Returns defaults if init() was not called."""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config
