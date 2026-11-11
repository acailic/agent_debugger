"""ToolPolicy approval and tools/list visibility tests."""

import pytest

from evidence.gateway.policy import (
    REASON_ALLOW,
    REASON_SCHEMA_CHANGED,
    REASON_UNAPPROVED_TOOL,
    ToolPolicy,
)
from evidence.schema import ToolBinding, input_schema_hash

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "status": {"type": "string"},
    },
    "required": ["claim_id", "status"],
}

CLAIM_SCHEMA_DRIFTED = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "status": {"type": "string"},
        "reason_code": {"type": "string"},
    },
    "required": ["claim_id", "status"],
}

DELETE_SCHEMA = {
    "type": "object",
    "properties": {"confirm": {"type": "boolean"}},
    "required": ["confirm"],
}


def binding_for(name: str, schema: dict, config_version: str = "cfg-1") -> ToolBinding:
    return ToolBinding(
        tool_name=name,
        input_schema_hash=input_schema_hash(schema),
        approved_server="fake-mcp-server",
        config_version=config_version,
    )


class TestToolPolicyCheck:
    def test_matching_name_and_schema_is_allowed(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        decision = policy.check("update_claim_status", CLAIM_SCHEMA)
        assert decision.allowed is True
        assert decision.reason == REASON_ALLOW
        assert decision.binding is not None
        assert decision.binding.tool_name == "update_claim_status"

    def test_binding_attached_to_allow_decision_carries_config_version(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA, config_version="cfg-7")])
        decision = policy.check("update_claim_status", CLAIM_SCHEMA)
        assert decision.binding is not None
        assert decision.binding.config_version == "cfg-7"

    def test_unknown_tool_is_denied_as_unapproved(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        decision = policy.check("delete_everything", DELETE_SCHEMA)
        assert decision.allowed is False
        assert decision.reason == REASON_UNAPPROVED_TOOL
        assert decision.binding is None

    def test_schema_drift_is_denied_as_schema_changed(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        decision = policy.check("update_claim_status", CLAIM_SCHEMA_DRIFTED)
        assert decision.allowed is False
        assert decision.reason == REASON_SCHEMA_CHANGED
        # the stale approval is attached: it is the one needing re-approval
        assert decision.binding is not None
        assert decision.binding.input_schema_hash == input_schema_hash(CLAIM_SCHEMA)

    def test_no_bindings_at_all_denies_everything(self):
        policy = ToolPolicy([])
        decision = policy.check("update_claim_status", CLAIM_SCHEMA)
        assert decision.allowed is False
        assert decision.reason == REASON_UNAPPROVED_TOOL

    def test_same_schema_hash_under_other_tool_name_is_unapproved(self):
        # the drifted schema is itself bound, but for another tool name
        policy = ToolPolicy([binding_for("other_tool", CLAIM_SCHEMA)])
        decision = policy.check("update_claim_status", CLAIM_SCHEMA)
        assert decision.allowed is False
        assert decision.reason == REASON_UNAPPROVED_TOOL

    def test_schema_key_order_does_not_change_the_decision(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        reordered = {
            "required": ["claim_id", "status"],
            "properties": {"status": {"type": "string"}, "claim_id": {"type": "string"}},
            "type": "object",
        }
        assert policy.check("update_claim_status", reordered).allowed is True

    @pytest.mark.parametrize("schema", [None, {}])
    def test_missing_schema_never_matches_a_binding(self, schema):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        decision = policy.check("update_claim_status", schema)
        assert decision.allowed is False
        assert decision.reason == REASON_SCHEMA_CHANGED


class TestVisibleTools:
    def test_unapproved_tools_are_filtered_out(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        visible = policy.visible_tools(
            [
                {"name": "update_claim_status", "inputSchema": CLAIM_SCHEMA},
                {"name": "delete_everything", "inputSchema": DELETE_SCHEMA},
            ]
        )
        assert [tool["name"] for tool in visible] == ["update_claim_status"]

    def test_schema_drifted_tool_is_hidden_until_reapproval(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        visible = policy.visible_tools(
            [{"name": "update_claim_status", "inputSchema": CLAIM_SCHEMA_DRIFTED}]
        )
        assert visible == []

    def test_visible_tools_keeps_the_tool_dicts_untouched(self):
        approved = {"name": "update_claim_status", "inputSchema": CLAIM_SCHEMA}
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        visible = policy.visible_tools([approved])
        assert visible == [approved]

    def test_all_tools_hidden_without_bindings(self):
        policy = ToolPolicy([])
        visible = policy.visible_tools([{"name": "update_claim_status", "inputSchema": CLAIM_SCHEMA}])
        assert visible == []

    def test_tool_without_a_schema_is_hidden(self):
        policy = ToolPolicy([binding_for("update_claim_status", CLAIM_SCHEMA)])
        visible = policy.visible_tools([{"name": "update_claim_status"}])
        assert visible == []
