import type {
  AgentBaseline,
  AlertPolicy,
  AlertStatus,
  AlertSummary,
  AlertTrendingPoint,
  AnalyticsResponse,
  BaselineDivergenceResponse,
  BehavioralDivergenceResponse,
  BreakpointResponse,
  BreakpointsResponse,
  BreakpointType,
  BranchResponse,
  BranchesResponse,
  CausalAnalysisResponse,
  ComparisonResponse,
  DecisionJustificationResponse,
  CoordinationAnalysisResponse,
  EvidenceGraphResponse,
  PortfolioAuditResponse,
  CostSummary,
  DivergenceAnalysisResponse,
  DivergenceSummaryResponse,
  DriftResponse,
  EditOperation,
  EmergentBehaviorsResponse,
  ExecutionContextResponse,
  FixNoteResponse,
  HierarchicalReasoning,
  LiveSummary,
  ManagedAlert,
  MessageFlowsResponse,
  MultiAgentAnalysisResponse,
  ReasoningEdit,
  RedundancyAnalysisResponse,
  ReplayResponse,
  SafetyAnalysisResponse,
  SessionAuditResponse,
  ScenarioBranch,
  ScenarioComparison,
  SearchResponse,
  Session,
  SessionCost,
  SessionEmbedding,
  SimilarFailuresResponse,
  SimilarSession,
  SparseFailurePattern,
  StepAction,
  StepperResponse,
  StepperState,
  StepperStateResponse,
  StructuralDivergenceResponse,
  SwimlaneVisualizationResponse,
  TemporalDivergenceResponse,
  TopSession,
  TraceAnalysis,
  TraceBundle,
  TraceCluster,
  TraceEvent,
  TraceSearchResponse,
  ViolationReport,
  WorkflowGraphResponse,
} from '../types'
import { validateResponse, logValidationFailure, validators, ValidationError } from './validation'
import { logger } from '../utils/logger'

const API_BASE = '/api'

// Request deduplication: track in-flight requests to avoid duplicate fetches
const MAX_PENDING_REQUESTS = 100
const pendingRequests = new Map<string, Promise<Response>>()

/**
 * Sleep utility for retry backoff
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Check if error is retryable (transient network errors or 5xx)
 */
function isRetryableError(response: Response, error: unknown): boolean {
  // Retry on network errors
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return true
  }
  // Retry on 5xx server errors
  if (response.status >= 500 && response.status < 600) {
    return true
  }
  // Retry on 429 Too Many Requests
  if (response.status === 429) {
    return true
  }
  return false
}

/**
 * Fetch with exponential backoff retry
 */
async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  maxRetries = 3
): Promise<Response> {
  let lastError: Error | null = null

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, options)

      // If successful or non-retryable error, return immediately
      if (response.ok || !isRetryableError(response, null)) {
        return response
      }

      // For retryable errors, wait and retry
      if (attempt < maxRetries) {
        const backoffMs = Math.min(1000 * Math.pow(2, attempt), 10000) // Max 10s
        await sleep(backoffMs)
        lastError = new Error(`HTTP ${response.status}: ${response.statusText}`)
        continue
      }

      return response
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error))

      // Don't retry non-fetch errors
      if (!(error instanceof TypeError) || !error.message.includes('fetch')) {
        throw error
      }

      // Retry with backoff
      if (attempt < maxRetries) {
        const backoffMs = Math.min(1000 * Math.pow(2, attempt), 10000)
        await sleep(backoffMs)
        continue
      }

      throw lastError
    }
  }

  throw lastError ?? new Error('Max retries exceeded')
}

async function fetchWithDeduplication(url: string): Promise<Response> {
  // Check if there's already a pending request for this URL
  let requestPromise = pendingRequests.get(url)
  if (!requestPromise) {
    // Evict oldest entries if limit exceeded
    if (pendingRequests.size >= MAX_PENDING_REQUESTS) {
      const firstKey = pendingRequests.keys().next().value
      if (firstKey) {
        pendingRequests.delete(firstKey)
      }
    }
    // Create new request with retry logic and store the promise
    requestPromise = fetchWithRetry(url)
    pendingRequests.set(url, requestPromise)

    // Clean up after request completes (whether success or failure)
    requestPromise.finally(() => {
      pendingRequests.delete(url)
    })
  }

  // Clone the shared response so concurrent callers can read the body safely.
  return (await requestPromise).clone()
}

interface ValidationConfig {
  validator?: (value: unknown) => boolean
  endpoint: string
  fallback?: unknown
}

