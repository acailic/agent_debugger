"""Auto-patch adapters for LLM and agent frameworks."""

from agent_debugger_sdk.auto_patch.adapters.anthropic_adapter import AnthropicAdapter
from agent_debugger_sdk.auto_patch.adapters.autogen_adapter import AutoGenAdapter
from agent_debugger_sdk.auto_patch.adapters.crewai_adapter import CrewAIAdapter
from agent_debugger_sdk.auto_patch.adapters.langchain_adapter import LangChainAdapter
from agent_debugger_sdk.auto_patch.adapters.llamaindex_adapter import LlamaIndexAdapter
from agent_debugger_sdk.auto_patch.adapters.openai_adapter import OpenAIAdapter
from agent_debugger_sdk.auto_patch.adapters.pydanticai_adapter import PydanticAIAdapter
from agent_debugger_sdk.auto_patch.registry import AgentAdapterMixin

__all__ = [
    "AgentAdapterMixin",
    "AnthropicAdapter",
    "AutoGenAdapter",
    "CrewAIAdapter",
    "LangChainAdapter",
    "LlamaIndexAdapter",
    "OpenAIAdapter",
    "PydanticAIAdapter",
]
