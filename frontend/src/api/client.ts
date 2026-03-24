import type {
  AgentBaseline,
  DriftResponse,
  LiveSummary,
  ReplayResponse,
  Session,
  TraceAnalysis,
  TraceBundle,
  TraceSearchResponse,
} from '../types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function getSessions(params: { sortBy?: 'started_at' | 'replay_value' } = {}) {
  const search = new URLSearchParams()
  if (params.sortBy) search.set('sort_by', params.sortBy)
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return fetchJSON<{ sessions: Session[]; total: number; limit: number; offset: number }>(`${API_BASE}/sessions${suffix}`)
}

export async function getTraceBundle(sessionId: string) {
  return fetchJSON<TraceBundle>(`${API_BASE}/sessions/${sessionId}/trace`)
}

export async function getReplay(
  sessionId: string,
  params: {
    mode?: 'full' | 'focus' | 'failure'
    focusEventId?: string | null
    breakpointEventTypes?: string[]
    breakpointToolNames?: string[]
    breakpointConfidenceBelow?: number | null
    breakpointSafetyOutcomes?: string[]
    stopAtBreakpoint?: boolean
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
  return fetchJSON<ReplayResponse>(`${API_BASE}/sessions/${sessionId}/replay?${search.toString()}`)
}

export async function getAnalysis(sessionId: string) {
  return fetchJSON<{ session_id: string; analysis: TraceAnalysis }>(`${API_BASE}/sessions/${sessionId}/analysis`)
}

export function createEventSource(sessionId: string): EventSource {
  return new EventSource(`${API_BASE}/sessions/${sessionId}/stream`)
}

export async function getLiveSummary(sessionId: string) {
  return fetchJSON<{ session_id: string; live_summary: LiveSummary }>(`${API_BASE}/sessions/${sessionId}/live`)
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
  return fetchJSON<TraceSearchResponse>(`${API_BASE}/traces/search?${search.toString()}`)
}

export async function getAgentBaseline(agentName: string): Promise<AgentBaseline> {
  return fetchJSON<AgentBaseline>(`${API_BASE}/agents/${encodeURIComponent(agentName)}/baseline`)
}

export async function getAgentDrift(agentName: string): Promise<DriftResponse> {
  return fetchJSON<DriftResponse>(`${API_BASE}/agents/${encodeURIComponent(agentName)}/drift`)
}
