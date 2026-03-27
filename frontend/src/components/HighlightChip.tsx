import type { CollapsedSegment } from '../types'

interface HighlightChipProps {
  segment: CollapsedSegment
  children: React.ReactNode
  isExpanded?: boolean
  onToggle: () => void
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

export default function HighlightChip({
  segment,
  children,
  isExpanded = false,
  onToggle,
}: HighlightChipProps) {
  if (isExpanded) {
    return (
      <div className="highlight-chip highlight-chip-expanded">
        <div className="highlight-chip-meta">
          <strong>{segment.summary}</strong>
          <span>
            {segment.event_count} event{segment.event_count !== 1 ? 's' : ''}
          </span>
          {segment.total_duration_ms != null && (
            <span className="highlight-chip-duration">
              ~{formatDuration(segment.total_duration_ms)}
            </span>
          )}
        </div>
        <div className="highlight-chip-events">{children}</div>
        <button
          type="button"
          className="highlight-chip-toggle"
          onClick={onToggle}
        >
          ▴ Collapse
        </button>
      </div>
    )
  }

  return (
    <button
      type="button"
      className="highlight-chip"
      onClick={onToggle}
    >
      <div className="highlight-chip-meta">
        <strong>{segment.summary}</strong>
        <span>
          {segment.event_count} event{segment.event_count !== 1 ? 's' : ''}
        </span>
        {segment.total_duration_ms != null && (
          <span className="highlight-chip-duration">
            ~{formatDuration(segment.total_duration_ms)}
          </span>
        )}
      </div>
      <div className="highlight-chip-types">
        {segment.event_types.map((type) => (
          <span key={type} className="highlight-chip-type">
            {type.replaceAll('_', ' ')}
          </span>
        ))}
        <span className="highlight-chip-expand">▸</span>
      </div>
    </button>
  )
}
