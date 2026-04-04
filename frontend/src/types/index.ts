export type AppTab = 'trace' | 'inspect' | 'analytics'
export type ReplayMode = 'full' | 'focus' | 'failure' | 'highlights'
export type SessionSortMode = 'started_at' | 'replay_value'
export type SearchScope = 'current' | 'all'

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
