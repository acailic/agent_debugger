"""Tests for checkpoint schemas and restore functionality."""


class TestBaseCheckpointState:
    def test_base_checkpoint_state_defaults(self):
        """BaseCheckpointState should auto-populate created_at."""
        from agent_debugger_sdk.checkpoints import BaseCheckpointState

        state = BaseCheckpointState(framework="custom")
        assert state.framework == "custom"
        assert state.label == ""
        assert state.created_at  # Should be auto-populated

    def test_base_checkpoint_state_with_label(self):
        """BaseCheckpointState should accept optional label."""
        from agent_debugger_sdk.checkpoints import BaseCheckpointState

        state = BaseCheckpointState(framework="langchain", label="after_tool")
        assert state.label == "after_tool"


class TestLangChainCheckpointState:
    def test_langchain_checkpoint_state_defaults(self):
        """LangChainCheckpointState should have framework preset."""
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        state = LangChainCheckpointState()
        assert state.framework == "langchain"
        assert state.messages == []
        assert state.intermediate_steps == []

    def test_langchain_checkpoint_state_with_messages(self):
        """LangChainCheckpointState should accept messages."""
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        messages = [{"role": "user", "content": "Hello"}]
        state = LangChainCheckpointState(
            label="greeting",
            messages=messages,
            run_name="test_agent",
        )
        assert state.messages == messages
        assert state.run_name == "test_agent"


class TestCustomCheckpointState:
    def test_custom_checkpoint_state_defaults(self):
        """CustomCheckpointState should have framework preset."""
        from agent_debugger_sdk.checkpoints import CustomCheckpointState

        state = CustomCheckpointState()
        assert state.framework == "custom"
        assert state.data == {}

    def test_custom_checkpoint_state_with_data(self):
        """CustomCheckpointState should accept arbitrary data."""
        from agent_debugger_sdk.checkpoints import CustomCheckpointState

        state = CustomCheckpointState(
            label="custom_state",
            data={"step": 5, "payload": {"x": 1}},
        )
        assert state.data["step"] == 5
        assert state.data["payload"]["x"] == 1


class TestSchemaRegistry:
    def test_schema_registry_contains_expected_frameworks(self):
        """SCHEMA_REGISTRY should contain langchain and custom."""
        from agent_debugger_sdk.checkpoints import SCHEMA_REGISTRY

        assert "langchain" in SCHEMA_REGISTRY
        assert "custom" in SCHEMA_REGISTRY

    def test_schema_registry_returns_correct_classes(self):
        """SCHEMA_REGISTRY should map to correct schema classes."""
        from agent_debugger_sdk.checkpoints import (
            SCHEMA_REGISTRY,
            CustomCheckpointState,
            LangChainCheckpointState,
        )

        assert SCHEMA_REGISTRY["langchain"] is LangChainCheckpointState
        assert SCHEMA_REGISTRY["custom"] is CustomCheckpointState
