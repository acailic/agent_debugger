import type { TraceBundle, TraceEvent, Highlight } from '../types'
import { formatEventHeadline } from '../utils/formatting'
import { EventReferenceList } from './EventReferenceList'
import { DecisionProvenancePanel } from './DecisionProvenancePanel'
import { memo } from 'react'
import { BLOCKED_EVENT_TYPES } from '../utils/latency'

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
      <section className="event-detail panel panel--primary empty-panel">
        <span className="empty-icon">🔍</span>
        <p>Choose a trace node to inspect provenance, guardrails, and replay value.</p>
      </section>
    )
  }

  const isBlockedEvent = BLOCKED_EVENT_TYPES.includes(event.event_type)
  const isRepairAttempt = event.event_type === 'repair_attempt'
  const repairSequenceEvents = isRepairAttempt && event.repair_sequence_id
    ? [...eventLookup.values()]
      .filter((candidate) => candidate.event_type === 'repair_attempt' && candidate.repair_sequence_id === event.repair_sequence_id)
      .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime())
    : isRepairAttempt
      ? [event]
      : []
  const currentRepairIndex = repairSequenceEvents.findIndex((candidate) => candidate.id === event.id)
  const priorRepairEvents = currentRepairIndex > 0 ? repairSequenceEvents.slice(0, currentRepairIndex) : []
  const priorFailedRepairEvents = priorRepairEvents.filter((candidate) => candidate.repair_outcome === 'failure')

  return (
    <section className="event-detail panel panel--primary fade-in">
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
          <span title="How severe or impactful this event is">Severity {ranking.severity.toFixed(2)}</span>
          <span title="How unusual or new this behavior is">Novelty {ranking.novelty.toFixed(2)}</span>
          <span title="How frequently this pattern occurs">Recurrence {ranking.recurrence.toFixed(2)}</span>
          <span title="A metric measuring how closely this trace matches expected behavior patterns">Replay {ranking.replay_value.toFixed(2)}</span>
          <span title="Combined ranking score (severity × novelty × recurrence × replay)">Composite {ranking.composite.toFixed(2)} <small>(severity + novelty + recurrence + replay)</small></span>
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

        <DecisionProvenancePanel
          event={event}
          eventLookup={eventLookup}
          onSelectEvent={onSelectEvent}
        />

        {event.reasoning && (
          <div>
            <h3>Reasoning</h3>
            <p>{event.reasoning}</p>
          </div>
        )}
        {isRepairAttempt && (
          <div>
            <h3>Repair Attempt</h3>
            <div className="analysis-strip">
              <span>Outcome {event.repair_outcome ?? 'failure'}</span>
              <span>Sequence {event.repair_sequence_id ?? 'standalone'}</span>
              <span>Prior attempts {priorRepairEvents.length}</span>
              <span>Prior failed {priorFailedRepairEvents.length}</span>
            </div>
            {event.attempted_fix && <p><strong>Attempted fix:</strong> {event.attempted_fix}</p>}
            {event.validation_result && <p><strong>Validation:</strong> {event.validation_result}</p>}
            {event.repair_diff && (
              <div>
                <h3>Repair Diff</h3>
                <pre>{event.repair_diff}</pre>
              </div>
            )}
            {repairSequenceEvents.length > 1 && (
              <EventReferenceList
                title="Repair Sequence"
                eventIds={repairSequenceEvents.map((candidate) => candidate.id)}
                eventLookup={eventLookup}
                onSelectEvent={onSelectEvent}
              />
            )}
            {priorRepairEvents.length > 0 && (
              <EventReferenceList
                title="Prior Repair Attempts"
                eventIds={priorRepairEvents.map((candidate) => candidate.id)}
                eventLookup={eventLookup}
                onSelectEvent={onSelectEvent}
              />
            )}
          </div>
        )}
        {isBlockedEvent && (
          <div>
            <h3>Blocked Action Context</h3>
            <div className="analysis-strip">
              <span>Outcome {event.outcome ?? 'blocked'}</span>
              <span>Policy {event.policy_name ?? 'unknown'}</span>
              <span>Risk {event.risk_level ?? event.severity ?? 'unknown'}</span>
            </div>
            {event.blocked_action && <p><strong>Blocked:</strong> {event.blocked_action}</p>}
            {event.reason && <p><strong>Reason:</strong> {event.reason}</p>}
            {event.safe_alternative && <p><strong>Safe alternative:</strong> {event.safe_alternative}</p>}
            {event.rationale && <p><strong>Rationale:</strong> {event.rationale}</p>}
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

// Custom comparison for EventDetail - memoize on event identity
function arePropsEqual(
  prevProps: Readonly<EventDetailProps>,
  nextProps: Readonly<EventDetailProps>
): boolean {
  return (
    prevProps.event === nextProps.event &&
    prevProps.ranking === nextProps.ranking &&
    prevProps.diagnosis === nextProps.diagnosis &&
    prevProps.highlight === nextProps.highlight &&
    prevProps.eventLookup === nextProps.eventLookup
  )
}

export const EventDetailMemo = memo(EventDetail, arePropsEqual)
