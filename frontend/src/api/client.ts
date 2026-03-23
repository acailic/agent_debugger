import type { ReplayResponse, Session, TraceAnalysis, TraceBundle, TraceEvent } from '../types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function getSessions() {
  return fetchJSON<{ sessions: Session[]; total: number; limit: number; offset: number }>(`${API_BASE}/sessions`)
}

export async function getSessionTraces(sessionId: string, limit = 100) {
  return fetchJSON<{ traces: TraceEvent[]; session_id: string }>(`${API_BASE}/sessions/${sessionId}/traces?limit=${limit}`)
}

export async function getSessionTree(sessionId: string) {
  return fetchJSON<{ session_id: string; events: TraceEvent[] }>(`${API_BASE}/sessions/${sessionId}/tree`)
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
  return fetchJSON<ReplayResponse>(`${API_BASE}/sessions/${sessionId}/replay?${search.toString()}`)
}

export async function getAnalysis(sessionId: string) {
  return fetchJSON<{ session_id: string; analysis: TraceAnalysis }>(`${API_BASE}/sessions/${sessionId}/analysis`)
}

export function createEventSource(sessionId: string): EventSource {
  return new EventSource(`${API_BASE}/sessions/${sessionId}/stream`)
}
