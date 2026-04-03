import { useState, memo, useCallback, useMemo } from 'react'
import type { TraceEvent, Highlight, EventType } from '../types'
import { formatEventHeadline } from '../utils/formatting'
import { BLOCKED_EVENT_TYPES } from '../utils/latency'

interface TraceTimelineProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  highlightEventIds?: Set<string>
  /** Map of event_id to Highlight for displaying reasons */
  highlightsMap?: Map<string, Highlight>
  showBlockedActions?: boolean
  onToggleShowBlockedActions?: (show: boolean) => void
}

const EVENT_TYPE_FILTERS: { label: string; types: EventType[]; color: string }[] = [
  { label: 'All', types: [], color: '#6366f1' },
  { label: 'LLM', types: ['llm_request', 'llm_response'], color: '#8b5cf6' },
  { label: 'Tools', types: ['tool_call', 'tool_result'], color: '#06b6d4' },
  { label: 'Decisions', types: ['decision'], color: '#f59e0b' },
  { label: 'Errors', types: ['error'], color: '#ef4444' },
  { label: 'Agents', types: ['agent_start', 'agent_end', 'agent_turn'], color: '#10b981' },
]

export function TraceTimeline({
  events,
  selectedEventId,
  onSelectEvent,
  highlightEventIds,
  highlightsMap,
  showBlockedActions,
  onToggleShowBlockedActions,
}: TraceTimelineProps) {
  const [internalShowBlockedActions, setInternalShowBlockedActions] = useState(false)
  const [activeFilter, setActiveFilter] = useState<typeof EVENT_TYPE_FILTERS[number]>(EVENT_TYPE_FILTERS[0])
  const blockedActionsVisible = showBlockedActions ?? internalShowBlockedActions

  const handleBlockedActionsToggle = useCallback((nextValue: boolean) => {
    setInternalShowBlockedActions(nextValue)
    onToggleShowBlockedActions?.(nextValue)
  }, [onToggleShowBlockedActions])

  const filteredEvents = useMemo(() => events.filter((event) => {
    // Apply type filter
    if (activeFilter.types.length > 0 && !activeFilter.types.includes(event.event_type)) {
      return false
    }
    // Apply blocked actions filter
    if (!blockedActionsVisible) {
      return !BLOCKED_EVENT_TYPES.includes(event.event_type)
    }
    return true
  }), [events, activeFilter.types, blockedActionsVisible])

  // Compute latency statistics for color-coding
  const latencyStats = useMemo(() => {
    const durations = filteredEvents.map(e => e.duration_ms).filter((d): d is number => d !== undefined)
    const maxDuration = durations.length > 0 ? Math.max(...durations) : 0
    const avgDuration = durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : 0
    return { maxDuration, avgDuration }
  }, [filteredEvents])

  const getLatencyColor = useCallback((durationMs: number | undefined): string => {
    if (durationMs === undefined) return 'transparent'
    if (durationMs > latencyStats.avgDuration * 2) return '#ef4444' // Red for very slow
    if (durationMs > latencyStats.avgDuration * 1.5) return '#f59e0b' // Orange for slow
    if (durationMs > latencyStats.avgDuration) return '#fbbf24' // Yellow for above average
    return '#10b981' // Green for fast
  }, [latencyStats.avgDuration])

  const getLatencyWidth = useCallback((durationMs: number | undefined): number => {
    if (durationMs === undefined || latencyStats.maxDuration === 0) return 0
    return Math.min(Math.max((durationMs / latencyStats.maxDuration) * 100, 5), 100)
  }, [latencyStats.maxDuration])

  const isBlockedEvent = useCallback((event: TraceEvent): boolean => {
    return BLOCKED_EVENT_TYPES.includes(event.event_type)
  }, [])

  // Memoize filter counts to avoid recalculation on every render
  const filterCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    EVENT_TYPE_FILTERS.forEach((filter) => {
      if (filter.types.length > 0) {
        counts[filter.label] = events.filter(e => filter.types.includes(e.event_type as EventType)).length
      }
    })
    return counts
  }, [events])

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
              checked={blockedActionsVisible}
              onChange={(e) => handleBlockedActionsToggle(e.target.checked)}
              className="toggle-checkbox"
            />
            <span className="toggle-label">Show Blocked Actions</span>
          </label>
        </div>
      </div>

      {/* Event Type Filter Chips */}
      <div className="event-filters">
        {EVENT_TYPE_FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            className={`filter-chip ${activeFilter.label === filter.label ? 'active' : ''}`}
            onClick={() => setActiveFilter(filter)}
            style={{ borderColor: activeFilter.label === filter.label ? filter.color : undefined }}
            aria-pressed={activeFilter.label === filter.label}
          >
            {filter.label}
            {filter.types.length > 0 && (
              <span className="filter-count">
                {filterCounts[filter.label] ?? 0}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="timeline-events">
        {filteredEvents.length === 0 ? (
          <div className="timeline-empty">
            <p>
              {blockedActionsVisible && activeFilter.types.length === 0
                ? 'No events captured in this trace.'
                : activeFilter.types.length > 0
                  ? `No ${activeFilter.label.toLowerCase()} events found.`
                  : 'No events matching current filters.'}
            </p>
          </div>
        ) : (
          filteredEvents.map((event) => {
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
                  {event.duration_ms !== undefined && (
                    <span
                      className="latency-bar"
                      title={`Duration: ${event.duration_ms.toFixed(0)}ms`}
                      style={{
                        backgroundColor: getLatencyColor(event.duration_ms),
                        width: `${getLatencyWidth(event.duration_ms)}%`
                      }}
                      aria-valuemin={0}
                      aria-valuemax={latencyStats.maxDuration}
                      aria-valuenow={event.duration_ms}
                      role="progressbar"
                    >
                      <span className="latency-text" aria-hidden="true">{event.duration_ms.toFixed(0)}ms</span>
                    </span>
                  )}
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
          })
        )}
      </div>
    </div>
  )
}

// Custom comparison to avoid re-renders when events array reference changes but content is same
function arePropsEqual(
  prevProps: Readonly<TraceTimelineProps>,
  nextProps: Readonly<TraceTimelineProps>
): boolean {
  return (
    prevProps.selectedEventId === nextProps.selectedEventId &&
    prevProps.events === nextProps.events &&
    prevProps.highlightEventIds === nextProps.highlightEventIds &&
    prevProps.highlightsMap === nextProps.highlightsMap &&
    prevProps.showBlockedActions === nextProps.showBlockedActions
  )
}

export const TraceTimelineMemo = memo(TraceTimeline, arePropsEqual)
