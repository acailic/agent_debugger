export type AppTab = 'trace' | 'inspect' | 'analytics'
export type ReplayMode = 'full' | 'focus' | 'failure' | 'highlights'
export type SessionSortMode = 'started_at' | 'replay_value'
export type SearchScope = 'current' | 'all'
export type ViewMode = 'sequential' | 'tree' | 'graph'

// Safety and risk level types from SDK
export type SafetyOutcome = 'pass' | 'fail' | 'warn' | 'block'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export type EventType =
  | 'trace_root'
  | 'agent_start'
  | 'agent_end'
  | 'tool_call'
  | 'tool_result'
  | 'llm_request'
  | 'llm_response'
  | 'decision'
  | 'error'
  | 'checkpoint'
  | 'safety_check'
  | 'refusal'
  | 'policy_violation'
  | 'prompt_policy'
  | 'agent_turn'
  | 'behavior_alert'
  | 'repair_attempt'

export interface TraceEvent {
  id: string
  session_id: string
  timestamp: string
  event_type: EventType
  parent_id: string | null
  name: string
  data: Record<string, unknown>
  metadata: Record<string, unknown>
  importance: number
  upstream_event_ids: string[]
  model?: string
  messages?: Array<{ role: string; content: string }>
  tools?: ToolDefinition[]
  settings?: Record<string, unknown>
  content?: string
  tool_calls?: ToolCall[]
  usage?: {
    input_tokens: number
    output_tokens: number
  }
  cost_usd?: number
  duration_ms?: number
  tool_name?: string
  arguments?: Record<string, unknown>
  result?: unknown
  error?: string | null
  reasoning?: string
  confidence?: number
  evidence?: Array<Record<string, unknown>>
  evidence_event_ids?: string[]
  alternatives?: Array<Record<string, unknown>>
  chosen_action?: string
  error_type?: string
  error_message?: string
  stack_trace?: string | null
  checkpoint_id?: string
  sequence?: number
  policy_name?: string
  outcome?: SafetyOutcome
  risk_level?: RiskLevel
  rationale?: string
  attempted_fix?: string
  validation_result?: string | null
  repair_outcome?: 'success' | 'failure' | 'partial'
  repair_sequence_id?: string | null
  repair_diff?: string | null
  blocked_action?: string | null
  reason?: string
  safe_alternative?: string | null
  severity?: RiskLevel
  violation_type?: string
  details?: Record<string, unknown>
  template_id?: string
  policy_parameters?: Record<string, unknown>
  speaker?: string
  state_summary?: string
  goal?: string
  agent_id?: string
  turn_index?: number
  alert_type?: string
  signal?: string
  related_event_ids?: string[]
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolDefinition {
  name: string
  description: string
  parameters: Record<string, unknown>
}

export interface Session {
  id: string
  agent_name: string
  framework: string
  started_at: string
  ended_at: string | null
  status: 'running' | 'completed' | 'error'
  total_tokens: number
  total_cost_usd: number
  tool_calls: number
  llm_calls: number
  errors: number
  config: Record<string, unknown>
  tags: string[]
  replay_value?: number
  retention_tier?: 'full' | 'summarized' | 'downsampled'
  failure_count?: number
  behavior_alert_count?: number
  representative_event_id?: string | null
  fix_note?: string | null
}

export interface Checkpoint {
  id: string
  session_id: string
  event_id: string
  sequence: number
  state: Record<string, unknown>
  memory: Record<string, unknown>
  timestamp: string
  importance: number
}

export interface TreeNode {
  event: TraceEvent
  children: TreeNode[]
}

export interface TraceAnalysisRanking {
  event_id: string
  event_type: EventType
  fingerprint: string
  severity: number
  novelty: number
  recurrence: number
  replay_value: number
  composite: number
}

export interface TraceAnalysisCluster {
  fingerprint: string
  count: number
  event_ids: string[]
  representative_event_id: string
  max_composite: number
}

export interface FailureCauseCandidate {
  event_id: string
  event_type: EventType
  headline: string
  score: number
  causal_depth: number
  relation: string
  relation_label: string
  explicit: boolean
  supporting_event_ids: string[]
  rationale: string
}

export interface FailureExplanation {
  failure_event_id: string
  failure_event_type: EventType
  failure_headline: string
  failure_mode: string
  symptom: string
  likely_cause: string
  likely_cause_event_id: string | null
  confidence: number
  supporting_event_ids: string[]
  next_inspection_event_id: string
  narrative: string
  candidates: FailureCauseCandidate[]
}

export interface Highlight {
  event_id: string
  event_type: EventType
  highlight_type: 'decision' | 'error' | 'refusal' | 'anomaly' | 'state_change'
  importance: number
  reason: string
  timestamp: string
  headline: string
}

export interface TraceAnalysis {
  event_rankings: TraceAnalysisRanking[]
  failure_clusters: TraceAnalysisCluster[]
  representative_failure_ids: string[]
  high_replay_value_ids: string[]
  failure_explanations: FailureExplanation[]
  checkpoint_rankings: Array<{
    checkpoint_id: string
    event_id: string
    sequence: number
    importance: number
    replay_value: number
    restore_value: number
    retention_tier: 'full' | 'summarized' | 'downsampled'
  }>
  session_replay_value: number
  retention_tier: 'full' | 'summarized' | 'downsampled'
  session_summary: {
    failure_count: number
    behavior_alert_count: number
    high_severity_count: number
    checkpoint_count: number
  }
  live_summary: LiveSummary
  behavior_alerts: Array<{
    alert_type: string
    severity: string
    signal: string
    event_id: string
  }>
  highlights: Highlight[]
}

export interface LiveSummary {
  event_count: number
  checkpoint_count: number
  latest: {
    decision_event_id: string | null
    tool_event_id: string | null
    safety_event_id: string | null
    turn_event_id: string | null
    policy_event_id: string | null
    checkpoint_id: string | null
  }
  rolling_summary: string
  recent_alerts: Array<{
    alert_type: string
    severity: 'medium' | 'high'
    signal: string
    event_id: string
    source: 'captured' | 'derived'
  }>
}

export interface TraceBundle {
  session: Session
  events: TraceEvent[]
  checkpoints: Checkpoint[]
  tree: TreeNode | null
  analysis: TraceAnalysis
}

export interface ReplayResponse {
  session_id: string
  mode: 'full' | 'focus' | 'failure' | 'highlights'
  focus_event_id: string | null
  start_index: number
  events: TraceEvent[]
  checkpoints: Checkpoint[]
  nearest_checkpoint: Checkpoint | null
  breakpoints: TraceEvent[]
  failure_event_ids: string[]
  collapsed_segments: CollapsedSegment[]
  highlight_indices: number[]
  stopped_at_breakpoint: boolean
  stopped_at_index: number | null
}

export interface TraceSearchResponse {
  query: string
  session_id: string | null
  event_type: EventType | null
  total: number
  results: TraceEvent[]
}

export interface AgentBaseline {
  agent_name: string
  session_count: number
  total_llm_calls: number
  total_tool_calls: number
  total_tokens: number
  total_cost_usd: number
  avg_llm_calls_per_session: number
  avg_tool_calls_per_session: number
  avg_tokens_per_session: number
  avg_cost_per_session: number
  error_rate: number
  avg_duration_seconds: number
}

export interface DriftAlert {
  metric: string
  metric_label: string
  baseline_value: number
  current_value: number
  change_percent: number
  severity: 'warning' | 'critical'
  description: string
}

export interface DriftResponse {
  agent_name: string
  baseline: AgentBaseline
  current: AgentBaseline
  alerts: DriftAlert[]
  message?: string
  baseline_session_count?: number
  recent_session_count?: number
}

export interface CollapsedSegment {
  start_index: number
  end_index: number
  event_count: number
  summary: string
  event_types: string[]
  total_duration_ms: number | null
}

export interface FailureCluster {
  id: string
  fingerprint: string
  session_count: number
  event_count: number
  avg_severity: number
  representative_session_id: string
  sample_symptom: string | null
}

export interface AnalyticsMetrics {
  sessions_created: number
  why_button_clicks: number
  failures_matched: number
  replay_highlights_used: number
  nl_queries_made: number
  searches_performed: number
}

export interface AnalyticsAdoptionRate {
  why_button: number
  failure_memory: number
  replay_highlights: number
}

export interface AnalyticsDerived {
  adoption_rate: AnalyticsAdoptionRate
  estimated_time_saved_minutes: number
}

export interface DailyBreakdown {
  date: string
  sessions: number
  clicks: number
}

export interface AnalyticsResponse {
  range: string
  period_start: string
  period_end: string
  metrics: AnalyticsMetrics
  derived: AnalyticsDerived
  daily_breakdown: DailyBreakdown[]
}

// Cost Dashboard types
export interface CostSummary {
  total_cost_usd: number
  session_count: number
  avg_cost_per_session: number
  by_framework: Array<{
    framework: string
    session_count: number
    total_cost_usd: number
    avg_cost_per_session: number
    total_tokens: number
  }>
  daily_cost: DailyCostItem[]
  period_start: string | null
  period_end: string | null
}

export interface DailyCostItem {
  date: string
  session_count: number
  total_cost_usd: number
  total_tokens: number
  avg_cost_usd: number
}

export interface TopSession {
  session_id: string
  agent_name: string
  framework: string
  total_cost_usd: number
  total_tokens: number
  llm_calls: number
  tool_calls: number
  started_at: string
  status: string
}

export interface SessionCost {
  session_id: string
  total_cost_usd: number
  total_tokens: number
  llm_calls: number
  tool_calls: number
}

// Failure Memory Search types
export interface SearchResult {
  session_id: string
  agent_name: string
  framework: string
  status: string
  total_cost_usd: number
  started_at: string
  ended_at: string | null
  errors: number
  fix_note: string | null
  similarity: number
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResult[]
}

export interface FixNoteResponse {
  session_id: string
  fix_note: string
}

// Similar Failures types
export interface SimilarFailure {
  session_id: string
  agent_name: string
  framework: string
  started_at: string
  failure_type: string
  failure_mode: string
  root_cause: string
  similarity: number
  fix_note: string | null
}

export interface SimilarFailuresResponse {
  session_id: string
  failure_event_id: string
  similar_failures: SimilarFailure[]
  total: number
}

// Comparison types
export interface PolicyShift {
  shift_magnitude: number
  from_template: string | null
  to_template: string | null
  turn_index: number
  rationale: string
}

export interface PolicyAnalysis {
  shift_count: number
  avg_shift_magnitude: number
  shifts: PolicyShift[]
}

export interface EscalationSignal {
  signal_type: string
  magnitude: number
  description: string
  turn_index: number | null
  event_id: string | null
}

export interface EscalationAnalysis {
  score: number
  signal_count: number
  dominant_signal_type: string | null
  signals: EscalationSignal[]
}

export interface SessionComparisonData {
  session: Session
  policy_analysis: PolicyAnalysis
  escalation_analysis: EscalationAnalysis
}

export interface ComparisonDeltas {
  turn_count: {
    primary: number
    secondary: number
    delta: number
  }
  policy_count: {
    primary: number
    secondary: number
    delta: number
  }
  speaker_count: {
    primary: number
    secondary: number
    delta: number
  }
  stance_shift_count: {
    primary: number
    secondary: number
    delta: number
  }
  escalation_count: {
    primary: number
    secondary: number
    delta: number
  }
  escalation_score: {
    primary: number
    secondary: number
    delta: number
  }
  grounded_decision_count: {
    primary: number
    secondary: number
    delta: number
  }
  grounding_rate: {
    primary: number
    secondary: number
    delta: number
  }
  avg_shift_magnitude: {
    primary: number
    secondary: number
    delta: number
  }
}

export interface ComparisonResponse {
  primary: SessionComparisonData
  secondary: SessionComparisonData
  comparison_deltas: ComparisonDeltas
}

// Alert Dashboard types
export type AlertStatus = 'active' | 'acknowledged' | 'resolved' | 'dismissed'

export interface AlertPolicy {
  id: string
  agent_name: string | null
  alert_type: string
  threshold_value: number
  severity_threshold: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AlertSummary {
  by_severity: Record<string, number>
  by_status: Record<string, number>
  by_type: Record<string, number>
  total: number
}

export interface AlertTrendingPoint {
  date: string
  count: number
}

// Extended alert with lifecycle management
export interface ManagedAlert {
  id: string
  session_id: string
  alert_type: string
  severity: number
  signal: string
  status: AlertStatus
  event_ids: string[]
  detection_source: string
  detection_config: Record<string, unknown>
  resolution_note: string | null
  acknowledged_at: string | null
  resolved_at: string | null
  dismissed_at: string | null
  created_at: string
}

/** Map numeric severity (0.0–1.0) to a display label. */
export function severityLabel(severity: number): RiskLevel {
  if (severity >= 0.8) return 'critical'
  if (severity >= 0.5) return 'high'
  if (severity >= 0.3) return 'medium'
  return 'low'
}

// Safety Monitoring types
export type SafetyDimension = 'goal_alignment' | 'constraint_adherence' | 'reasoning_coherence'

export interface SafetyScore {
  dimension: SafetyDimension
  score: number
  is_safe: boolean
  details: string
  step_index: number | null
  event_id: string | null
  confidence: number
}

export interface SafetyAlert {
  dimension: SafetyDimension
  severity: 'low' | 'medium' | 'high' | 'critical'
  score: number
  threshold: number
  message: string
  step_index: number | null
  event_id: string | null
  mitigation_suggestion: string | null
}

export interface SessionSafetyReport {
  session_id: string
  overall_score: number
  is_safe: boolean
  per_dimension_scores: Record<SafetyDimension, number>
  per_step_scores: SafetyScore[]
  alerts: SafetyAlert[]
  total_steps: number
  unsafe_steps: number
  high_risk_dimensions: SafetyDimension[]
}

export interface SafetyAnalysisResponse {
  session_id: string
  safety_report: SessionSafetyReport
}

// Redundancy Analysis types
export type StepContribution = 'essential' | 'redundant' | 'harmful' | 'unknown'

export interface RedundancyScore {
  step_id: string
  score: number
  contribution: StepContribution
  reasoning: string
}

export interface RedundancySummary {
  total_steps: number
  essential_count: number
  redundant_count: number
  harmful_count: number
  unknown_count: number
  avg_score: number
  redundancy_rate: number
}

export interface RedundancyAnalysisResponse {
  session_id: string
  scores: RedundancyScore[]
  summary: RedundancySummary
}

// Workflow Graph Inspector types
export interface WorkflowNode {
  id: string
  event_id: string
  node_type: 'decision' | 'tool_call' | 'llm_request' | 'error' | 'checkpoint'
  label: string
  status: 'success' | 'failure' | 'pending'
  duration_ms: number | null
  token_count: number | null
  timestamp: string
  parent_id: string | null
  metadata: Record<string, unknown> | null
}

export interface WorkflowEdge {
  id: string
  source_id: string
  target_id: string
  edge_type: 'data_flow' | 'control_flow' | 'dependency'
  label: string | null
}

export interface WorkflowGraph {
  session_id: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  metadata: Record<string, unknown> | null
}

export interface WorkflowGraphResponse {
  graph: WorkflowGraph
}

// Causal Analysis types
export type CausalRelationType =
  | 'direct'
  | 'temporal'
  | 'dependency'
  | 'failure_propagation'
  | 'state_derivation'

export interface CausalNode {
  id: string
  event_type: string
  timestamp: string
  name: string
  parent_id: string | null
  dependencies: string[]
  is_failure: boolean
  failure_type: string | null
  causal_depth: number
  metadata: Record<string, unknown>
}

export interface CausalEdge {
  from_node: string
  to_node: string
  relation_type: CausalRelationType
  strength: number
  evidence: string | null
}

export interface CausalGraphStats {
  total_nodes: number
  total_edges: number
  failure_count: number
  max_depth: number
}

export interface CausalGraph {
  nodes: CausalNode[]
  edges: CausalEdge[]
  root_cause_candidates: string[]
  statistics: CausalGraphStats
}

export interface CriticalPathEvent {
  sequence: number
  event_id: string
  event_type: string
  name: string
  is_failure: boolean
  failure_type: string | null
  timestamp: string
}

export interface WeakPoint {
  event_id: string
  weakness_type: string
  description: string
  position: number
}

export interface CriticalPathAnalysis {
  failure_node_id: string
  root_cause_found: boolean
  root_cause_id: string | null
  chain_length: number
  critical_events: CriticalPathEvent[]
  weak_points: WeakPoint[]
  total_duration_seconds: number
}

export interface CausalAnalysisResponse {
  session_id: string
  causal_graph: CausalGraph
  critical_paths: Record<string, CriticalPathAnalysis>
  root_causes: CausalNode[]
}

// ============================================================================
// Divergence Detection types (#184)
// ============================================================================

export type DivergenceType =
  | 'structural'
  | 'temporal'
  | 'behavioral'
  | 'state'
  | 'error'
  | 'performance'

export type DivergenceSeverity = 'critical' | 'high' | 'medium' | 'low'

export interface DivergencePoint {
  divergence_type: DivergenceType
  severity: DivergenceSeverity
  primary_event_id: string | null
  secondary_event_id: string | null
  description: string
  timestamp: string | null
  divergence_score: number
  metadata: Record<string, unknown>
}

export interface SessionComparison {
  primary_session_id: string
  secondary_session_id: string
  divergence_points: DivergencePoint[]
  overall_divergence_score: number
  structural_similarity: number
  temporal_similarity: number
  behavioral_similarity: number
  comparison_summary: Record<string, unknown>
}

export interface DivergenceAnalysisResponse {
  primary_session_id: string
  secondary_session_id: string
  divergence_analysis: SessionComparison
  primary_session: Session
  secondary_session: Session
}

export interface StructuralDivergenceResponse {
  primary_session_id: string
  secondary_session_id: string
  structural_comparison: {
    primary_depth: number
    secondary_depth: number
    primary_branching_factor: number
    secondary_branching_factor: number
    event_type_distribution_primary: Record<string, number>
    event_type_distribution_secondary: Record<string, number>
    structural_similarity: number
  }
}

export interface TemporalDivergenceResponse {
  primary_session_id: string
  secondary_session_id: string
  temporal_analysis: {
    primary_duration_seconds: number
    secondary_duration_seconds: number
    duration_difference_seconds: number
    temporal_divergence_score: number
    timing_differences: Array<{
      type: string
      time_difference_seconds: number
      description: string
    }>
  }
}

export interface BehavioralDivergenceResponse {
  primary_session_id: string
  secondary_session_id: string
  behavioral_analysis: {
    primary_decision_count: number
    secondary_decision_count: number
    primary_tool_call_count: number
    secondary_tool_call_count: number
    decision_divergences: Array<{
      index: number
      primary_confidence: number
      secondary_confidence: number
      confidence_difference: number
      description: string
    }>
    tool_divergences: Array<{
      tool_name: string
      tool_only_in_one: boolean
      description: string
    }>
    behavioral_divergence_score: number
  }
}

export interface BaselineDivergenceResponse {
  session_id: string
  baseline_session_id: string | null
  divergence_analysis: SessionComparison | null
  session: Session
  baseline_session: Session | null
  error?: string
}

export interface DivergenceSummaryResponse {
  session_id: string
  similar_sessions_count: number
  divergence_summary: {
    comparisons: Array<{
      session_id: string
      divergence_score: number
      total_divergences: number
      critical_divergences: number
      similarity_scores: {
        structural: number
        temporal: number
        behavioral: number
      }
    }>
    average_divergence_score: number
    most_similar_session: {
      session_id: string
      divergence_score: number
      total_divergences: number
      critical_divergences: number
      similarity_scores: {
        structural: number
        temporal: number
        behavioral: number
      }
    } | null
    least_similar_session: {
      session_id: string
      divergence_score: number
      total_divergences: number
      critical_divergences: number
      similarity_scores: {
        structural: number
        temporal: number
        behavioral: number
      }
    } | null
  } | null
  message?: string
}

// ============================================================================
// Violation Detection types (#194)
// ============================================================================

export type ViolationType =
  | 'outlier_behavior'
  | 'sparse_failure'
  | 'pattern_deviation'
  | 'temporal_anomaly'
  | 'resource_anomaly'
  | 'safety_violation'

export type ViolationSeverity = 'critical' | 'high' | 'medium' | 'low'

export interface ViolationEvidence {
  session_id: string
  event_id: string | null
  evidence_type: string
  description: string
  timestamp: string | null
  confidence: number
  metadata: Record<string, unknown>
}

export interface ViolationReport {
  violation_id: string
  violation_type: ViolationType
  severity: ViolationSeverity
  title: string
  description: string
  affected_sessions: string[]
  evidence: ViolationEvidence[]
  detected_at: string
  metadata: Record<string, unknown>
}

export interface SessionEmbedding {
  session_id: string
  embedding_vector: number[]
  feature_weights: Record<string, number>
  summary_hash: string
}

export interface TraceCluster {
  cluster_id: string
  session_ids: string[]
  centroid_embedding: SessionEmbedding | null
  cluster_characteristics: Record<string, unknown>
  outlier_session_ids: string[]
}

export interface SparseFailurePattern {
  pattern_id: string
  failure_type: string
  description: string
  required_sessions: number
  session_ids: string[]
  failure_points: Array<{
    session_id: string
    event_id: string | null
    timestamp: string | null
    error_type: string
    error_message: string
  }>
  confidence: number
}

export interface ViolationClusterResponse {
  clusters: TraceCluster[]
  global_outliers: string[]
  total_sessions_analyzed: number
  clustering_params: {
    similarity_threshold: number
    min_cluster_size: number
  }
}

export interface ViolationSearchResponse {
  violations: ViolationReport[]
  query: string
  total_sessions_searched: number
  total_violations_found: number
}

export interface SparseFailureResponse {
  sparse_failures: SparseFailurePattern[]
  total_sessions_analyzed: number
  total_patterns_found: number
  min_occurrences: number
}

export interface ViolationDashboardSummary {
  total_sessions_analyzed: number
  violation_summary: {
    by_type: Record<string, number>
    by_severity: Record<string, number>
    total_violations: number
  }
  cluster_summary: {
    total_clusters: number
    total_outliers: number
    average_cluster_size: number
  }
  sparse_failure_summary: {
    total_patterns: number
    most_common_failure_types: Array<{
      failure_type: string
      occurrence_count: number
    }>
  }
  time_range_days: number
}

export interface SimilarSession {
  session_id: string
  agent_name: string
  started_at: string | null
  similarity_score: number
}

export interface SimilarSessionsResponse {
  reference_session_id: string
  similar_sessions: SimilarSession[]
  total_compared: number
}

// ============================================================================
// Reasoning Editor types (#192)
// ============================================================================

export type EditOperation = 'modify' | 'insert' | 'delete' | 'replace'

export interface ReasoningEdit {
  edit_id: string
  operation: EditOperation
  event_id: string
  field_name: string
  position: number
  old_value: unknown
  new_value: unknown
  created_at: string
}

export interface ScenarioBranch {
  branch_id: string
  name: string
  description: string
  parent_event_id: string
  edits: ReasoningEdit[]
  original_session_id: string
  created_at: string
  replay_result: Record<string, unknown> | null
}

export interface HierarchicalReasoning {
  topics: Array<{
    title: string
    content: string[]
    subtopics: unknown[]
  }>
  raw: string
}

export interface ScenarioComparison {
  branches: Array<{
    id: string
    name: string
    description: string
    edit_count: number
    created_at: string
  }>
  differences: Array<{
    branch_a: string
    branch_b: string
    edit_difference: number
    shared_parent: boolean
  }>
  metrics: Record<string, unknown>
}

export interface ReasoningEditorResponse {
  event_id: string
  reasoning: string
  hierarchical_reasoning: HierarchicalReasoning
  available_edits: EditOperation[]
  applied_edits: ReasoningEdit[]
}

export interface ScenarioResponse {
  branch_id: string
  name: string
  description: string
  parent_event_id: string
  edits: ReasoningEdit[]
  original_session_id: string
  created_at: string
  replay_result: Record<string, unknown> | null
}

export interface ScenarioListResponse {
  session_id: string
  scenarios: ScenarioBranch[]
  total_scenarios: number
}

export interface EditResponse {
  edit_id: string
  operation: EditOperation
  event_id: string
  field_name: string
  old_value: unknown
  new_value: unknown
  position: number
  created_at: string
  success: boolean
  message?: string
}

// Agent Stepper types
export type BreakpointType =
  | 'event_type'
  | 'tool_name'
  | 'confidence_threshold'
  | 'safety_outcome'
  | 'custom_condition'
  | 'event_id'

export type StepAction =
  | 'step_into'
  | 'step_over'
  | 'step_out'
  | 'continue'
  | 'run_to'

export interface Breakpoint {
  breakpoint_id: string
  breakpoint_type: BreakpointType
  condition_value: unknown
  description: string
  enabled: boolean
  hit_count: number
  created_at: string
}

export interface StepperState {
  current_event_index: number
  current_event_id: string
  breakpoints: Breakpoint[]
  step_history: Array<{
    action: string
    event_index: number
    event_id: string
    timestamp: string
  }>
  paused: boolean
  completed: boolean
}

export interface StepResult {
  success: boolean
  current_event: TraceEvent | null
  next_event: TraceEvent | null
  breakpoint_hit: Breakpoint | null
  state: StepperState | null
  message: string
}

export interface BranchPoint {
  branch_id: string
  parent_event_id: string
  name: string
  description: string
  created_at: string
  replay_events_count: number
  branch_result: Record<string, unknown> | null
}

export interface AgentState {
  completed: boolean
  current_position: number
  total_events: number
  current_event?: {
    event_id: string
    event_type: string
    timestamp: string | null
    name: string
    data: Record<string, unknown>
    parent_id: string | null
    confidence?: number
    reasoning?: string
    tool_name?: string
  }
  events_count: number
  breakpoints_active: number
  paused: boolean
}

export interface StepperResponse {
  session_id: string
  step_result: StepResult
}

export interface StepperStateResponse {
  session_id: string
  agent_state: AgentState
  stepper_state: StepperState
}

export interface BreakpointResponse {
  session_id: string
  breakpoint: Breakpoint
  stepper_state: StepperState
}

export interface BreakpointsResponse {
  session_id: string
  breakpoints: Breakpoint[]
}

export interface BranchResponse {
  session_id: string
  branch: BranchPoint
}

export interface BranchesResponse {
  session_id: string
  branches: BranchPoint[]
}

export interface ExecutionContextResponse {
  session_id: string
  execution_context: {
    state: StepperState
    events_count: number
    branches: BranchPoint[]
    breakpoints: Breakpoint[]
  }
}

// ============================================================================
// Multi-agent Swimlane Debugger types (#193)
// ============================================================================

export type MessageFlowType =
  | 'request'
  | 'response'
  | 'notification'
  | 'synchronization'
  | 'broadcast'
  | 'delegation'

export type CoordinationIssueType =
  | 'deadlock'
  | 'race_condition'
  | 'communication_gap'
  | 'circular_dependency'
  | 'resource_conflict'
  | 'inconsistent_state'
  | 'timeout'

export type CoordinationSeverity = 'critical' | 'high' | 'medium' | 'low'

export type EmergentBehaviorType =
  | 'collaborative_problem_solving'
  | 'emergent_hierarchy'
  | 'swarm_intelligence'
  | 'adaptive_specialization'
  | 'consensus_building'
  | 'emergent_workflow'
  | 'self_organization'

export interface SwimlaneLane {
  agent_id: string
  agent_name: string
  events: string[] // Event IDs for serialization
  event_count: number
  start_time: string | null
  end_time: string | null
  duration_seconds: number
  color: string
  metadata: Record<string, unknown>
}

export interface MessageFlow {
  flow_id: string
  from_agent_id: string
  to_agent_id: string
  flow_type: MessageFlowType
  event_id: string
  timestamp: string | null
  description: string
  metadata: Record<string, unknown>
}

export interface CoordinationIssue {
  issue_id: string
  issue_type: CoordinationIssueType
  severity: CoordinationSeverity
  involved_agents: string[]
  event_ids: string[]
  description: string
  timestamp: string
  suggestion: string
  metadata: Record<string, unknown>
}

export interface EmergentBehavior {
  behavior_id: string
  behavior_type: EmergentBehaviorType
  confidence: number
  involved_agents: string[]
  event_ids: string[]
  description: string
  timestamp: string
  pattern_description: string
  metadata: Record<string, unknown>
}

export interface MultiAgentSession {
  session_id: string
  lanes: Record<string, SwimlaneLane>
  message_flows: MessageFlow[]
  start_time: string | null
  end_time: string | null
  duration_seconds: number
  agent_count: number
  total_event_count: number
  coordination_issues: CoordinationIssue[]
  emergent_behaviors: EmergentBehavior[]
  metadata: Record<string, unknown>
}

export interface SwimlaneVisualizationResponse {
  session_id: string
  swimlane_data: MultiAgentSession
}

export interface MessageFlowSummary {
  total_flows: number
  flow_types: Record<string, number>
  agent_pairs: Record<string, number>
  most_active_pair: {
    pair: string | null
    count: number
  } | null
}

export interface MessageFlowsResponse {
  session_id: string
  message_flows: MessageFlow[]
  flow_summary: MessageFlowSummary
}

export interface CoordinationSummary {
  total_issues: number
  by_severity: Record<string, number>
  by_type: Record<string, number>
  critical_issues: CoordinationIssue[]
}

export interface CoordinationAnalysisResponse {
  session_id: string
  coordination_issues: CoordinationIssue[]
  summary: CoordinationSummary
}

export interface EmergentBehaviorSummary {
  total_behaviors: number
  by_type: Record<string, number>
  high_confidence_behaviors: EmergentBehavior[]
  avg_confidence: number
}

export interface EmergentBehaviorsResponse {
  session_id: string
  emergent_behaviors: EmergentBehavior[]
  summary: EmergentBehaviorSummary
}

export interface MultiAgentAnalysisResponse {
  session_id: string
  session_info: {
    agent_name: string
    framework: string
    started_at: string
    status: string
  }
  swimlane_data: MultiAgentSession
  coordination_analysis: {
    issues: CoordinationIssue[]
    summary: CoordinationSummary
  }
  emergent_behavior_analysis: {
    behaviors: EmergentBehavior[]
    summary: EmergentBehaviorSummary
  }
}

// ============================================================================
// Agent Audit / Trust types — evidence-backed audit report per session
// ============================================================================

export type AuditVerificationStatus =
  | 'verified'
  | 'partially_verified'
  | 'contradicted'
  | 'unsupported'
  | 'unverified'
  | 'stale'

export type AuditSignalType =
  | 'unsupported_claim'
  | 'missing_evidence'
  | 'confidence_evidence_mismatch'
  | 'contradiction'
  | 'repeated_failed_strategy'
  | 'plan_drift'
  | 'policy_violation'
  | 'weak_evidence'
  | string

export type AuditSeverity = 'high' | 'medium' | 'low'
export type AuditTrustBand = 'low' | 'medium' | 'high'

export interface AuditClaim {
  event_id: string
  event_type: string
  headline: string
  claim: string
  rationale: string
  confidence: number
  alternatives_considered: number
  evidence_refs: string[]
  evidence_sources: string[]
  verification_status: AuditVerificationStatus
  verification_basis: string
  contradicted: boolean
  timestamp: string
}

export interface AuditSignal {
  event_id: string
  type: AuditSignalType
  severity: AuditSeverity
  message: string
}

export interface AuditFailure {
  event_id: string
  event_type: string
  headline: string
  mode: string
  symptom: string
  likely_cause: string
  likely_cause_event_id: string | null
  confidence: number
  supporting_event_ids: string[]
  position: number
}

export interface AuditReviewPoint {
  event_id: string
  priority: AuditSeverity
  reason: string
}

export interface TrustScore {
  score: number
  band: AuditTrustBand
  components: Record<string, number>
  explanation: string
}

export interface AuditWhatHappened {
  summary: string
  event_count: number
  tool_calls: number
  tool_results: number
  llm_calls: number
  decisions: number
  retries: number
  edits: number
}

export interface AuditWhyItem {
  event_id: string
  headline: string
  rationale: string
  confidence: number
  alternatives_considered: number
}

export interface AuditEvidence {
  tool_backed_facts: number
  user_input_facts: number
  retrieved_facts: number
  evidence_sources: string[]
  coverage_of_decisions: number
}

export interface AuditOutcomeFailure {
  event_id: string | null
  mode: string
  symptom: string
  likely_cause_event_id: string | null
}

export interface AuditOutcome {
  success_count: number
  failure_count: number
  failed_tool_results: number
  state_snapshots: number
  failures: AuditOutcomeFailure[]
}

export interface AuditTopSignal {
  type: string
  severity: AuditSeverity
  message: string
}

export interface AuditWhereItFailed {
  first_failure: string | null
  first_bad_decision: string | null
  failures: number
  top_signals: AuditTopSignal[]
}

export interface AuditQuestions {
  what_happened: AuditWhatHappened
  why: { decisions_with_rationale: AuditWhyItem[] }
  evidence: AuditEvidence
  outcome: AuditOutcome
  where_it_failed: AuditWhereItFailed
}

export interface SessionAuditReport {
  session_id: string
  objective: string | null
  final_outcome: string
  questions: AuditQuestions
  claims: AuditClaim[]
  signals: AuditSignal[]
  failures: AuditFailure[]
  critical_decisions: AuditClaim[]
  trust: TrustScore
  review_points: AuditReviewPoint[]
}

export interface SessionAuditResponse {
  session_id: string
  audit: SessionAuditReport
}

// ============================================================================
// Decision justification lookup — per-node why / evidence / outcome drill-down
// ============================================================================

export interface DecisionJustificationWhat {
  claim: string
  action: string
  event_type: string
  timestamp: string
}

export interface DecisionJustificationAlternative {
  action: string
  chosen: boolean
}

export interface DecisionJustificationWhy {
  rationale: string
  intent: string | null
  confidence: number
  alternatives: DecisionJustificationAlternative[]
}

export interface DecisionJustificationEvidence {
  refs: string[]
  resolved_refs: string[]
  sources: string[]
  verification_status: AuditVerificationStatus
  verification_basis: string
}

export interface DecisionJustificationOutcome {
  downstream_event_count: number
  downstream_successes: number
  downstream_failures: number
  produced: string[]
  state_changes: number
}

export interface DecisionJustificationSubtreeFailure {
  event_id: string | null
  mode: string
  symptom: string
  likely_cause_event_id: string | null
}

export interface DecisionJustificationWhereItFailed {
  contradicted: boolean
  subtree_failures: DecisionJustificationSubtreeFailure[]
  path_to_first_failure: string[]
}

export interface DecisionJustificationPolicy {
  violations_in_subtree: Array<{ event_id: string; type: string }>
  compliant: boolean
}

export interface DecisionJustification {
  event_id: string
  headline: string
  what: DecisionJustificationWhat
  why: DecisionJustificationWhy
  evidence: DecisionJustificationEvidence
  outcome: DecisionJustificationOutcome
  where_it_failed: DecisionJustificationWhereItFailed
  policy: DecisionJustificationPolicy
}

export interface DecisionJustificationResponse {
  session_id: string
  event_id: string
  justification: DecisionJustification
}

export interface EvidenceGraphNode {
  event_id: string
  event_type: string
  role: string // claim | tool_fact | user_fact | other
  label: string
  verification_status: string | null
  confidence: number | null
  is_failure: boolean
  timestamp: string | null
}

export interface EvidenceGraphEdge {
  source_id: string
  target_id: string
  edge_type: string // evidence | causal
  source_class: string | null // tool_backed | user_provided | other
}

export interface EvidenceGraphStats {
  node_count: number
  claim_count: number
  fact_count: number
  evidence_edges: number
  causal_edges: number
  unresolved_evidence_refs: number
  verification_counts: Record<string, number>
  evidence_coverage: number
}

export interface EvidenceGraph {
  session_id: string
  nodes: EvidenceGraphNode[]
  edges: EvidenceGraphEdge[]
  stats: EvidenceGraphStats
}

export interface EvidenceGraphResponse {
  session_id: string
  graph: EvidenceGraph
}

export interface PortfolioSessionRow {
  session_id: string
  agent_name: string | null
  started_at: string | null
  status: string | null
  trust_score: number
  band: string
  decision_count: number
  unsupported_count: number
  contradiction_count: number
  failure_count: number
  signal_count: number
  first_bad_decision: string | null
  objective: string | null
  final_outcome: string | null
}

export interface PortfolioAuditSummary {
  total_sessions: number
  trust: {
    mean_score: number
    band_distribution: Record<string, number>
  }
  means: Record<string, number>
  verification_totals: Record<string, number>
  totals: Record<string, number>
  signal_type_counts: Array<{ type: string; count: number }>
  failure_mode_counts: Array<{ mode: string; count: number }>
  sessions: PortfolioSessionRow[]
}

export interface PortfolioAuditResponse {
  summary: PortfolioAuditSummary
}
