import type { TraceBundle } from '../types'

interface FailureExplanationCardProps {
  explanation: TraceBundle['analysis']['failure_explanations'][number]
  onInspect: (eventId: string) => void
  onFocusReplay: (eventId: string) => void
}

export function FailureExplanationCard({ explanation, onInspect, onFocusReplay }: FailureExplanationCardProps) {
  return (
    <button
      type="button"
      className="diagnosis-overview-card"
      onClick={() => {
        onInspect(explanation.failure_event_id)
        onFocusReplay(explanation.next_inspection_event_id)
      }}
    >
      <div className="diagnosis-head">
        <span>{explanation.failure_mode.replaceAll('_', ' ')}</span>
        <strong>{explanation.confidence.toFixed(2)}</strong>
      </div>
      <h3>{explanation.failure_headline}</h3>
      <p>{explanation.symptom}</p>
      <small>{explanation.likely_cause}</small>
    </button>
  )
}
