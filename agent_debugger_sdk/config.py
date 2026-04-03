"""SDK configuration and initialization."""

from __future__ import annotations

import os
import threading
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
    max_retries: int = 3
    initial_backoff_seconds: float = 0.5
    _skip_validation: bool = False  # Private: skip validation for testing

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        if not self.endpoint:
            raise ValueError("endpoint_url must be non-empty")

        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError(f"endpoint_url must start with http:// or https://, got: {self.endpoint}")

        if not isinstance(self.max_payload_kb, int) or self.max_payload_kb <= 0:
            raise ValueError(f"max_payload_kb must be a positive integer, got: {self.max_payload_kb}")

        if self.max_payload_kb > 10000:
            raise ValueError(f"max_payload_kb must be at most 10000, got: {self.max_payload_kb}")

        if not isinstance(self.enabled, bool):
            raise ValueError(f"enabled must be a boolean, got: {type(self.enabled).__name__}")

    def __post_init__(self):
        # Apply cloud mode defaults if api_key is present
        if self.api_key and not self._skip_validation:
            self.mode = "cloud"
            if self.endpoint == "http://localhost:8000":
                object.__setattr__(self, "endpoint", "https://api.agentdebugger.dev")

        # Validate unless explicitly skipped (for testing)
        if not self._skip_validation:
            self.validate()

    @classmethod
    def _create_unvalidated(cls, **kwargs: object) -> "Config":
        """Create a Config instance without validation (for testing).

        Args:
            **kwargs: Config field values

        Returns:
            A Config instance with validation skipped
        """
        kwargs["_skip_validation"] = True
        return cls(**kwargs)


_global_config: Config | None = None
_config_lock = threading.Lock()


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
    # Double-checked locking for thread-safe singleton initialization
    global _global_config
    if _global_config is not None:
        return _global_config

    with _config_lock:
        # Check again after acquiring lock
        if _global_config is not None:
            return _global_config

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
    # Double-checked locking for thread-safe singleton initialization
    if _global_config is not None:
        return _global_config

    with _config_lock:
        # Check again after acquiring lock
        if _global_config is not None:
            return _global_config

        _global_config = Config()
        return _global_config


__all__ = ["Config", "init", "get_config"]
