import type { EventType, TraceEvent } from '../types'

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
}

export function formatEventHeadline(event: TraceEvent | null): string {
  if (!event) return 'Select an event'
  switch (event.event_type) {
    case 'decision':
      return event.chosen_action ?? event.name
    case 'tool_call':
    case 'tool_result':
      return event.tool_name ?? event.name
    case 'refusal':
      return event.reason ?? event.name
    case 'safety_check':
      return `${event.policy_name ?? 'Safety'} · ${event.outcome ?? 'pass'}`
    case 'policy_violation':
      return event.violation_type ?? event.name
    case 'behavior_alert':
      return event.alert_type ?? event.name
    case 'agent_turn':
      return `${event.speaker ?? event.agent_id ?? 'Agent'} turn`
    default:
      return event.name
  }
}

export const SEARCHABLE_EVENT_TYPES: Array<{ value: '' | EventType; label: string }> = [
  { value: '', label: 'All event types' },
  { value: 'decision', label: 'Decisions' },
  { value: 'tool_call', label: 'Tool calls' },
  { value: 'tool_result', label: 'Tool results' },
  { value: 'llm_request', label: 'LLM requests' },
  { value: 'llm_response', label: 'LLM responses' },
  { value: 'safety_check', label: 'Safety checks' },
  { value: 'refusal', label: 'Refusals' },
  { value: 'policy_violation', label: 'Policy violations' },
  { value: 'agent_turn', label: 'Agent turns' },
  { value: 'behavior_alert', label: 'Behavior alerts' },
  { value: 'error', label: 'Errors' },
]