async function fetchJSON<T>(url: string, config?: ValidationConfig): Promise<T> {
  const response = await fetchWithDeduplication(url)
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()

  // Apply runtime validation if validator provided
  if (config?.validator) {
    const validated = validateResponse<T>(data, config.validator)
    if (validated === null) {
      logValidationFailure(config.endpoint, 'Response shape validation failed', data)
      // If fallback is provided, return it with a console warning
      if (config.fallback !== undefined) {
        logger.warn('[API Validation] Using fallback data for endpoint: ${config.endpoint}', {component: 'client'})
        return config.fallback as T
      }
      // Otherwise, throw a typed error instead of returning unvalidated data
      throw new ValidationError(
        `Response validation failed for endpoint: ${config.endpoint}`,
        config.endpoint,
        data
      )
    }
    return validated
  }

  return data as T
}

export async function getSessions(params: { sortBy?: 'started_at' | 'replay_value' } = {}) {
  const search = new URLSearchParams()
  if (params.sortBy) search.set('sort_by', params.sortBy)
  const suffix = search.toString() ? `?${search.toString()}` : ''
  const url = `${API_BASE}/sessions${suffix}`

  return fetchJSON<{ sessions: Session[]; total: number; limit: number; offset: number }>(url, {
    validator: (value: unknown) => {
      if (typeof value !== 'object' || value === null) return false
      const v = value as Record<string, unknown>
      return (
        'sessions' in v &&
        Array.isArray(v.sessions) &&
        v.sessions.every((s: unknown) => validators.Session(s)) &&
        'total' in v &&
        typeof v.total === 'number' &&
        'limit' in v &&
        typeof v.limit === 'number' &&
        'offset' in v &&
        typeof v.offset === 'number'
      )
    },
    endpoint: '/sessions',
  })
}

export async function getTraceBundle(sessionId: string) {
  return fetchJSON<TraceBundle>(
    `${API_BASE}/sessions/${sessionId}/trace`,
    {
      validator: validators.TraceBundle,
      endpoint: `/sessions/${sessionId}/trace`,
    }
  )
}

export async function getReplay(
  sessionId: string,
  params: {
    mode?: 'full' | 'focus' | 'failure' | 'highlights'
    focusEventId?: string | null
    breakpointEventTypes?: string[]
    breakpointToolNames?: string[]
    breakpointConfidenceBelow?: number | null
    breakpointSafetyOutcomes?: string[]
    stopAtBreakpoint?: boolean
    collapseThreshold?: number
  } = {},
) {
  const search = new URLSearchParams()
  if (params.mode) search.set('mode', params.mode)
  if (params.focusEventId) search.set('focus_event_id', params.focusEventId)
  if (params.breakpointEventTypes?.length) search.set('breakpoint_event_types', params.breakpointEventTypes.join(','))
  if (params.breakpointToolNames?.length) search.set('breakpoint_tool_names', params.breakpointToolNames.join(','))
  if (params.breakpointConfidenceBelow !== null && params.breakpointConfidenceBelow !== undefined) {
    search.set('breakpoint_confidence_below', String(params.breakpointConfidenceBelow))
  }
  if (params.breakpointSafetyOutcomes?.length) {
    search.set('breakpoint_safety_outcomes', params.breakpointSafetyOutcomes.join(','))
  }
  if (params.stopAtBreakpoint !== undefined) {
    search.set('stop_at_breakpoint', String(params.stopAtBreakpoint))
  }
  if (params.collapseThreshold != null) search.set('collapse_threshold', String(params.collapseThreshold))
  return fetchJSON<ReplayResponse>(
    `${API_BASE}/sessions/${sessionId}/replay?${search.toString()}`,
    {
      validator: validators.ReplayResponse,
      endpoint: `/sessions/${sessionId}/replay`,
    }
  )
}

export async function getAnalysis(sessionId: string) {
  return fetchJSON<{ session_id: string; analysis: TraceAnalysis }>(
    `${API_BASE}/sessions/${sessionId}/analysis`,
    {
      validator: (value: unknown) =>
        typeof value === 'object' &&
        value !== null &&
        'session_id' in value &&
        'analysis' in value &&
        validators.AnalysisResult((value as Record<string, unknown>).analysis),
      endpoint: `/sessions/${sessionId}/analysis`,
    }
  )
}

export async function getSafetyAnalysis(sessionId: string) {
  return fetchJSON<SafetyAnalysisResponse>(
    `${API_BASE}/sessions/${sessionId}/safety`,
    {
      validator: (value: unknown) =>
        typeof value === 'object' &&
        value !== null &&
        'session_id' in value &&
        'safety_report' in value,
      endpoint: `/sessions/${sessionId}/safety`,
    }
  )
}

