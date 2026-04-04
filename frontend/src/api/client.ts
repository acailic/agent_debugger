import type {
  AgentBaseline,
  AlertPolicy,
  AlertStatus,
  AlertSummary,
  AlertTrendingPoint,
  AnalyticsResponse,
  CostSummary,
  DriftResponse,
  FixNoteResponse,
  LiveSummary,
  ManagedAlert,
  ReplayResponse,
  SearchResponse,
  Session,
  SessionCost,
  SimilarFailuresResponse,
  TopSession,
  TraceAnalysis,
  TraceBundle,
  TraceSearchResponse,
} from '../types'
import { validateResponse, logValidationFailure, validators, ValidationError } from './validation'

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
        console.warn(`[API Validation] Using fallback data for endpoint: ${config.endpoint}`)
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
    body: JSON.stringify({ status, resolution_note: note }),
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
  return response.json() as Promise<{ updated: number; failed: number }>
}

export async function fetchAlertSummary() {
  return fetchJSON<AlertSummary>(`${API_BASE}/alerts/summary`)
}

export async function fetchAlertTrending(days: number = 7) {
  return fetchJSON<AlertTrendingPoint[]>(`${API_BASE}/alerts/trending?days=${days}`)
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
