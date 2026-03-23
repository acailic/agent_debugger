"""Agent Debugger SDK - Core types and interfaces for tracing agent execution."""

__version__ = "0.1.2"

from agent_debugger_sdk.config import Config
from agent_debugger_sdk.config import get_config
from agent_debugger_sdk.config import init
from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.context import get_current_context
from agent_debugger_sdk.core.decorators import trace_agent
from agent_debugger_sdk.core.decorators import trace_llm
from agent_debugger_sdk.core.decorators import trace_tool
from agent_debugger_sdk.core.events import AgentTurnEvent
from agent_debugger_sdk.core.events import BehaviorAlertEvent
from agent_debugger_sdk.core.events import Checkpoint
from agent_debugger_sdk.core.events import DecisionEvent
from agent_debugger_sdk.core.events import ErrorEvent
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import LLMRequestEvent
from agent_debugger_sdk.core.events import LLMResponseEvent
from agent_debugger_sdk.core.events import PolicyViolationEvent
from agent_debugger_sdk.core.events import PromptPolicyEvent
from agent_debugger_sdk.core.events import RefusalEvent
from agent_debugger_sdk.core.events import SafetyCheckEvent
from agent_debugger_sdk.core.events import Session
from agent_debugger_sdk.core.events import ToolCallEvent
from agent_debugger_sdk.core.events import ToolResultEvent
from agent_debugger_sdk.core.events import TraceEvent
from agent_debugger_sdk.core.scorer import ImportanceScorer
from agent_debugger_sdk.core.scorer import get_importance_scorer

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
    # Context
    "TraceContext",
    "get_current_context",
    "configure_event_pipeline",
    "get_importance_scorer",
    # Decorators
    "trace_agent",
    "trace_tool",
    "trace_llm",
]
