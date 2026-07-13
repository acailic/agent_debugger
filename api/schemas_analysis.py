"""Analysis domain schemas: workflow, safety, redundancy, causal, drift, baseline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# Workflow graph inspector schemas
# ------------------------------------------------------------------


class WorkflowNodeSchema(BaseModel):
    """Schema for a single node in the workflow graph."""

    id: str
    event_id: str
    node_type: str  # "decision", "tool_call", "llm_request", "error", "checkpoint"
    label: str
    status: str  # "success", "failure", "pending"
    duration_ms: float | None = None
    token_count: int | None = None
    timestamp: datetime
    parent_id: str | None = None
    metadata: dict[str, Any] | None = None


class WorkflowEdgeSchema(BaseModel):
    """Schema for an edge in the workflow graph."""

    id: str
    source_id: str
    target_id: str
    edge_type: str  # "data_flow", "control_flow", "dependency"
    label: str | None = None


class WorkflowGraphSchema(BaseModel):
    """Schema for the complete workflow graph."""

    session_id: str
    nodes: list[WorkflowNodeSchema]
    edges: list[WorkflowEdgeSchema]
    metadata: dict[str, Any] | None = None


class WorkflowGraphResponse(BaseModel):
    """Response schema for workflow graph endpoint."""

    graph: WorkflowGraphSchema


# ------------------------------------------------------------------
# Safety Monitoring schemas
# ------------------------------------------------------------------


class SafetyScoreSchema(BaseModel):
    """Schema for a single safety score."""

    dimension: str
    score: float = Field(ge=0.0, le=1.0)
    is_safe: bool
    details: str
    step_index: int | None = None
    event_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SafetyAlertSchema(BaseModel):
    """Schema for a safety alert."""

    dimension: str
    severity: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    message: str
    step_index: int | None = None
    event_id: str | None = None
    mitigation_suggestion: str | None = None


class SessionSafetyReportSchema(BaseModel):
    """Schema for a comprehensive session safety report."""

    session_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    is_safe: bool
    per_dimension_scores: dict[str, float]
    per_step_scores: list[SafetyScoreSchema]
    alerts: list[SafetyAlertSchema]
    total_steps: int
    unsafe_steps: int
    high_risk_dimensions: list[str]


class SafetyAnalysisResponse(BaseModel):
    """Response schema for safety analysis endpoint."""

    session_id: str
    safety_report: SessionSafetyReportSchema


# ------------------------------------------------------------------
# Redundancy Analysis schemas
# ------------------------------------------------------------------


class RedundancyScoreSchema(BaseModel):
    """Schema for a single step's redundancy score."""

    step_id: str
    score: float = Field(ge=0.0, le=1.0)
    contribution: str = Field(description="Step contribution: essential, redundant, harmful, or unknown")
    reasoning: str


class RedundancySummarySchema(BaseModel):
    """Schema for session-level redundancy summary."""

    total_steps: int = Field(ge=0)
    essential_count: int = Field(ge=0)
    redundant_count: int = Field(ge=0)
    harmful_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    avg_score: float = Field(ge=0.0, le=1.0)
    redundancy_rate: float = Field(ge=0.0, le=1.0)


class RedundancyAnalysisResponse(BaseModel):
    """Response schema for redundancy analysis endpoint."""

    session_id: str
    scores: list[RedundancyScoreSchema]
    summary: RedundancySummarySchema


# ------------------------------------------------------------------
# Causal Analysis Schemas
# ------------------------------------------------------------------


class CausalNodeSchema(BaseModel):
    """Schema for a causal graph node."""

    id: str
    event_type: str
    timestamp: datetime
    name: str
    parent_id: str | None = None
    dependencies: list[str] = []
    is_failure: bool = False
    failure_type: str | None = None
    causal_depth: int = 0
    metadata: dict[str, Any] = {}


class CausalEdgeSchema(BaseModel):
    """Schema for a causal graph edge."""

    from_node: str
    to_node: str
    relation_type: str
    strength: float = 1.0
    evidence: str | None = None


class CausalGraphSchema(BaseModel):
    """Schema for a complete causal graph."""

    nodes: list[CausalNodeSchema] = []
    edges: list[CausalEdgeSchema] = []
    root_cause_candidates: list[str] = []
    statistics: dict[str, Any] = {}


class CriticalPathEvent(BaseModel):
    """Event in the critical path to failure."""

    sequence: int
    event_id: str
    event_type: str
    name: str
    is_failure: bool
    failure_type: str | None = None
    timestamp: str


class WeakPoint(BaseModel):
    """Identified weak point in causal chain."""

    event_id: str
    weakness_type: str
    description: str
    position: int


class CriticalPathAnalysis(BaseModel):
    """Critical path analysis for a failure."""

    failure_node_id: str
    root_cause_found: bool
    root_cause_id: str | None = None
    chain_length: int
    critical_events: list[CriticalPathEvent] = []
    weak_points: list[WeakPoint] = []
    total_duration_seconds: float = 0.0


class CausalAnalysisResponse(BaseModel):
    """Response schema for causal analysis endpoint."""

    session_id: str
    causal_graph: CausalGraphSchema
    critical_paths: dict[str, CriticalPathAnalysis] = {}
    root_causes: list[CausalNodeSchema] = []


# ------------------------------------------------------------------
# Agent baseline and drift schemas
# ------------------------------------------------------------------


