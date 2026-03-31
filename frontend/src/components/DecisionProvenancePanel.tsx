import type { TraceEvent } from '../types'
import { EventReferenceList } from './EventReferenceList'

interface DecisionProvenancePanelProps {
  event: TraceEvent
  eventLookup: Map<string, TraceEvent>
  onSelectEvent: (eventId: string) => void
}

export function DecisionProvenancePanel({ event, eventLookup, onSelectEvent }: DecisionProvenancePanelProps) {
  if (event.event_type !== 'decision') {
    return null
  }

  const hasEvidence = event.evidence && event.evidence.length > 0
  const hasAlternatives = event.alternatives && event.alternatives.length > 0

  return (
    <div className="decision-provenance panel panel--secondary">
      <div className="panel-head">
        <p className="eyebrow">Decision Provenance</p>
        <h2>Decision Analysis</h2>
      </div>

      <div className="provenance-sections">
        {/* Question 1: What was the decision? */}
        <div className="provenance-card">
          <h3>What was the decision?</h3>
          {event.chosen_action ? (
            <p className="decision-action">{event.chosen_action}</p>
          ) : (
            <p className="no-data">No chosen action recorded</p>
          )}
          {event.reasoning && (
            <div className="reasoning-text">
              <span className="metric-label">Reasoning</span>
              <p>{event.reasoning}</p>
            </div>
          )}
          {event.confidence !== undefined && (
            <div className="confidence-meter">
              <span className="metric-label">Confidence</span>
              <div className="confidence-bar">
                <div
                  className="confidence-fill"
                  style={{ width: `${event.confidence * 100}%` }}
                  title={`Confidence: ${(event.confidence * 100).toFixed(1)}%`}
                />
              </div>
              <span>{(event.confidence * 100).toFixed(1)}%</span>
            </div>
          )}
        </div>

        {/* Question 2: What evidence supported it? */}
        <div className="provenance-card">
          <h3>What evidence supported it?</h3>
          {hasEvidence ? (
            <div className="evidence-list">
              {event.evidence!.map((item, index) => (
                <div key={index} className="evidence-item">
                  <pre>{JSON.stringify(item, null, 2)}</pre>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-evidence-badge">
              <span className="warning-icon">⚠️</span>
              <span>No evidence captured</span>
            </div>
          )}
        </div>

        {/* Question 3: Which upstream events produced that evidence? */}
        {event.evidence_event_ids && event.evidence_event_ids.length > 0 && (
          <EventReferenceList
            title="Which upstream events produced this evidence?"
            eventIds={event.evidence_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        )}

        {/* Question 4: What alternatives were rejected? */}
        <div className="provenance-card">
          <h3>What alternatives were rejected?</h3>
          {hasAlternatives ? (
            <div className="alternatives-list">
              {event.alternatives!.map((alt, index) => (
                <div key={index} className="alternative-item">
                  <pre>{JSON.stringify(alt, null, 2)}</pre>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-data">No alternatives recorded</p>
          )}
        </div>
      </div>
    </div>
  )
}
