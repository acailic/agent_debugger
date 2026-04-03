export type ValidationChecker = (value: unknown) => boolean

/**
 * Typed error for validation failures
 * Thrown when response validation fails and no fallback is provided
 */
export class ValidationError extends Error {
  constructor(
    message: string,
    public endpoint: string,
    public data: unknown
  ) {
    super(message)
    this.name = 'ValidationError'
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number'
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function shapeValidator(required: Record<string, ValidationChecker>): ValidationChecker {
  return (value: unknown) => {
    if (!isPlainObject(value)) return false
    for (const [key, checker] of Object.entries(required)) {
      if (!(key in value)) return false
      if (!checker((value as Record<string, unknown>)[key])) return false
    }
    return true
  }
}

function arrayValidator(itemChecker: ValidationChecker): ValidationChecker {
  return (value: unknown) => {
    if (!isArray(value)) return false
    return value.every(itemChecker)
  }
}

function unionValidator(...checkers: ValidationChecker[]): ValidationChecker {
  return (value: unknown) => checkers.some(checker => checker(value))
}

// Validators for core types

const traceEventValidator: ValidationChecker = shapeValidator({
  id: isString,
  session_id: isString,
  timestamp: isString,
  event_type: isString,
  parent_id: unionValidator(isString, value => value === null),
  name: isString,
  data: isPlainObject,
  metadata: isPlainObject,
  importance: isNumber,
  upstream_event_ids: isArray,
})

const sessionValidator: ValidationChecker = shapeValidator({
  id: isString,
  agent_name: isString,
  framework: isString,
  started_at: isString,
  ended_at: unionValidator(isString, value => value === null),
  status: value => typeof value === 'string' && ['running', 'completed', 'error'].includes(value),
  total_tokens: isNumber,
  total_cost_usd: isNumber,
  tool_calls: isNumber,
  llm_calls: isNumber,
  errors: isNumber,
  config: isPlainObject,
  tags: isArray,
})

const agentBaselineValidator: ValidationChecker = shapeValidator({
  agent_name: isString,
  session_count: isNumber,
  total_llm_calls: isNumber,
  total_tool_calls: isNumber,
  total_tokens: isNumber,
  total_cost_usd: isNumber,
  avg_llm_calls_per_session: isNumber,
  avg_tool_calls_per_session: isNumber,
  avg_tokens_per_session: isNumber,
  avg_cost_per_session: isNumber,
  error_rate: isNumber,
  avg_duration_seconds: isNumber,
})

const driftAlertValidator: ValidationChecker = shapeValidator({
  metric: isString,
  metric_label: isString,
  baseline_value: isNumber,
  current_value: isNumber,
  change_percent: isNumber,
  severity: value => typeof value === 'string' && ['warning', 'critical'].includes(value),
  description: isString,
})

const driftResponseValidator: ValidationChecker = shapeValidator({
  agent_name: isString,
  baseline_session_count: isNumber,
  recent_session_count: isNumber,
  baseline: agentBaselineValidator,
  current: agentBaselineValidator,
  alerts: arrayValidator(driftAlertValidator),
})

const checkpointValidator: ValidationChecker = shapeValidator({
  id: isString,
  session_id: isString,
  event_id: isString,
  sequence: isNumber,
  state: isPlainObject,
  memory: isPlainObject,
  timestamp: isString,
  importance: isNumber,
})

const treeNodeValidator: ValidationChecker = (value: unknown): boolean => {
  if (!isPlainObject(value)) return false
  const event = (value as Record<string, unknown>).event
  const children = (value as Record<string, unknown>).children
  return traceEventValidator(event) && isArray(children)
}

const liveSummaryValidator: ValidationChecker = shapeValidator({
  event_count: isNumber,
  checkpoint_count: isNumber,
  latest: isPlainObject,
  rolling_summary: isString,
  recent_alerts: isArray,
})

const traceAnalysisValidator: ValidationChecker = shapeValidator({
  event_rankings: isArray,
  failure_clusters: isArray,
  representative_failure_ids: isArray,
  high_replay_value_ids: isArray,
  failure_explanations: isArray,
  checkpoint_rankings: isArray,
  session_replay_value: isNumber,
  retention_tier: isString,
  session_summary: isPlainObject,
  live_summary: liveSummaryValidator,
  behavior_alerts: isArray,
  highlights: isArray,
})

const traceBundleValidator: ValidationChecker = shapeValidator({
  session: sessionValidator,
  events: arrayValidator(traceEventValidator),
  checkpoints: arrayValidator(checkpointValidator),
  tree: unionValidator(treeNodeValidator, value => value === null),
  analysis: traceAnalysisValidator,
})

const replayResponseValidator: ValidationChecker = shapeValidator({
  session_id: isString,
  mode: isString,
  focus_event_id: unionValidator(isString, value => value === null),
  start_index: isNumber,
  events: arrayValidator(traceEventValidator),
  checkpoints: arrayValidator(checkpointValidator),
  nearest_checkpoint: unionValidator(checkpointValidator, value => value === null),
  breakpoints: arrayValidator(traceEventValidator),
  failure_event_ids: isArray,
  collapsed_segments: isArray,
  highlight_indices: isArray,
  stopped_at_breakpoint: isBoolean,
  stopped_at_index: unionValidator(isNumber, value => value === null),
})

export function validateResponse<T>(data: unknown, validator: ValidationChecker): T | null {
  if (validator(data)) {
    return data as T
  }
  return null
}

export function logValidationFailure(endpoint: string, reason: string, data: unknown): void {
  console.warn(`[API Validation] Endpoint: ${endpoint} — Reason: ${reason} — Data: ${JSON.stringify(data)}`)
}

// Export validators for use in client
export const validators = {
  Session: sessionValidator,
  TraceEvent: traceEventValidator,
  TraceBundle: traceBundleValidator,
  ReplayResponse: replayResponseValidator,
  AnalysisResult: traceAnalysisValidator,
  LiveSummary: liveSummaryValidator,
  AgentBaseline: agentBaselineValidator,
  DriftAlert: driftAlertValidator,
  DriftResponse: driftResponseValidator,
}
