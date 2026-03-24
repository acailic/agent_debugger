import type { PolicyShift } from '../types'

interface PolicyDiffViewProps {
  policyShifts: PolicyShift[]
  onSelectEvent: (eventId: string) => void
}

function formatMagnitude(magnitude: number): { label: string; className: string } {
  if (magnitude >= 0.8) return { label: 'Major', className: 'magnitude-major' }
  if (magnitude >= 0.5) return { label: 'Moderate', className: 'magnitude-moderate' }
  if (magnitude >= 0.3) return { label: 'Minor', className: 'magnitude-minor' }
  return { label: 'Subtle', className: 'magnitude-subtle' }
}

export function PolicyDiffView({ policyShifts, onSelectEvent }: PolicyDiffViewProps) {
  if (policyShifts.length === 0) {
    return (
      <section className="panel policy-diff-panel">
        <div className="panel-head">
          <p className="eyebrow">Policy Changes</p>
          <h2>Parameter shifts</h2>
        </div>
        <p className="empty-message">No policy shifts detected in this session.</p>
      </section>
    )
  }

  return (
    <section className="panel policy-diff-panel">
      <div className="panel-head">
        <p className="eyebrow">Policy Changes</p>
        <h2>Parameter shifts ({policyShifts.length})</h2>
      </div>

      <div className="policy-shift-list">
        {policyShifts.map((shift, index) => {
          const magnitudeInfo = formatMagnitude(shift.shift_magnitude)
          return (
            <button
              key={`${shift.event_id}-${index}`}
              type="button"
              className={`policy-shift-card ${magnitudeInfo.className}`}
              onClick={() => onSelectEvent(shift.event_id)}
              aria-label={`Policy change at turn ${shift.turn_index}: ${magnitudeInfo.label} shift from ${shift.previous_template || 'initial'} to ${shift.new_template}`}
            >
              <div className="shift-header">
                <span className="shift-turn">Turn {shift.turn_index}</span>
                <span className={`shift-magnitude ${magnitudeInfo.className}`}>
                  {magnitudeInfo.label}
                </span>
              </div>
              <div className="shift-templates">
                {shift.previous_template ? (
                  <div className="template-change">
                    <span className="template-previous">{shift.previous_template}</span>
                    <span className="template-arrow" aria-hidden="true">→</span>
                    <span className="template-new">{shift.new_template}</span>
                  </div>
                ) : (
                  <div className="template-initial">
                    <span className="template-new">{shift.new_template}</span>
                    <span className="template-badge">Initial</span>
                  </div>
                )}
              </div>
              <div className="shift-score">
                <span className="metric-label">Magnitude</span>
                <div className="magnitude-bar-container">
                  <div
                    className="magnitude-bar-fill"
                    style={{ width: `${shift.shift_magnitude * 100}%` }}
                    role="progressbar"
                    aria-valuenow={shift.shift_magnitude}
                    aria-label={`${(shift.shift_magnitude * 100).toFixed(0)}% magnitude`}
                  />
                </div>
                <strong>{shift.shift_magnitude.toFixed(2)}</strong>
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}