class AgentBaselineSchema(BaseModel):
    """Response schema for agent baseline metrics."""

    agent_name: str
    session_count: int
    computed_at: datetime
    time_window_days: int
    avg_decision_confidence: float
    low_confidence_rate: float
    avg_tool_duration_ms: float
    error_rate: float
    avg_tokens_per_session: float
    avg_cost_per_session: float
    tool_loop_rate: float
    refusal_rate: float
    avg_session_replay_value: float
    multi_agent_metrics: dict[str, Any] | None = None
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_llm_calls_per_session: float = 0.0
    avg_tool_calls_per_session: float = 0.0
    avg_duration_seconds: float = 0.0


class DriftAlertSchema(BaseModel):
    """Schema for a single drift alert."""

    metric: str
    metric_label: str
    baseline_value: float
    current_value: float
    change_percent: float
    severity: str  # "warning", "critical"
    description: str
    likely_cause: str | None = None


class DriftResponseSchema(BaseModel):
    """Response schema for agent drift detection."""

    agent_name: str
    baseline_session_count: int
    recent_session_count: int
    baseline: AgentBaselineSchema
    current: AgentBaselineSchema
    alerts: list[DriftAlertSchema]
    message: str | None = None


# ------------------------------------------------------------------
# Similar failures schemas
# ------------------------------------------------------------------


class SimilarFailureSchema(BaseModel):
    """Schema for a similar failure session."""

    session_id: str
    agent_name: str
    framework: str
    started_at: datetime
    failure_type: str
    failure_mode: str
    root_cause: str
    similarity: float
    fix_note: str | None = None


class SimilarFailuresResponse(BaseModel):
    """Response schema for similar failures endpoint."""

    session_id: str
    failure_event_id: str
    similar_failures: list[SimilarFailureSchema]
    total: int


# ------------------------------------------------------------------
# Agent audit / trust schemas
# ------------------------------------------------------------------


class AuditClaimSchema(BaseModel):
    """A single agent claim (decision) with its verification status."""

    event_id: str
    event_type: str
    headline: str
    claim: str
    rationale: str
    confidence: float
    alternatives_considered: int
    evidence_refs: list[str]
    evidence_sources: list[str]
    verification_status: str  # verified | partially_verified | contradicted | unsupported | unverified | stale
    verification_basis: str
    contradicted: bool
    timestamp: str


class AuditSignalSchema(BaseModel):
    """A deterministic risk signal derived from the trace."""

    event_id: str
    type: str  # unsupported_claim | missing_evidence | contradiction | repeated_failed_strategy | plan_drift | ...
    severity: str  # high | medium | low
    message: str


class AuditFailureSchema(BaseModel):
    """A failure with its localized root-cause suspect."""

    event_id: str
    event_type: str
    headline: str
    mode: str
    symptom: str
    likely_cause: str
    likely_cause_event_id: str | None
    confidence: float
    supporting_event_ids: list[str]
    position: int


class AuditReviewPointSchema(BaseModel):
    """A point in the run a human reviewer should look at."""

    event_id: str
    priority: str  # high | medium | low
    reason: str


class TrustScoreSchema(BaseModel):
    """Explainable trust/reliability score for a session."""

    score: float = Field(ge=0.0, le=1.0)
    band: str  # low | medium | high
    components: dict[str, Any]
    explanation: str


class SessionAuditReportSchema(BaseModel):
    """Human-auditable session report answering the five operator questions."""

    session_id: str
    objective: str | None
    final_outcome: str
    questions: dict[str, Any]
    claims: list[AuditClaimSchema]
    signals: list[AuditSignalSchema]
    failures: list[AuditFailureSchema]
    critical_decisions: list[AuditClaimSchema]
    trust: TrustScoreSchema
    review_points: list[AuditReviewPointSchema]


class SessionAuditResponse(BaseModel):
    """Response schema for the session audit endpoint."""

    session_id: str
    audit: SessionAuditReportSchema


class DecisionJustificationSchema(BaseModel):
    """Per-decision justification: why / evidence / outcome / where-failed."""

    event_id: str
    headline: str
    what: dict[str, Any]
    why: dict[str, Any]
    evidence: dict[str, Any]
    outcome: dict[str, Any]
    where_it_failed: dict[str, Any]
    policy: dict[str, Any]


class DecisionJustificationResponse(BaseModel):
    """Response schema for the decision justification lookup endpoint."""

    session_id: str
    event_id: str
    justification: DecisionJustificationSchema


class EvidenceGraphNodeSchema(BaseModel):
    """A node in the evidence-provenance graph (claim or fact)."""

    event_id: str
    event_type: str
    role: str  # claim | tool_fact | user_fact | other
    label: str
    verification_status: str | None = None
    confidence: float | None = None
    is_failure: bool = False
    timestamp: str | None = None


class EvidenceGraphEdgeSchema(BaseModel):
    """An edge in the evidence-provenance graph."""

    source_id: str
    target_id: str
    edge_type: str  # evidence | causal
    source_class: str | None = None  # tool_backed | user_provided | other


class EvidenceGraphSchema(BaseModel):
    """Evidence-provenance graph: how each claim connects to its facts."""

    session_id: str
    nodes: list[EvidenceGraphNodeSchema]
    edges: list[EvidenceGraphEdgeSchema]
    stats: dict[str, Any]


class EvidenceGraphResponse(BaseModel):
    """Response schema for the evidence-graph endpoint."""

    session_id: str
    graph: EvidenceGraphSchema
