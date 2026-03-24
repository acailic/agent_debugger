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


class TestCheckpointValidation:
    def test_validate_dict_with_langchain_framework(self):
        """Should validate dict and return LangChainCheckpointState."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {
            "framework": "langchain",
            "label": "test",
            "messages": [{"role": "user", "content": "hi"}],
        }
        result = validate_checkpoint_state(state_dict)
        assert isinstance(result, object)
        assert result.framework == "langchain"
        assert result.label == "test"

    def test_validate_dict_with_unknown_framework_returns_custom(self):
        """Unknown framework should fall back to CustomCheckpointState."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {
            "framework": "unknown_framework",
            "label": "test",
            "data": {"foo": "bar"},
        }
        result = validate_checkpoint_state(state_dict)
        # Should preserve the unknown framework string
        assert result.framework == "unknown_framework"

    def test_validate_dict_without_framework_defaults_to_custom(self):
        """Missing framework should default to custom."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {"data": {"step": 1}}
        result = validate_checkpoint_state(state_dict)
        assert result.framework == "custom"

    def test_validate_dataclass_passthrough(self):
        """Already-typed state should pass through unchanged."""
        from agent_debugger_sdk.checkpoints import (
            LangChainCheckpointState,
            validate_checkpoint_state,
        )

        state = LangChainCheckpointState(label="test")
        result = validate_checkpoint_state(state)
        assert result is state

    def test_validate_dict_with_extra_fields_on_known_framework(self):
        """Extra fields on known framework should be stored in metadata."""
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state

        state_dict = {
            "framework": "langchain",
            "label": "test",
            "custom_field": "extra_value",
        }
        result = validate_checkpoint_state(state_dict)
        assert result.framework == "langchain"
        assert result.metadata.get("_extra") == {"custom_field": "extra_value"}

    def test_serialize_state_to_dict(self):
        """Should serialize dataclass to dict with extra fields preserved."""
        from agent_debugger_sdk.checkpoints import (
            LangChainCheckpointState,
            serialize_checkpoint_state,
        )

        state = LangChainCheckpointState(
            label="test",
            messages=[{"role": "user", "content": "hi"}],
        )
        result = serialize_checkpoint_state(state)
        assert result["framework"] == "langchain"
        assert result["label"] == "test"
        assert result["messages"] == [{"role": "user", "content": "hi"}]
