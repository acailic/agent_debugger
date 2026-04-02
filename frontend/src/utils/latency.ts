import type { EventType } from '../types'

export const BLOCKED_EVENT_TYPES: EventType[] = [
  'safety_check',
  'refusal',
  'policy_violation',
]

export const EVENT_TYPE_FILTERS: {
  label: string
  types: EventType[]
  color: string
}[] = [
  { label: 'All', types: [], color: '#6366f1' },
  { label: 'LLM', types: ['llm_request', 'llm_response'], color: '#8b5cf6' },
  { label: 'Tools', types: ['tool_call', 'tool_result'], color: '#06b6d4' },
  { label: 'Decisions', types: ['decision'], color: '#f59e0b' },
  { label: 'Errors', types: ['error'], color: '#ef4444' },
  {
    label: 'Agents',
    types: ['agent_start', 'agent_end', 'agent_turn'],
    color: '#10b981',
  },
]

export function filterEvents(
  events: { event_type: EventType }[],
  activeFilter: (typeof EVENT_TYPE_FILTERS)[number],
  showBlockedActions: boolean
): { event_type: EventType }[] {
  return events.filter((event) => {
    if (
      activeFilter.types.length > 0 &&
      !activeFilter.types.includes(event.event_type)
    ) {
      return false
    }
    if (!showBlockedActions) {
      return !BLOCKED_EVENT_TYPES.includes(event.event_type)
    }
    return true
  })
}

export function getLatencyColor(
  durationMs: number | undefined,
  avgDuration: number
): string {
  if (durationMs === undefined) return 'transparent'
  if (durationMs > avgDuration * 2) return '#ef4444'
  if (durationMs > avgDuration * 1.5) return '#f59e0b'
  if (durationMs > avgDuration) return '#fbbf24'
  return '#10b981'
}

export function getLatencyWidth(
  durationMs: number | undefined,
  maxDuration: number
): number {
  if (durationMs === undefined || maxDuration === 0) return 0
  return Math.min(Math.max((durationMs / maxDuration) * 100, 5), 100)
}
