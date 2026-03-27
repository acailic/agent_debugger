import type { TraceEvent, Highlight } from '../types'

interface TraceTimelineProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  highlightEventIds?: Set<string>
  /** Map of event_id to Highlight for displaying reasons */
  highlightsMap?: Map<string, Highlight>
}

function describeEvent(event: TraceEvent): string {
  switch (event.event_type) {
    case 'tool_call':
    case 'tool_result':
      return event.tool_name ?? event.name
    case 'decision':
      return event.chosen_action ?? event.name
    case 'refusal':
      return event.reason ?? event.name
    case 'safety_check':
      return event.policy_name ?? event.name
    case 'policy_violation':
      return event.violation_type ?? event.name
    case 'agent_turn':
      return `${event.speaker ?? event.agent_id}: ${event.goal ?? event.name}`
    default:
      return event.name
  }
}

export function TraceTimeline({ events, selectedEventId, onSelectEvent, highlightEventIds, highlightsMap }: TraceTimelineProps) {
  return (
    <div className="trace-timeline">
      <div className="timeline-header">
        <h3>Event Timeline</h3>
        <span className="event-count">{events.length} events</span>
      </div>

      <div className="timeline-events">
        {events.map((event) => {
          const isHighlight = highlightEventIds?.has(event.id) ?? false
          const highlight = highlightsMap?.get(event.id)
          return (
            <div
              key={event.id}
              className={`timeline-event ${event.event_type} ${event.id === selectedEventId ? 'selected' : ''} ${isHighlight ? 'highlight' : ''}`}
              onClick={() => onSelectEvent(event.id)}
            >
              <div className="event-marker" />
              {isHighlight && <span className="highlight-marker" title="Highlighted event">*</span>}
              <div className="event-info">
                <span className="event-type">{event.event_type.replaceAll('_', ' ')}</span>
                <span className="event-summary">{describeEvent(event)}</span>
                <span className="event-time">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
                {highlight && <span className="highlight-reason">{highlight.reason}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