export function createEventSource(sessionId: string): EventSource {
  return new EventSource(`${API_BASE}/sessions/${sessionId}/stream`)
}

export async function getLiveSummary(sessionId: string) {
  return fetchJSON<{ session_id: string; live_summary: LiveSummary }>(
    `${API_BASE}/sessions/${sessionId}/live`,
    {
      validator: (value: unknown) =>
        typeof value === 'object' &&
        value !== null &&
        'session_id' in value &&
        'live_summary' in value &&
        validators.LiveSummary((value as Record<string, unknown>).live_summary),
      endpoint: `/sessions/${sessionId}/live`,
    }
  )
}

export async function searchTraces(params: {
  query: string
  sessionId?: string | null
  eventType?: string | null
  limit?: number
}) {
  const search = new URLSearchParams()
  search.set('query', params.query)
  if (params.sessionId) search.set('session_id', params.sessionId)
  if (params.eventType) search.set('event_type', params.eventType)
  if (params.limit) search.set('limit', String(params.limit))
  return fetchJSON<TraceSearchResponse>(
    `${API_BASE}/traces/search?${search.toString()}`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'query' in v &&
          typeof v.query === 'string' &&
          'total' in v &&
          typeof v.total === 'number' &&
          'results' in v &&
          Array.isArray(v.results) &&
          v.results.every((r: unknown) => validators.TraceEvent(r))
        )
      },
      endpoint: '/traces/search',
    }
  )
}

export async function getAgentBaseline(agentName: string): Promise<AgentBaseline> {
  return fetchJSON<AgentBaseline>(`${API_BASE}/agents/${encodeURIComponent(agentName)}/baseline`, {
    validator: validators.AgentBaseline,
    endpoint: `/agents/${encodeURIComponent(agentName)}/baseline`,
  })
}

export async function getAgentDrift(agentName: string): Promise<DriftResponse> {
  return fetchJSON<DriftResponse>(`${API_BASE}/agents/${encodeURIComponent(agentName)}/drift`, {
    validator: validators.DriftResponse,
    endpoint: `/agents/${encodeURIComponent(agentName)}/drift`,
  })
}

export async function getAnalytics(range: string): Promise<AnalyticsResponse> {
  return fetchJSON<AnalyticsResponse>(`${API_BASE}/analytics?range=${encodeURIComponent(range)}`)
}

// Cost Dashboard API
export async function getCostSummary(range?: string): Promise<CostSummary> {
  const params = range ? `?range=${encodeURIComponent(range)}` : ''
  return fetchJSON<CostSummary>(`${API_BASE}/cost/summary${params}`)
}

export async function getTopSessions(range?: string, limit: number = 10): Promise<TopSession[]> {
  const params = new URLSearchParams()
  if (range) params.set('range', range)
  params.set('limit', String(limit))
  return fetchJSON<TopSession[]>(`${API_BASE}/cost/top-sessions?${params}`)
}

export async function getSessionCost(sessionId: string) {
  return fetchJSON<SessionCost>(`${API_BASE}/cost/sessions/${sessionId}`)
}

// Failure Memory Search API
export async function searchSessions(params: {
  q: string
  status?: string | null
  limit?: number
}) {
  const search = new URLSearchParams()
  search.set('q', params.q)
  if (params.status) search.set('status', params.status)
  if (params.limit) search.set('limit', String(params.limit))
  return fetchJSON<SearchResponse>(`${API_BASE}/search?${search.toString()}`)
}

export async function addFixNote(sessionId: string, note: string) {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/fix-note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<FixNoteResponse>
}

export async function getSimilarFailures(params: {
  sessionId: string
  failureEventId: string
  limit?: number
}) {
  const search = new URLSearchParams()
  search.set('failure_event_id', params.failureEventId)
  if (params.limit) search.set('limit', String(params.limit))
  return fetchJSON<SimilarFailuresResponse>(
    `${API_BASE}/sessions/${params.sessionId}/similar-failures?${search.toString()}`
  )
}

// Alert Dashboard API functions
export async function fetchAlerts(filters?: Record<string, string>) {
  const search = new URLSearchParams()
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value) search.set(key, value)
    })
  }
  const queryString = search.toString() ? `?${search.toString()}` : ''
  return fetchJSON<{ alerts: ManagedAlert[]; total: number }>(
    `${API_BASE}/alerts${queryString}`
  )
}

