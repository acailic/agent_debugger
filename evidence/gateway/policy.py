"""Tool approval policy: name + input-schema binding checks.

The gateway allows a tool call only when the configuration carries a
:class:`~evidence.schema.ToolBinding` whose ``tool_name`` matches and
whose ``input_schema_hash`` equals the hash of the schema currently
served by the upstream.  A schema drift (same name, different hash)
denies the call and hides the tool until the operator re-approves it
explicitly; a tool with no binding at all is simply unapproved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evidence.schema import ToolBinding, input_schema_hash

__all__ = [
    "REASON_ALLOW",
    "REASON_UNAPPROVED_TOOL",
    "REASON_SCHEMA_CHANGED",
    "PolicyDecision",
    "ToolPolicy",
]

REASON_ALLOW = "allow"
REASON_UNAPPROVED_TOOL = "unapproved_tool"
REASON_SCHEMA_CHANGED = "schema_changed"


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of one policy evaluation.

    ``binding`` is the matched approval on allow; on ``schema_changed``
    it carries the stale approval (the one that needs re-approval),
    and it is ``None`` for tools with no binding at all.
    """

    allowed: bool
    reason: str
    binding: ToolBinding | None = None


class ToolPolicy:
    """Immutable view over the config's approved tool bindings."""

    def __init__(self, bindings: list[ToolBinding]) -> None:
        self._by_name: dict[str, list[ToolBinding]] = {}
        for binding in bindings:
            self._by_name.setdefault(binding.tool_name, []).append(binding)

    def check(self, tool_name: str, input_schema: dict[str, Any] | None) -> PolicyDecision:
        """Decide one tool call from its name and currently served schema."""
        candidates = self._by_name.get(tool_name, [])
        if not candidates:
            return PolicyDecision(allowed=False, reason=REASON_UNAPPROVED_TOOL, binding=None)
        schema_hash = input_schema_hash(input_schema if input_schema is not None else {})
        for binding in candidates:
            if binding.input_schema_hash == schema_hash:
                return PolicyDecision(allowed=True, reason=REASON_ALLOW, binding=binding)
        return PolicyDecision(allowed=False, reason=REASON_SCHEMA_CHANGED, binding=candidates[0])

    def visible_tools(self, upstream_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter ``tools/list`` down to tools the agent may even see.

        Unapproved and schema-drifted tools disappear from discovery so
        the agent never learns they exist.
        """
        visible: list[dict[str, Any]] = []
        for tool in upstream_tools:
            name = tool.get("name")
            if isinstance(name, str) and self.check(name, tool.get("inputSchema")).allowed:
                visible.append(tool)
        return visible
