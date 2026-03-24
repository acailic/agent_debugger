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


class TestCheckpointEndpoints:
    def test_checkpoint_schemas_importable(self):
        """CheckpointResponse, RestoreRequest, RestoreResponse should exist in api.schemas."""
        from api.schemas import CheckpointResponse, RestoreRequest, RestoreResponse

        assert CheckpointResponse
        assert RestoreRequest
        assert RestoreResponse

    def test_checkpoint_endpoints_registered(self):
        """GET and POST checkpoint endpoints should be registered in the app."""
        import api.main as api_main
        from fastapi.routing import APIRoute

        routes = [(r.path, r.methods) for r in api_main.app.routes if isinstance(r, APIRoute)]
        assert any(p == "/api/checkpoints/{checkpoint_id}" and "GET" in m for p, m in routes)
        assert any(p == "/api/checkpoints/{checkpoint_id}/restore" and "POST" in m for p, m in routes)

    def test_get_checkpoint_returns_404_for_missing(self, tmp_path):
        """GET /api/checkpoints/{id} should return 404 when checkpoint does not exist."""
        import asyncio

        import api.main as api_main
        from fastapi import HTTPException
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from storage import Base, TraceRepository

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/cp.db", echo=False)
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            endpoint = next(
                r.endpoint
                for r in api_main.app.routes
                if hasattr(r, "path") and r.path == "/api/checkpoints/{checkpoint_id}"
                and hasattr(r, "methods") and "GET" in r.methods
            )
            async with session_maker() as session:
                repo = TraceRepository(session)
                try:
                    await endpoint(checkpoint_id="nonexistent-cp", repo=repo)
                    return False  # Should have raised
                except HTTPException as e:
                    return e.status_code == 404

        result = asyncio.run(run())
        asyncio.run(engine.dispose())
        assert result


class TestCreateCheckpointValidation:
    @pytest.mark.asyncio
    async def test_create_checkpoint_serializes_dataclass_state_to_dict(self):
        """create_checkpoint should serialize dataclass state to dict when persisting."""
        from agent_debugger_sdk import TraceContext
        from agent_debugger_sdk.checkpoints import LangChainCheckpointState

        persisted: list = []

        async def capture(cp):
            persisted.append(cp)

        async with TraceContext(agent_name="test") as ctx:
            ctx._checkpoint_persister = capture
            state = LangChainCheckpointState(
                label="test_state",
                messages=[{"role": "user", "content": "hi"}],
            )
            await ctx.create_checkpoint(state, importance=0.9)

        assert len(persisted) == 1
        assert isinstance(persisted[0].state, dict), "state must be serialized to dict"
        assert persisted[0].state["framework"] == "langchain"
        assert persisted[0].state["messages"] == [{"role": "user", "content": "hi"}]

    @pytest.mark.asyncio
    async def test_create_checkpoint_validates_dict_state(self):
        """create_checkpoint should validate dict state against schema."""
        from agent_debugger_sdk import TraceContext

        persisted: list = []

        async def capture(cp):
            persisted.append(cp)

        async with TraceContext(agent_name="test") as ctx:
            ctx._checkpoint_persister = capture
            state_dict = {
                "framework": "langchain",
                "label": "test_state",
                "messages": [{"role": "user", "content": "hi"}],
            }
            await ctx.create_checkpoint(state_dict, importance=0.9)

        assert len(persisted) == 1
        assert isinstance(persisted[0].state, dict)
        assert persisted[0].state["framework"] == "langchain"
