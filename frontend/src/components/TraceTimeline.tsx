import { useState } from 'react'
import type { TraceEvent, Highlight } from '../types'
import { formatEventHeadline } from '../utils/formatting'

interface TraceTimelineProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  highlightEventIds?: Set<string>
  /** Map of event_id to Highlight for displaying reasons */
  highlightsMap?: Map<string, Highlight>
}

const BLOCKED_EVENT_TYPES = ['safety_check', 'refusal', 'policy_violation']

export function TraceTimeline({ events, selectedEventId, onSelectEvent, highlightEventIds, highlightsMap }: TraceTimelineProps) {
  const [showBlockedActions, setShowBlockedActions] = useState(false)

  const filteredEvents = events.filter((event) => {
    if (showBlockedActions) {
      return true
    }
    return !BLOCKED_EVENT_TYPES.includes(event.event_type)
  })

  const isBlockedEvent = (event: TraceEvent): boolean => {
    return BLOCKED_EVENT_TYPES.includes(event.event_type)
  }

  return (
    <div className="trace-timeline">
      <div className="timeline-header">
        <div className="timeline-header-left">
          <h3>Event Timeline</h3>
          <span className="event-count">{filteredEvents.length} events</span>
        </div>
        <div className="timeline-header-right">
          <label className="blocked-actions-toggle">
            <input
              type="checkbox"
              checked={showBlockedActions}
              onChange={(e) => setShowBlockedActions(e.target.checked)}
              className="toggle-checkbox"
            />
            <span className="toggle-label">Show Blocked Actions</span>
          </label>
        </div>
      </div>

      <div className="timeline-events">
        {filteredEvents.map((event) => {
          const isHighlight = highlightEventIds?.has(event.id) ?? false
          const highlight = highlightsMap?.get(event.id)
          const blocked = isBlockedEvent(event)
          return (
            <div
              key={event.id}
              className={`timeline-event ${event.event_type} ${event.id === selectedEventId ? 'selected' : ''} ${isHighlight ? 'highlight' : ''} ${blocked ? 'blocked' : ''}`}
              onClick={() => onSelectEvent(event.id)}
            >
              <div className="event-marker" />
              {isHighlight && <span className="highlight-marker" title="Highlighted event">*</span>}
              {blocked && <span className="blocked-badge">BLOCKED</span>}
              <div className="event-info">
                <span className="event-type">{event.event_type.replaceAll('_', ' ')}</span>
                <span className="event-summary">{formatEventHeadline(event)}</span>
                <span className="event-time">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
                {blocked && event.blocked_action && (
                  <span className="blocked-action">Blocked: {event.blocked_action}</span>
                )}
                {blocked && event.reason && (
                  <span className="blocked-reason">Reason: {event.reason}</span>
                )}
                {highlight && <span className="highlight-reason">{highlight.reason}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
