import type { EventType, TraceEvent } from '../types'

export function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
}

export function formatEventHeadline(event: TraceEvent | null, fallback = 'Select an event'): string {
  if (!event) return fallback
  switch (event.event_type) {
    case 'agent_start':
      return 'Agent Start'
    case 'agent_end':
      return 'Agent End'
    case 'llm_request':
      return 'LLM Request'
    case 'llm_response':
      return 'LLM Response'
    case 'checkpoint':
      return `Checkpoint ${event.sequence ?? ''}`.trim()
    case 'tool_call':
      return event.tool_name ?? event.name
    case 'tool_result':
      return event.tool_name ?? event.name
    case 'decision':
      return event.chosen_action ?? event.name
    case 'refusal':
      return event.reason ?? event.name
    case 'safety_check':
      return `${event.policy_name ?? 'Safety'} · ${event.outcome ?? 'pass'}`
    case 'policy_violation':
      return event.violation_type ?? event.name
    case 'prompt_policy':
      return event.template_id ?? event.name
    case 'agent_turn':
      return `${event.speaker ?? event.agent_id ?? 'Agent'} turn`
    case 'behavior_alert':
      return event.alert_type ?? event.name
    case 'error':
      return event.error_type ?? event.name
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
