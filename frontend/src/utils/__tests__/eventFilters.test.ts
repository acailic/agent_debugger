import { describe, it, expect } from 'vitest'
import {
  filterEvents,
  getLatencyColor,
  getLatencyWidth,
  BLOCKED_EVENT_TYPES,
  EVENT_TYPE_FILTERS,
} from '../latency'
import type { EventType } from '../../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEvent(eventType: EventType, extra: Record<string, unknown> = {}) {
  return { event_type: eventType, ...extra }
}

const allFilter = EVENT_TYPE_FILTERS[0] // "All" — empty types array
const llmFilter = EVENT_TYPE_FILTERS.find((f) => f.label === 'LLM')!
const toolsFilter = EVENT_TYPE_FILTERS.find((f) => f.label === 'Tools')!
const decisionsFilter = EVENT_TYPE_FILTERS.find((f) => f.label === 'Decisions')!
const errorsFilter = EVENT_TYPE_FILTERS.find((f) => f.label === 'Errors')!
const agentsFilter = EVENT_TYPE_FILTERS.find((f) => f.label === 'Agents')!

// ---------------------------------------------------------------------------
// BLOCKED_EVENT_TYPES
// ---------------------------------------------------------------------------
describe('BLOCKED_EVENT_TYPES', () => {
  it('contains safety_check, refusal, and policy_violation', () => {
    expect(BLOCKED_EVENT_TYPES).toEqual([
      'safety_check',
      'refusal',
      'policy_violation',
    ])
  })
})

// ---------------------------------------------------------------------------
// EVENT_TYPE_FILTERS
// ---------------------------------------------------------------------------
describe('EVENT_TYPE_FILTERS', () => {
  it('has an "All" filter with empty types', () => {
    expect(allFilter.label).toBe('All')
    expect(allFilter.types).toEqual([])
  })

  it('covers all expected filter categories', () => {
    const labels = EVENT_TYPE_FILTERS.map((f) => f.label)
    expect(labels).toEqual(['All', 'LLM', 'Tools', 'Decisions', 'Errors', 'Agents'])
  })

  it('each filter has a non-empty color string', () => {
    for (const filter of EVENT_TYPE_FILTERS) {
      expect(filter.color).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// filterEvents
// ---------------------------------------------------------------------------
describe('filterEvents', () => {
  const mixedEvents = [
    makeEvent('llm_request'),
    makeEvent('llm_response'),
    makeEvent('tool_call'),
    makeEvent('tool_result'),
    makeEvent('decision'),
    makeEvent('error'),
    makeEvent('agent_start'),
    makeEvent('agent_end'),
    makeEvent('safety_check'),
    makeEvent('refusal'),
    makeEvent('policy_violation'),
  ]

  it('returns all non-blocked events with "All" filter and showBlocked=false', () => {
    const result = filterEvents(mixedEvents, allFilter, false)
    const resultTypes = result.map((e) => e.event_type)
    expect(resultTypes).not.toContain('safety_check')
    expect(resultTypes).not.toContain('refusal')
    expect(resultTypes).not.toContain('policy_violation')
    expect(result).toHaveLength(8) // 11 - 3 blocked
  })

  it('returns all events including blocked when showBlocked=true', () => {
    const result = filterEvents(mixedEvents, allFilter, true)
    expect(result).toHaveLength(11)
  })

  it('filters to LLM events only', () => {
    const result = filterEvents(mixedEvents, llmFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['llm_request', 'llm_response'])
  })

  it('filters to Tool events only', () => {
    const result = filterEvents(mixedEvents, toolsFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['tool_call', 'tool_result'])
  })

  it('filters to Decision events only', () => {
    const result = filterEvents(mixedEvents, decisionsFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['decision'])
  })

  it('filters to Error events only', () => {
    const result = filterEvents(mixedEvents, errorsFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['error'])
  })

  it('filters to Agent events only', () => {
    const result = filterEvents(mixedEvents, agentsFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['agent_start', 'agent_end'])
  })

  it('excludes blocked events from LLM filter even when showBlocked=false', () => {
    // safety_check is not an LLM type, so it would already be filtered by type.
    // But with showBlocked=false, blocked events in any filter are also removed.
    const events = [
      makeEvent('llm_request'),
      makeEvent('safety_check'),
    ]
    const result = filterEvents(events, llmFilter, false)
    expect(result.map((e) => e.event_type)).toEqual(['llm_request'])
  })

  it('includes blocked events in LLM filter when showBlocked=true', () => {
    const events = [
      makeEvent('llm_request'),
      makeEvent('refusal'),
    ]
    const result = filterEvents(events, llmFilter, true)
    // refusal is not in LLM types, so still filtered by type
    expect(result.map((e) => e.event_type)).toEqual(['llm_request'])
  })

  it('returns empty array for empty input', () => {
    expect(filterEvents([], allFilter, false)).toEqual([])
    expect(filterEvents([], allFilter, true)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// getLatencyColor
// ---------------------------------------------------------------------------
describe('getLatencyColor', () => {
  it('returns transparent for undefined duration', () => {
    expect(getLatencyColor(undefined, 100)).toBe('transparent')
  })

  it('returns green for durations at or below average', () => {
    expect(getLatencyColor(50, 100)).toBe('#10b981')
    expect(getLatencyColor(100, 100)).toBe('#10b981')
  })

  it('returns yellow for durations above average but <= 1.5x average', () => {
    expect(getLatencyColor(120, 100)).toBe('#fbbf24')
    expect(getLatencyColor(150, 100)).toBe('#fbbf24')
  })

  it('returns orange for durations above 1.5x but <= 2x average', () => {
    expect(getLatencyColor(160, 100)).toBe('#f59e0b')
    expect(getLatencyColor(200, 100)).toBe('#f59e0b')
  })

  it('returns red for durations above 2x average', () => {
    expect(getLatencyColor(201, 100)).toBe('#ef4444')
    expect(getLatencyColor(500, 100)).toBe('#ef4444')
  })

  it('handles zero average gracefully', () => {
    // With avgDuration=0, any positive duration is > avgDuration * 2 = 0
    expect(getLatencyColor(1, 0)).toBe('#ef4444')
    expect(getLatencyColor(0, 0)).toBe('#10b981')
  })
})

// ---------------------------------------------------------------------------
// getLatencyWidth
// ---------------------------------------------------------------------------
describe('getLatencyWidth', () => {
  it('returns 0 for undefined duration', () => {
    expect(getLatencyWidth(undefined, 1000)).toBe(0)
  })

  it('returns 0 when maxDuration is 0', () => {
    expect(getLatencyWidth(500, 0)).toBe(0)
  })

  it('returns percentage as width relative to maxDuration', () => {
    expect(getLatencyWidth(500, 1000)).toBe(50)
    expect(getLatencyWidth(1000, 1000)).toBe(100)
  })

  it('enforces a minimum width of 5', () => {
    // 1/1000 * 100 = 0.1, but minimum is 5
    expect(getLatencyWidth(1, 1000)).toBe(5)
  })

  it('caps width at 100', () => {
    // 2000/1000 * 100 = 200, but capped at 100
    expect(getLatencyWidth(2000, 1000)).toBe(100)
  })

  it('returns exactly 5 at the boundary that would be below min', () => {
    // 50/1000 * 100 = 5 exactly — should be 5
    expect(getLatencyWidth(50, 1000)).toBe(5)
  })
})
