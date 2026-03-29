import type { TraceBundle, TraceEvent, Highlight } from '../types'
import { formatEventHeadline } from '../utils/formatting'
import { EventReferenceList } from './EventReferenceList'

interface EventDetailProps {
  event: TraceEvent | null
  ranking?: TraceBundle['analysis']['event_rankings'][number]
  diagnosis?: TraceBundle['analysis']['failure_explanations'][number]
  highlight?: Highlight | null
  eventLookup: Map<string, TraceEvent>
  onSelectEvent: (eventId: string) => void
  onFocusReplay: (eventId: string) => void
  onReplayFromHere: (eventId: string) => void
  onResetReplay: () => void
}

export function EventDetail({
  event,
  ranking,
  diagnosis,
  highlight,
  eventLookup,
  onSelectEvent,
  onFocusReplay,
  onReplayFromHere,
  onResetReplay,
}: EventDetailProps) {
  if (!event) {
    return (
      <section className="event-detail panel empty-panel">
        <p>Choose a trace node to inspect provenance, guardrails, and replay value.</p>
      </section>
    )
  }

  return (
    <section className="event-detail panel">
      {highlight && (
        <div className="highlight-info-card">
          <h4>Why highlighted</h4>
          <p>{highlight.reason}</p>
        </div>
      )}
      <div className="detail-header">
        <div>
          <p className="eyebrow">Event Detail</p>
          <h2>{formatEventHeadline(event)}</h2>
        </div>
        <span className={`event-chip ${event.event_type}`}>{event.event_type.replaceAll('_', ' ')}</span>
      </div>

      <div className="detail-actions">
        <button type="button" onClick={() => onFocusReplay(event.id)}>
          Focus replay
        </button>
        <button type="button" onClick={() => onReplayFromHere(event.id)}>
          Replay from here
        </button>
        <button type="button" onClick={onResetReplay}>
          Full session
        </button>
      </div>

      <div className="detail-grid">
        <div>
          <span className="metric-label">Importance</span>
          <strong>{event.importance.toFixed(2)}</strong>
        </div>
        <div>
          <span className="metric-label">Timestamp</span>
          <strong>{new Date(event.timestamp).toLocaleTimeString()}</strong>
        </div>
        <div>
          <span className="metric-label">Parent</span>
          <strong>{event.parent_id ? event.parent_id.slice(0, 8) : 'root'}</strong>
        </div>
        <div>
          <span className="metric-label">Upstream</span>
          <strong>{event.upstream_event_ids.length}</strong>
        </div>
      </div>

      {ranking && (
        <div className="analysis-strip">
          <span>Severity {ranking.severity.toFixed(2)}</span>
          <span>Novelty {ranking.novelty.toFixed(2)}</span>
          <span>Recurrence {ranking.recurrence.toFixed(2)}</span>
          <span>Replay {ranking.replay_value.toFixed(2)}</span>
          <span>Composite {ranking.composite.toFixed(2)}</span>
        </div>
      )}

      <div className="detail-sections">
        {diagnosis && (
          <div className="diagnosis-card">
            <div className="diagnosis-head">
              <h3>Failure Diagnosis</h3>
              <span className="diagnosis-badge">{diagnosis.failure_mode.replaceAll('_', ' ')}</span>
            </div>
            <p>{diagnosis.narrative}</p>
            <div className="analysis-strip">
              <span>Confidence {diagnosis.confidence.toFixed(2)}</span>
              <span>Candidates {diagnosis.candidates.length}</span>
              <span>Inspect {diagnosis.next_inspection_event_id.slice(0, 8)}</span>
            </div>
            {diagnosis.likely_cause_event_id ? (
              <div className="detail-actions">
                <button type="button" onClick={() => onSelectEvent(diagnosis.likely_cause_event_id!)}>
                  Inspect likely cause
                </button>
                <button type="button" onClick={() => onFocusReplay(diagnosis.next_inspection_event_id)}>
                  Replay from suspect
                </button>
              </div>
            ) : null}
            <EventReferenceList
              title="Supporting Chain"
              eventIds={diagnosis.supporting_event_ids}
              eventLookup={eventLookup}
              onSelectEvent={onSelectEvent}
            />
            {diagnosis.candidates.length ? (
              <div>
                <h3>Candidate Causes</h3>
                <div className="candidate-list">
                  {diagnosis.candidates.map((candidate) => (
                    <button
                      key={candidate.event_id}
                      type="button"
                      className="candidate-card"
                      onClick={() => onSelectEvent(candidate.event_id)}
                    >
                      <div className="candidate-head">
                        <span>{candidate.event_type.replaceAll('_', ' ')}</span>
                        <strong>{candidate.score.toFixed(2)}</strong>
                      </div>
                      <strong>{candidate.headline}</strong>
                      <p>{candidate.rationale}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
        {event.reasoning && (
          <div>
            <h3>Reasoning</h3>
            <p>{event.reasoning}</p>
          </div>
        )}
        {event.evidence?.length ? (
          <div>
            <h3>Evidence</h3>
            <pre>{JSON.stringify(event.evidence, null, 2)}</pre>
          </div>
        ) : null}
        {event.evidence_event_ids?.length ? (
          <EventReferenceList
            title="Evidence Provenance"
            eventIds={event.evidence_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        ) : null}
        {event.upstream_event_ids.length ? (
          <EventReferenceList
            title="Upstream Context"
            eventIds={event.upstream_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        ) : null}
        {event.related_event_ids?.length ? (
          <EventReferenceList
            title="Related Events"
            eventIds={event.related_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        ) : null}
        {event.rationale && (
          <div>
            <h3>Guardrail Rationale</h3>
            <p>{event.rationale}</p>
          </div>
        )}
        {event.signal && (
          <div>
            <h3>Behavior Signal</h3>
            <p>{event.signal}</p>
          </div>
        )}
        <div>
          <h3>Payload</h3>
          <pre>{JSON.stringify(event, null, 2)}</pre>
        </div>
      </div>
    </section>
  )
}
