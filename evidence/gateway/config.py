"""Declarative configuration of one evidence gateway instance.

The demo (and the orchestrator wiring) drives the gateway from a JSON
file: ``GatewayConfig.from_json_file(path)``.  Unknown fields are
rejected so a stale or hand-edited config cannot silently change what
the gateway considers approved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evidence.schema import IdentitySource, ToolBinding

__all__ = ["GatewayConfig"]


class GatewayConfig(BaseModel):
    """Everything the gateway needs to run against one upstream server.

    ``principal`` is a *declared* identity (stdio transport, pilot
    scope): nothing authenticates it, which is why every decision event
    records ``identity_source`` alongside it.
    """

    model_config = ConfigDict(extra="forbid")

    gateway_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    identity_source: IdentitySource = IdentitySource.DECLARED
    policy_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    #: Approved tool bindings — a call is allowed only when name AND
    #: schema hash match one of these.
    bindings: list[ToolBinding] = Field(default_factory=list)
    #: Argv used to spawn the real MCP server (used by ``main()``).
    upstream_command: list[str] = Field(min_length=1)
    #: When set, injected into allowed tool calls as the idempotency key
    #: before forwarding (unless the client already supplied one).
    idempotency_argument_name: str | None = None
    upstream_timeout_s: float = Field(default=5.0, gt=0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GatewayConfig:
        """Validate a plain config dict (unknown fields rejected)."""
        return cls.model_validate(data)

    @classmethod
    def from_json_file(cls, path: str | Path) -> GatewayConfig:
        """Load and validate the config from a UTF-8 JSON file."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
