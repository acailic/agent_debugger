"""Agent Debugger SDK - Core types and interfaces for tracing agent execution."""

__version__ = "0.1.4"

from agent_debugger_sdk.checkpoints import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
)
from agent_debugger_sdk.config import Config, get_config, init
from agent_debugger_sdk.core.context import TraceContext, configure_event_pipeline, get_current_context
from agent_debugger_sdk.core.decorators import trace_agent, trace_llm, trace_tool
from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
    Session,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from agent_debugger_sdk.core.scorer import ImportanceScorer, get_importance_scorer
from agent_debugger_sdk.pricing import ModelPricing, calculate_cost, get_pricing

__all__ = [
    # SDK Configuration
    "init",
    "get_config",
    "Config",
    # Events
    "EventType",
    "TraceEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "LLMRequestEvent",
    "LLMResponseEvent",
    "DecisionEvent",
    "ErrorEvent",
    "SafetyCheckEvent",
    "RefusalEvent",
    "PolicyViolationEvent",
    "PromptPolicyEvent",
    "AgentTurnEvent",
    "BehaviorAlertEvent",
    "Session",
    "Checkpoint",
    "ImportanceScorer",
    # Checkpoints
    "BaseCheckpointState",
    "CustomCheckpointState",
    "LangChainCheckpointState",
    # Context
    "TraceContext",
    "get_current_context",
    "configure_event_pipeline",
    "get_importance_scorer",
    # Decorators
    "trace_agent",
    "trace_tool",
    "trace_llm",
    # Pricing
    "ModelPricing",
    "get_pricing",
    "calculate_cost",
]
