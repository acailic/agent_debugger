"""SDK Core module - data models for agent tracing.

.. note::
    This barrel module re-exports all core types for convenience.
    Prefer importing from specific submodules:

    - ``agent_debugger_sdk.core.events``  for event types
    - ``agent_debugger_sdk.core.context``    for tracing context
    - ``agent_debugger_sdk.core.decorators`` for @trace_* decorators
    - ``agent_debugger_sdk.core.scorer``     for importance scoring

    The barrel import is provided for backward compatibility but will
    shrink in a future release.
"""

from agent_debugger_sdk.core.causal_tracer import (
    CausalEdge,
    CausalGraph,
    CausalNode,
    CausalRelationType,
)
from agent_debugger_sdk.core.conformal_scorer import (
    ConformalScore,
    CoverageLevel,
    PredictionRegion,
    compute_coverage_statistics,
    score_prediction_conformality,
)
from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.decorators import trace_agent, trace_llm, trace_tool
from agent_debugger_sdk.core.divergence_detector import (
    DivergencePoint,
    DivergenceSeverity,
    DivergenceType,
    SessionComparison,
    analyze_behavioral_divergence,
    analyze_temporal_divergence,
    compare_session_structures,
    detect_divergences,
)
from agent_debugger_sdk.core.error_attribution import (
    AttributionStrength,
    ErrorAttribution,
    FailureCategory,
    FailureChain,
    analyze_failure_patterns,
    attribute_errors,
    build_failure_chain,
    find_root_causes,
)
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
from agent_debugger_sdk.core.frame_tracer import (
    ExceptionInfo,
    FrameCaptureContext,
    FrameCost,
    FrameEvent,
    FrameLifetimeTrace,
    TokenUsage,
    build_frame_tree,
    capture_function_call,
    filter_frames_by_name,
    get_cost_breakdown,
    get_frame_by_id,
    get_frames_at_depth,
)
from agent_debugger_sdk.core.frame_tracer import (
    from_dict as frame_from_dict,
)
from agent_debugger_sdk.core.frame_tracer import (
    to_dict as frame_to_dict,
)
from agent_debugger_sdk.core.reasoning_editor import (
    EditableEvent,
    EditOperation,
    ReasoningEdit,
    ReasoningEditor,
    ScenarioBranch,
)
from agent_debugger_sdk.core.redundancy_scorer import (
    RedundancyScore,
    StepContribution,
    calculate_session_redundancy_summary,
    score_session,
)
from agent_debugger_sdk.core.safety_monitor import (
    SafetyAlert,
    SafetyDimension,
    SafetyScore,
    SessionSafetyReport,
    analyze_session_safety,
)
from agent_debugger_sdk.core.scorer import ImportanceScorer, get_importance_scorer
from agent_debugger_sdk.core.stepper import (
    AgentStepper,
    BranchPoint,
    Breakpoint,
    BreakpointType,
    StepAction,
    StepperState,
    StepResult,
)
from agent_debugger_sdk.core.swimlane import (
    CoordinationIssue,
    CoordinationSeverity,
    EmergentBehavior,
    EmergentBehaviorType,
    MessageFlow,
    MessageFlowType,
    MultiAgentSession,
    SwimlaneLane,
    analyze_multi_agent_session,
    detect_coordination_issues,
    detect_emergent_behaviors,
    get_message_flows,
    get_swimlane_data,
)
from agent_debugger_sdk.core.violation_detector import (
    CrossTraceSearch,
    SessionEmbedding,
    SparseFailureDetector,
    SparseFailurePattern,
    TraceCluster,
    TraceClusterer,
    ViolationEvidence,
    ViolationReport,
    ViolationSeverity,
    ViolationType,
    cluster_sessions,
    compute_session_embedding,
    detect_sparse_failures,
    search_violations_across_traces,
)

__all__ = [
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
    "TraceContext",
    "get_current_context",
    "get_importance_scorer",
    "trace_agent",
    "trace_tool",
    "trace_llm",
    "SafetyDimension",
    "SafetyScore",
    "SafetyAlert",
    "SessionSafetyReport",
    "analyze_session_safety",
    # Redundancy scoring
    "StepContribution",
    "RedundancyScore",
    "score_session",
    "calculate_session_redundancy_summary",
    # Causal analysis
    "CausalNode",
    "CausalEdge",
    "CausalGraph",
    "CausalRelationType",
    # Conformal prediction
    "CoverageLevel",
    "PredictionRegion",
    "ConformalScore",
    "score_prediction_conformality",
    "compute_coverage_statistics",
    # Error attribution
    "FailureCategory",
    "AttributionStrength",
    "ErrorAttribution",
    "FailureChain",
    "attribute_errors",
    "find_root_causes",
    "analyze_failure_patterns",
    "build_failure_chain",
    # Frame lifetime tracing
    "FrameEvent",
    "FrameLifetimeTrace",
    "FrameCaptureContext",
    "FrameCost",
    "TokenUsage",
    "ExceptionInfo",
    "build_frame_tree",
    "capture_function_call",
    "get_frame_by_id",
    "get_frames_at_depth",
    "filter_frames_by_name",
    "get_cost_breakdown",
    "frame_to_dict",
    "frame_from_dict",
    # Reasoning editing
    "EditOperation",
    "EditableEvent",
    "ReasoningEdit",
    "ReasoningEditor",
    "ScenarioBranch",
    # Divergence detection
    "DivergenceType",
    "DivergenceSeverity",
    "DivergencePoint",
    "SessionComparison",
    "detect_divergences",
    "compare_session_structures",
    "analyze_temporal_divergence",
    "analyze_behavioral_divergence",
    # Agent stepper
    "BreakpointType",
    "StepAction",
    "Breakpoint",
    "StepperState",
    "StepResult",
    "BranchPoint",
    "AgentStepper",
    # Multi-agent swimlane
    "MessageFlowType",
    "CoordinationIssue",
    "CoordinationSeverity",
    "EmergentBehaviorType",
    "SwimlaneLane",
    "MessageFlow",
    "EmergentBehavior",
    "MultiAgentSession",
    "analyze_multi_agent_session",
    "detect_coordination_issues",
    "detect_emergent_behaviors",
    "get_swimlane_data",
    "get_message_flows",
    # Violation detection
    "ViolationType",
    "ViolationSeverity",
    "ViolationEvidence",
    "ViolationReport",
    "TraceCluster",
    "SessionEmbedding",
    "SparseFailurePattern",
    "TraceClusterer",
    "CrossTraceSearch",
    "SparseFailureDetector",
    "cluster_sessions",
    "search_violations_across_traces",
    "detect_sparse_failures",
    "compute_session_embedding",
]
