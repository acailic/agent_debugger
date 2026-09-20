import type { TraceEvent } from '../types'

export function mergeSessionEvents(events: TraceEvent[], liveEvents: TraceEvent[]): TraceEvent[] {
  const merged = [...events]
  const seen = new Set(events.map((event) => event.id))
  for (const event of liveEvents) {
    if (!seen.has(event.id)) {
      merged.push(event)
      seen.add(event.id)
    }
  }
  return merged.sort((left, right) => left.timestamp.localeCompare(right.timestamp))
}
