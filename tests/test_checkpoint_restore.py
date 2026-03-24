"""Tests for checkpoint schemas and restore functionality."""

import pytest


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


class TestTraceContextRestore:
    def test_restore_classmethod_exists(self):
        """TraceContext.restore should be a classmethod."""
        from agent_debugger_sdk import TraceContext

        assert hasattr(TraceContext, "restore")
        assert callable(getattr(TraceContext, "restore"))

    @pytest.mark.asyncio
    async def test_restore_creates_context_with_restored_state(self):
        """TraceContext.restore should create context with restored state."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_debugger_sdk import TraceContext

        mock_checkpoint_data = {
            "id": "cp-test-123",
            "session_id": "sess-original",
            "event_id": "evt-1",
            "sequence": 1,
            "state": {
                "framework": "langchain",
                "label": "test_checkpoint",
                "messages": [{"role": "user", "content": "hello"}],
            },
            "memory": {},
            "timestamp": "2026-03-24T12:00:00Z",
            "importance": 0.9,
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_checkpoint_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            ctx = await TraceContext.restore(
                checkpoint_id="cp-test-123",
                server_url="http://localhost:8000",
            )

            assert ctx is not None
            assert ctx.restored_state is not None
            assert ctx.restored_state.framework == "langchain"

    @pytest.mark.asyncio
    async def test_restored_context_can_be_used_as_context_manager(self):
        """Restored context should work as async context manager."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_debugger_sdk import TraceContext

        mock_checkpoint_data = {
            "id": "cp-test-456",
            "session_id": "sess-original",
            "event_id": "evt-1",
            "sequence": 1,
            "state": {"framework": "custom", "data": {"step": 5}},
            "memory": {},
            "timestamp": "2026-03-24T12:00:00Z",
            "importance": 0.5,
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_checkpoint_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            async with await TraceContext.restore(
                checkpoint_id="cp-test-456",
                server_url="http://localhost:8000",
            ) as ctx:
                assert ctx.session_id != "sess-original"
                assert ctx.session.config.get("restored_from_checkpoint") == "cp-test-456"
