import type { TraceEvent } from '../types'
import { formatEventHeadline } from '../utils/formatting'

interface EventReferenceListProps {
  title: string
  eventIds: string[]
  eventLookup: Map<string, TraceEvent>
  onSelectEvent: (eventId: string) => void
}

export function EventReferenceList({ title, eventIds, eventLookup, onSelectEvent }: EventReferenceListProps) {
  const uniqueIds = [...new Set(eventIds)]
  if (!uniqueIds.length) return null

  return (
    <div>
      <h3>{title}</h3>
      <div className="reference-list">
        {uniqueIds.map((eventId) => {
          const relatedEvent = eventLookup.get(eventId)
          if (!relatedEvent) {
            return (
              <span key={eventId} className="reference-chip missing">
                Missing {eventId.slice(0, 8)}
              </span>
            )
          }

          return (
            <button key={eventId} type="button" className="reference-chip" onClick={() => onSelectEvent(eventId)}>
              <span>{relatedEvent.event_type.replaceAll('_', ' ')}</span>
              <strong>{formatEventHeadline(relatedEvent)}</strong>
            </button>
          )
        })}
      </div>
    </div>
  )
}
