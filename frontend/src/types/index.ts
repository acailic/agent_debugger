export type EventType =
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
  outcome?: string
  risk_level?: string
  rationale?: string
  blocked_action?: string | null
  reason?: string
  safe_alternative?: string | null
  severity?: string
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

export interface ReplayState {
  isPlaying: boolean
  currentIndex: number
  speed: number
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

export interface TraceAnalysis {
  event_rankings: TraceAnalysisRanking[]
  failure_clusters: TraceAnalysisCluster[]
  representative_failure_ids: string[]
  high_replay_value_ids: string[]
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
  mode: 'full' | 'focus' | 'failure'
  focus_event_id: string | null
  start_index: number
  events: TraceEvent[]
  checkpoints: Checkpoint[]
  nearest_checkpoint: Checkpoint | null
  breakpoints: TraceEvent[]
  failure_event_ids: string[]
}

export interface TraceSearchResponse {
  query: string
  session_id: string | null
  event_type: EventType | null
  total: number
  results: TraceEvent[]
}