export async function updateAlertStatus(
  alertId: string,
  status: AlertStatus,
  note?: string
) {
  const response = await fetch(`${API_BASE}/alerts/${alertId}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, note }),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<ManagedAlert>
}

export async function bulkUpdateAlertStatus(alertIds: string[], status: AlertStatus) {
  const response = await fetch(`${API_BASE}/alerts/bulk-status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alert_ids: alertIds, status }),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<{ updated: number; status: AlertStatus }>
}

export async function fetchAlertSummary() {
  return fetchJSON<AlertSummary>(`${API_BASE}/alerts/summary`)
}

export async function fetchAlertTrending(days: number = 7) {
  const data = await fetchJSON<{ trending: AlertTrendingPoint[]; days: number }>(
    `${API_BASE}/alerts/trending?days=${days}`
  )
  return data.trending
}

export async function fetchAlertPolicies(agentName?: string) {
  const params = agentName ? `?agent_name=${encodeURIComponent(agentName)}` : ''
  return fetchJSON<AlertPolicy[]>(`${API_BASE}/alert-policies${params}`)
}

export async function createAlertPolicy(policy: Partial<AlertPolicy>) {
  const response = await fetch(`${API_BASE}/alert-policies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<AlertPolicy>
}

export async function updateAlertPolicy(id: string, policy: Partial<AlertPolicy>) {
  const response = await fetch(`${API_BASE}/alert-policies/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<AlertPolicy>
}

export async function deleteAlertPolicy(id: string) {
  const response = await fetch(`${API_BASE}/alert-policies/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<{ deleted: boolean }>
}

// Comparison API
export async function getComparison(primaryId: string, secondaryId: string) {
  return fetchJSON<ComparisonResponse>(
    `${API_BASE}/compare/${primaryId}/${secondaryId}`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'primary' in v &&
          'secondary' in v &&
          'comparison_deltas' in v &&
          typeof v.primary === 'object' &&
          v.primary !== null &&
          typeof v.secondary === 'object' &&
          v.secondary !== null
        )
      },
      endpoint: '/compare/{primary_id}/{secondary_id}',
    }
  )
}

// Redundancy Analysis API
export async function getRedundancyAnalysis(sessionId: string): Promise<RedundancyAnalysisResponse> {
  return fetchJSON<RedundancyAnalysisResponse>(
    `${API_BASE}/sessions/${sessionId}/redundancy`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'session_id' in v &&
          'scores' in v &&
          'summary' in v &&
          Array.isArray(v.scores) &&
          typeof v.summary === 'object' &&
          v.summary !== null
        )
      },
      endpoint: '/sessions/{session_id}/redundancy',
    }
  )
}

// Causal Analysis API
export async function getCausalAnalysis(sessionId: string): Promise<CausalAnalysisResponse> {
  return fetchJSON<CausalAnalysisResponse>(
    `${API_BASE}/sessions/${sessionId}/causal`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'session_id' in v &&
          'causal_graph' in v &&
          'critical_paths' in v &&
          'root_causes' in v &&
          typeof v.causal_graph === 'object' &&
          v.causal_graph !== null
        )
      },
      endpoint: '/sessions/{session_id}/causal',
    }
  )
}

// Workflow Graph API
export async function getWorkflowGraph(sessionId: string): Promise<WorkflowGraphResponse> {
  return fetchJSON<WorkflowGraphResponse>(
    `${API_BASE}/sessions/${sessionId}/workflow-graph`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'graph' in v &&
          typeof v.graph === 'object' &&
          v.graph !== null &&
          'session_id' in v.graph &&
          'nodes' in v.graph &&
          'edges' in v.graph &&
          Array.isArray((v.graph as Record<string, unknown>).nodes) &&
          Array.isArray((v.graph as Record<string, unknown>).edges)
        )
      },
      endpoint: '/sessions/{session_id}/workflow-graph',
    }
  )
}

// ============================================================================
// Divergence Detection API (#184)
// ============================================================================

export async function getDivergenceAnalysis(
  primaryId: string,
  secondaryId: string
): Promise<DivergenceAnalysisResponse> {
  return fetchJSON<DivergenceAnalysisResponse>(
    `${API_BASE}/compare/${primaryId}/${secondaryId}/divergence`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'primary_session_id' in v &&
          'secondary_session_id' in v &&
          'divergence_analysis' in v &&
          typeof v.divergence_analysis === 'object' &&
          v.divergence_analysis !== null
        )
      },
      endpoint: '/compare/{primary_id}/{secondary_id}/divergence',
    }
  )
}

export async function getStructuralDivergence(
  primaryId: string,
  secondaryId: string
): Promise<StructuralDivergenceResponse> {
  return fetchJSON<StructuralDivergenceResponse>(
    `${API_BASE}/compare/${primaryId}/${secondaryId}/divergence/structural`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'primary_session_id' in v &&
          'secondary_session_id' in v &&
          'structural_comparison' in v &&
          typeof v.structural_comparison === 'object' &&
          v.structural_comparison !== null
        )
      },
      endpoint: '/compare/{primary_id}/{secondary_id}/divergence/structural',
    }
  )
}

export async function getTemporalDivergence(
  primaryId: string,
  secondaryId: string
): Promise<TemporalDivergenceResponse> {
  return fetchJSON<TemporalDivergenceResponse>(
    `${API_BASE}/compare/${primaryId}/${secondaryId}/divergence/temporal`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'primary_session_id' in v &&
          'secondary_session_id' in v &&
          'temporal_analysis' in v &&
          typeof v.temporal_analysis === 'object' &&
          v.temporal_analysis !== null
        )
      },
      endpoint: '/compare/{primary_id}/{secondary_id}/divergence/temporal',
    }
  )
}

export async function getBehavioralDivergence(
  primaryId: string,
  secondaryId: string
): Promise<BehavioralDivergenceResponse> {
  return fetchJSON<BehavioralDivergenceResponse>(
    `${API_BASE}/compare/${primaryId}/${secondaryId}/divergence/behavioral`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'primary_session_id' in v &&
          'secondary_session_id' in v &&
          'behavioral_analysis' in v &&
          typeof v.behavioral_analysis === 'object' &&
          v.behavioral_analysis !== null
        )
      },
      endpoint: '/compare/{primary_id}/{secondary_id}/divergence/behavioral',
    }
  )
}

export async function getBaselineDivergence(
  sessionId: string
): Promise<BaselineDivergenceResponse> {
  return fetchJSON<BaselineDivergenceResponse>(
    `${API_BASE}/sessions/${sessionId}/divergence/baseline`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return 'session_id' in v
      },
      endpoint: '/sessions/{session_id}/divergence/baseline',
    }
  )
}

export async function getDivergenceSummary(
  sessionId: string,
  limit: number = 5
): Promise<DivergenceSummaryResponse> {
  return fetchJSON<DivergenceSummaryResponse>(
    `${API_BASE}/sessions/${sessionId}/divergence/summary?limit=${limit}`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return 'session_id' in v
      },
      endpoint: '/sessions/{session_id}/divergence/summary',
    }
  )
}

// ============================================================================
// Reasoning Editor API functions (#192)
// ============================================================================

export async function editReasoning(
  sessionId: string,
  eventId: string,
  operation: EditOperation,
  fieldName: string = 'reasoning',
  newValue: unknown = null,
  position: number = -1
): Promise<{ session_id: string; edit: ReasoningEdit; modified_event: TraceEvent }> {
  const url = `${API_BASE}/sessions/${sessionId}/reasoning/edit`
  const response = await fetchWithRetry(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_id: eventId,
      operation,
      field_name: fieldName,
      new_value: newValue,
      position
    })
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function createScenarioBranch(
  sessionId: string,
  name: string,
  parentEventId: string,
  description: string = '',
  edits: Array<{ event_id: string; operation: EditOperation; field_name: string; new_value: unknown; position: number }> = []
): Promise<{ session_id: string; branch: ScenarioBranch }> {
  const url = `${API_BASE}/sessions/${sessionId}/reasoning/branch`
  const response = await fetchWithRetry(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      parent_event_id: parentEventId,
      description,
      edits
    })
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function getReplayEvents(
  sessionId: string,
  fromEventId: string,
  branchId: string | null = null,
  includeBranchEdits: boolean = true
): Promise<{ session_id: string; from_event_id: string; branch_id: string | null; replay_events: TraceEvent[]; replay_count: number }> {
  const url = new URL(`${API_BASE}/sessions/${sessionId}/reasoning/replay`)
  url.searchParams.append('from_event_id', fromEventId)
  if (branchId) url.searchParams.append('branch_id', branchId)
  url.searchParams.append('include_branch_edits', String(includeBranchEdits))

  return fetchJSON(url.toString())
}

export async function getHierarchicalReasoning(
  sessionId: string,
  eventId: string
): Promise<{ session_id: string; event_id: string; hierarchical_reasoning: HierarchicalReasoning }> {
  return fetchJSON(
    `${API_BASE}/sessions/${sessionId}/reasoning/hierarchical?event_id=${eventId}`
  )
}

export async function listScenarios(
  sessionId: string
): Promise<{ session_id: string; scenarios: ScenarioBranch[]; total_count: number }> {
  return fetchJSON(
    `${API_BASE}/sessions/${sessionId}/reasoning/scenarios`
  )
}

export async function getScenario(
  sessionId: string,
  branchId: string
): Promise<{ session_id: string; branch: ScenarioBranch }> {
  return fetchJSON(
    `${API_BASE}/sessions/${sessionId}/reasoning/scenarios/${branchId}`
  )
}

export async function compareScenarios(
  sessionId: string,
  branchIds: string[]
): Promise<{ session_id: string; comparison: ScenarioComparison }> {
  const url = new URL(`${API_BASE}/sessions/${sessionId}/reasoning/scenarios/compare`)
  branchIds.forEach(id => url.searchParams.append('branch_ids', id))

  return fetchJSON(url.toString())
}

export async function exportScenario(
  sessionId: string,
  branchId: string
): Promise<{ session_id: string; exported_scenario: ScenarioBranch }> {
  return fetchJSON(
    `${API_BASE}/sessions/${sessionId}/reasoning/scenarios/${branchId}/export`
  )
}

export async function importScenario(
  sessionId: string,
  scenarioData: Record<string, unknown>
): Promise<{ session_id: string; imported_branch: ScenarioBranch }> {
  const url = `${API_BASE}/sessions/${sessionId}/reasoning/scenarios/import`
  const response = await fetchWithRetry(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(scenarioData)
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

// =============================================================================
// Agent Stepper API functions
// =============================================================================

export async function setBreakpoint(
  sessionId: string,
  breakpointType: BreakpointType,
  conditionValue: unknown = null,
  description: string = ''
): Promise<BreakpointResponse> {
  const url = new URL(`${API_BASE}/sessions/${sessionId}/breakpoints`)
  url.searchParams.append('breakpoint_type', breakpointType)
  if (conditionValue !== null) {
    url.searchParams.append('condition_value', String(conditionValue))
  }
  if (description) {
    url.searchParams.append('description', description)
  }

  const response = await fetchWithRetry(url.toString(), {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function clearBreakpoint(
  sessionId: string,
  breakpointId: string
): Promise<{ session_id: string; success: boolean; stepper_state: StepperState }> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/breakpoints/${breakpointId}`,
    { method: 'DELETE' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function clearAllBreakpoints(
  sessionId: string
): Promise<{ session_id: string; success: boolean; breakpoints_cleared: number; stepper_state: StepperState }> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/breakpoints`,
    { method: 'DELETE' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function listBreakpoints(
  sessionId: string
): Promise<BreakpointsResponse> {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}/breakpoints`)
}

export async function stepExecution(
  sessionId: string,
  action: StepAction,
  targetEventId: string | null = null
): Promise<StepperResponse> {
  const url = new URL(`${API_BASE}/sessions/${sessionId}/step`)
  url.searchParams.append('action', action)
  if (targetEventId) {
    url.searchParams.append('target_event_id', targetEventId)
  }

  const response = await fetchWithRetry(url.toString(), {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function getStepperState(
  sessionId: string
): Promise<StepperStateResponse> {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}/state`)
}

export async function createBranch(
  sessionId: string,
  name: string,
  parentEventId: string,
  description: string = ''
): Promise<BranchResponse> {
  const url = new URL(`${API_BASE}/sessions/${sessionId}/branch`)
  url.searchParams.append('name', name)
  url.searchParams.append('parent_event_id', parentEventId)
  if (description) {
    url.searchParams.append('description', description)
  }

  const response = await fetchWithRetry(url.toString(), {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function listBranches(
  sessionId: string
): Promise<BranchesResponse> {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}/branches`)
}

export async function getBranch(
  sessionId: string,
  branchId: string
): Promise<BranchResponse> {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}/branches/${branchId}`)
}

export async function deleteBranch(
  sessionId: string,
  branchId: string
): Promise<{ session_id: string; branch_id: string; success: boolean }> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/branches/${branchId}`,
    { method: 'DELETE' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function resetStepper(
  sessionId: string
): Promise<{ session_id: string; success: boolean; stepper_state: StepperState }> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/stepper/reset`,
    { method: 'POST' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function getExecutionContext(
  sessionId: string
): Promise<ExecutionContextResponse> {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}/stepper/context`)
}

// ============================================================================
// Multi-agent Swimlane Debugger API functions (#193)
// ============================================================================

export async function getSwimlaneVisualization(
  sessionId: string
): Promise<SwimlaneVisualizationResponse> {
  return fetchJSON<SwimlaneVisualizationResponse>(
    `${API_BASE}/sessions/${sessionId}/swimlane`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'session_id' in v &&
          'swimlane_data' in v &&
          typeof v.swimlane_data === 'object' &&
          v.swimlane_data !== null
        )
      },
      endpoint: '/sessions/{session_id}/swimlane',
    }
  )
}

export async function getMessageFlows(
  sessionId: string
): Promise<MessageFlowsResponse> {
  return fetchJSON<MessageFlowsResponse>(
    `${API_BASE}/sessions/${sessionId}/messages`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'session_id' in v &&
          'message_flows' in v &&
          'flow_summary' in v &&
          Array.isArray(v.message_flows)
        )
      },
      endpoint: '/sessions/{session_id}/messages',
    }
  )
}

export async function getCoordinationAnalysis(
  sessionId: string
): Promise<CoordinationAnalysisResponse> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/coordination-analysis`,
    { method: 'POST' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<CoordinationAnalysisResponse>
}

export async function getEmergentBehaviors(
  sessionId: string
): Promise<EmergentBehaviorsResponse> {
  const response = await fetchWithRetry(
    `${API_BASE}/sessions/${sessionId}/emergent-behaviors`,
    { method: 'POST' }
  )
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<EmergentBehaviorsResponse>
}

export async function getMultiAgentAnalysis(
  sessionId: string
): Promise<MultiAgentAnalysisResponse> {
  return fetchJSON<MultiAgentAnalysisResponse>(
    `${API_BASE}/sessions/${sessionId}/multi-agent-analysis`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        return (
          'session_id' in v &&
          'swimlane_data' in v &&
          'coordination_analysis' in v &&
          'emergent_behavior_analysis' in v
        )
      },
      endpoint: '/sessions/{session_id}/multi-agent-analysis',
    }
  )
}

// ============================================================================
// Violation Detection API functions (#194)
// ============================================================================

export async function clusterSessions(params: {
  agentName?: string | null
  sessionIds?: string[] | null
  similarityThreshold?: number
  minClusterSize?: number
}): Promise<{
  clusters: TraceCluster[]
  global_outliers: string[]
  total_sessions_analyzed: number
  clustering_params: { similarity_threshold: number; min_cluster_size: number }
}> {
  const searchParams = new URLSearchParams()
  if (params.agentName) searchParams.append('agent_name', params.agentName)
  if (params.similarityThreshold !== undefined) searchParams.append('similarity_threshold', String(params.similarityThreshold))
  if (params.minClusterSize !== undefined) searchParams.append('min_cluster_size', String(params.minClusterSize))
  if (params.sessionIds) {
    params.sessionIds.forEach(id => searchParams.append('session_ids', id))
  }

  const url = `${API_BASE}/violations/cluster${searchParams.toString() ? '?' + searchParams.toString() : ''}`
  return fetchJSON(url)
}

export async function searchViolations(params: {
  nlQuery: string
  agentName?: string | null
  sessionIds?: string[] | null
  maxResults?: number
}): Promise<{
  violations: ViolationReport[]
  query: string
  total_sessions_searched: number
  total_violations_found: number
}> {
  const searchParams = new URLSearchParams()
  searchParams.append('nl_query', params.nlQuery)
  if (params.agentName) searchParams.append('agent_name', params.agentName)
  if (params.maxResults !== undefined) searchParams.append('max_results', String(params.maxResults))
  if (params.sessionIds) {
    params.sessionIds.forEach(id => searchParams.append('session_ids', id))
  }

  const url = `${API_BASE}/violations/search?${searchParams.toString()}`
  return fetchJSON(url)
}

export async function detectSparseFailures(params: {
  agentName?: string | null
  sessionIds?: string[] | null
  minOccurrences?: number
}): Promise<{
  sparse_failures: SparseFailurePattern[]
  total_sessions_analyzed: number
  total_patterns_found: number
  min_occurrences: number
}> {
  const searchParams = new URLSearchParams()
  if (params.agentName) searchParams.append('agent_name', params.agentName)
  if (params.minOccurrences !== undefined) searchParams.append('min_occurrences', String(params.minOccurrences))
  if (params.sessionIds) {
    params.sessionIds.forEach(id => searchParams.append('session_ids', id))
  }

  const url = `${API_BASE}/violations/sparse${searchParams.toString() ? '?' + searchParams.toString() : ''}`
  return fetchJSON(url)
}

export async function getViolationDashboard(params: {
  agentName?: string | null
  days?: number
}): Promise<{
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
    most_common_failure_types: Array<{ failure_type: string; occurrence_count: number }>
  }
  time_range_days: number
}> {
  const searchParams = new URLSearchParams()
  if (params.agentName) searchParams.append('agent_name', params.agentName)
  if (params.days !== undefined) searchParams.append('days', String(params.days))

  const url = `${API_BASE}/violations/dashboard${searchParams.toString() ? '?' + searchParams.toString() : ''}`
  return fetchJSON(url)
}

export async function getSessionEmbedding(sessionId: string): Promise<{
  session_id: string
  embedding: SessionEmbedding
}> {
  return fetchJSON(`${API_BASE}/violations/session/${sessionId}/embedding`)
}

export async function findSimilarSessions(params: {
  sessionId: string
  limit?: number
}): Promise<{
  reference_session_id: string
  similar_sessions: SimilarSession[]
  total_compared: number
}> {
  const searchParams = new URLSearchParams()
  if (params.limit !== undefined) searchParams.append('limit', String(params.limit))

  const url = `${API_BASE}/violations/session/${params.sessionId}/similar${searchParams.toString() ? '?' + searchParams.toString() : ''}`
  return fetchJSON(url)
}

// ============================================================================
// Agent Audit / Trust API
// ============================================================================

export async function getSessionAudit(sessionId: string): Promise<SessionAuditResponse> {
  return fetchJSON<SessionAuditResponse>(
    `${API_BASE}/sessions/${sessionId}/audit`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        if (v.session_id !== sessionId) return false
        const audit = v.audit
        if (typeof audit !== 'object' || audit === null) return false
        const a = audit as Record<string, unknown>
        return (
          'questions' in a &&
          typeof a.questions === 'object' &&
          a.questions !== null &&
          'claims' in a &&
          Array.isArray(a.claims) &&
          'signals' in a &&
          Array.isArray(a.signals) &&
          'failures' in a &&
          Array.isArray(a.failures) &&
          'trust' in a &&
          typeof a.trust === 'object' &&
          a.trust !== null
        )
      },
      endpoint: `/sessions/{session_id}/audit`,
    }
  )
}

export async function getDecisionJustification(
  sessionId: string,
  eventId: string
): Promise<DecisionJustificationResponse> {
  return fetchJSON<DecisionJustificationResponse>(
    `${API_BASE}/sessions/${sessionId}/decisions/${eventId}/justification`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        if (v.event_id !== eventId) return false
        const justification = v.justification
        if (typeof justification !== 'object' || justification === null) return false
        const j = justification as Record<string, unknown>
        return (
          'why' in j &&
          'evidence' in j &&
          'outcome' in j &&
          'where_it_failed' in j &&
          'policy' in j
        )
      },
      endpoint: `/sessions/{session_id}/decisions/{event_id}/justification`,
    }
  )
}

export async function getEvidenceGraph(
  sessionId: string
): Promise<EvidenceGraphResponse> {
  return fetchJSON<EvidenceGraphResponse>(
    `${API_BASE}/sessions/${sessionId}/evidence-graph`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        if (v.session_id !== sessionId) return false
        const graph = v.graph
        if (typeof graph !== 'object' || graph === null) return false
        const g = graph as Record<string, unknown>
        return (
          'nodes' in g &&
          Array.isArray(g.nodes) &&
          'edges' in g &&
          Array.isArray(g.edges) &&
          'stats' in g &&
          typeof g.stats === 'object' &&
          g.stats !== null
        )
      },
      endpoint: `/sessions/{session_id}/evidence-graph`,
    }
  )
}

export async function getAuditPortfolio(
  limit = 50
): Promise<PortfolioAuditResponse> {
  return fetchJSON<PortfolioAuditResponse>(
    `${API_BASE}/audit/portfolio?limit=${limit}`,
    {
      validator: (value: unknown) => {
        if (typeof value !== 'object' || value === null) return false
        const v = value as Record<string, unknown>
        const summary = v.summary
        if (typeof summary !== 'object' || summary === null) return false
        const s = summary as Record<string, unknown>
        return (
          typeof s.total_sessions === 'number' &&
          typeof s.trust === 'object' &&
          s.trust !== null &&
          Array.isArray(s.sessions)
        )
      },
      endpoint: `/audit/portfolio`,
    }
  )
}
