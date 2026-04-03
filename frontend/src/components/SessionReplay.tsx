import { useEffect, useCallback, useRef, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import type { TraceEvent } from '../types'
import { formatEventHeadline } from '../utils/formatting'
import { BLOCKED_EVENT_TYPES } from '../utils/latency'

interface SessionReplayProps {
  events: TraceEvent[]
  breakpointEventIds: string[]
  currentIndex: number
  isPlaying: boolean
  onPlay: () => void
  onPause: () => void
  onStepForward: () => void
  onStepBackward: () => void
  onSeek: (index: number) => void
  speed: number
  onSpeedChange: (speed: number) => void
  onToggleBreakpoint?: (eventId: string) => void
  showBlockedActions?: boolean
  onToggleShowBlockedActions?: (show: boolean) => void
}

const SPEED_OPTIONS = [0.5, 1, 2, 5]

const HIGH_IMPORTANCE_TYPES = ['decision', 'error', 'tool_call']

// Event types that can have breakpoints set on them
const BREAKPOINTABLE_TYPES = ['decision', 'error', 'tool_call', 'llm_request', 'llm_response', 'safety_check', 'refusal', 'policy_violation']

function isCheckpoint(event: TraceEvent): boolean {
  return event.event_type === 'checkpoint'
}

export function SessionReplay({
  events,
  breakpointEventIds,
  currentIndex,
  isPlaying,
  onPlay,
  onPause,
  onStepForward,
  onStepBackward,
  onSeek,
  speed,
  onSpeedChange,
  onToggleBreakpoint,
  showBlockedActions,
  onToggleShowBlockedActions,
}: SessionReplayProps) {
  const sliderRef = useRef<HTMLInputElement>(null)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [localBreakpoints, setLocalBreakpoints] = useState<Set<string>>(new Set(breakpointEventIds))
  const [showBreakpointPanel, setShowBreakpointPanel] = useState(false)
  const [internalShowBlockedActions, setInternalShowBlockedActions] = useState(false)

  const breakpointIdSet = localBreakpoints
  const blockedActionsVisible = showBlockedActions ?? internalShowBlockedActions
  const currentEvent = currentIndex >= 0 && currentIndex < events.length ? events[currentIndex] : null
  const blockedEventCount = events.filter((event) => BLOCKED_EVENT_TYPES.includes(event.event_type)).length

  const handleToggleBreakpoint = useCallback((eventId: string) => {
    setLocalBreakpoints((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(eventId)) {
        newSet.delete(eventId)
      } else {
        newSet.add(eventId)
      }
      return newSet
    })
    // Notify parent if callback provided
    if (onToggleBreakpoint) {
      onToggleBreakpoint(eventId)
    }
  }, [onToggleBreakpoint])

  const clearAllBreakpoints = useCallback(() => {
    setLocalBreakpoints(new Set())
  }, [])

  const handleBlockedActionsToggle = useCallback((nextValue: boolean) => {
    setInternalShowBlockedActions(nextValue)
    onToggleShowBlockedActions?.(nextValue)
  }, [onToggleShowBlockedActions])

  const isBreakpointed = useCallback((eventId: string) => {
    return breakpointIdSet.has(eventId)
  }, [breakpointIdSet])

  const canSetBreakpoint = useCallback((event: TraceEvent) => {
    return BREAKPOINTABLE_TYPES.includes(event.event_type)
  }, [])

  const isBlockedEvent = useCallback((event: TraceEvent) => {
    return BLOCKED_EVENT_TYPES.includes(event.event_type)
  }, [])

  const totalEvents = events.length
  const canStepBack = currentIndex > 0
  const canStepForward = currentIndex < totalEvents - 1

  const togglePlayPause = useCallback(() => {
    if (isPlaying) {
      onPause()
    } else {
      onPlay()
    }
  }, [isPlaying, onPlay, onPause])

  const handleSeek = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    onSeek(parseInt(e.target.value, 10))
  }, [onSeek])

  const handleSpeedChange = useCallback((e: ChangeEvent<HTMLSelectElement>) => {
    onSpeedChange(parseFloat(e.target.value))
  }, [onSpeedChange])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
      return
    }

    const currentSpeedIdx = SPEED_OPTIONS.indexOf(speed)

    switch (e.code) {
      case 'Space':
        e.preventDefault()
        togglePlayPause()
        break
      case 'ArrowLeft':
        e.preventDefault()
        if (canStepBack) onStepBackward()
        break
      case 'ArrowRight':
        e.preventDefault()
        if (canStepForward) onStepForward()
        break
      case 'ArrowUp':
        e.preventDefault()
        if (currentSpeedIdx < SPEED_OPTIONS.length - 1) {
          onSpeedChange(SPEED_OPTIONS[currentSpeedIdx + 1])
        }
        break
      case 'ArrowDown':
        e.preventDefault()
        if (currentSpeedIdx > 0) {
          onSpeedChange(SPEED_OPTIONS[currentSpeedIdx - 1])
        }
        break
    }
  }, [togglePlayPause, canStepBack, canStepForward, onStepBackward, onStepForward, speed, onSpeedChange])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  useEffect(() => {
    if (isPlaying) {
      const interval = 1000 / speed
      playIntervalRef.current = setInterval(() => {
        if (currentIndex < totalEvents - 1) {
          onStepForward()
        } else {
          onPause()
        }
      }, interval)
    } else {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
        playIntervalRef.current = null
      }
    }

    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
      }
    }
  }, [isPlaying, speed, currentIndex, totalEvents, onStepForward, onPause])

  const timelineMarkers = events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => (
      isCheckpoint(event)
      || breakpointIdSet.has(event.id)
      || HIGH_IMPORTANCE_TYPES.includes(event.event_type)
      || (blockedActionsVisible && isBlockedEvent(event))
    ))

  const progressPercent = totalEvents > 1 ? (currentIndex / (totalEvents - 1)) * 100 : 0

  return (
    <div className="session-replay">
      <div className="replay-controls">
        <button
          className="replay-btn step-back"
          onClick={onStepBackward}
          disabled={!canStepBack}
          title="Step backward (Left Arrow)"
          aria-label="Step backward"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
          </svg>
        </button>

        <button
          className="replay-btn step-back-single"
          onClick={onStepBackward}
          disabled={!canStepBack}
          title="Previous event"
          aria-label="Previous event"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
          </svg>
        </button>

        <button
          className="replay-btn play-pause"
          onClick={togglePlayPause}
          title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        <button
          className="replay-btn step-forward-single"
          onClick={onStepForward}
          disabled={!canStepForward}
          title="Next event"
          aria-label="Next event"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
          </svg>
        </button>

        <button
          className="replay-btn step-forward"
          onClick={onStepForward}
          disabled={!canStepForward}
          title="Step forward (Right Arrow)"
          aria-label="Step forward"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
          </svg>
        </button>

        <div className="timeline-container">
          <div className="timeline-markers">
            {timelineMarkers.map(({ event, index }) => {
              const markerPercent = totalEvents > 1 ? (index / (totalEvents - 1)) * 100 : 0
              const isHighImportance = HIGH_IMPORTANCE_TYPES.includes(event.event_type)
              const isBreakpointMarker = isBreakpointed(event.id)
              const isCurrentBreakpoint = index === currentIndex && isBreakpointMarker
              const isBlockedMarker = blockedActionsVisible && isBlockedEvent(event)
              return (
                <div
                  key={event.id}
                  className={`timeline-marker ${event.event_type} ${isHighImportance ? 'high-importance' : ''} ${isBreakpointMarker ? 'breakpoint' : ''} ${isCurrentBreakpoint ? 'current-breakpoint' : ''} ${isBlockedMarker ? 'blocked' : ''}`}
                  style={{ left: `${markerPercent}%` }}
                  title={formatEventHeadline(event)}
                  onClick={() => onSeek(index)}
                />
              )
            })}
          </div>
          <input
            ref={sliderRef}
            type="range"
            className="timeline-slider"
            min={0}
            max={Math.max(0, totalEvents - 1)}
            value={currentIndex}
            onChange={handleSeek}
            style={{ '--progress': `${progressPercent}%` } as CSSProperties}
          />
        </div>

        <span className="event-counter">
          {totalEvents > 0 ? currentIndex + 1 : 0} / {totalEvents}
        </span>

        <select
          className="speed-select"
          value={speed}
          onChange={handleSpeedChange}
          title="Playback speed (Up/Down Arrows)"
          aria-label="Playback speed"
        >
          {SPEED_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>

        <label className="blocked-actions-toggle replay-toggle">
          <input
            type="checkbox"
            checked={blockedActionsVisible}
            onChange={(e) => handleBlockedActionsToggle(e.target.checked)}
            className="toggle-checkbox"
          />
          <span className="toggle-label">Show Blocked Actions</span>
        </label>

        <button
          className={`replay-btn breakpoint-toggle ${localBreakpoints.size > 0 ? 'has-breakpoints' : ''}`}
          onClick={() => setShowBreakpointPanel((prev) => !prev)}
          title={`Breakpoints (${localBreakpoints.size})`}
          aria-label="Toggle breakpoint panel"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <circle cx="8" cy="12" r="3" />
            <circle cx="16" cy="12" r="3" />
          </svg>
          {localBreakpoints.size > 0 && (
            <span className="breakpoint-count">{localBreakpoints.size}</span>
          )}
        </button>
      </div>

      {blockedActionsVisible && blockedEventCount > 0 && (
        <div className="replay-summary replay-summary--inline">
          <span>Blocked events in scope: {blockedEventCount}</span>
        </div>
      )}

      {/* Breakpoint Panel */}
      {showBreakpointPanel && (
        <div className="breakpoint-panel">
          <div className="breakpoint-panel-header">
            <h4>Breakpoints</h4>
            <button
              className="breakpoint-clear-btn"
              onClick={clearAllBreakpoints}
              disabled={localBreakpoints.size === 0}
              title="Clear all breakpoints"
              aria-label="Clear all breakpoints"
            >
              Clear All
            </button>
          </div>
          <div className="breakpoint-list">
            {events.length === 0 ? (
              <div className="breakpoint-empty">No events available</div>
            ) : (
              events
                .filter((event) => canSetBreakpoint(event))
                .slice(0, 50) // Limit to first 50 breakpointable events for performance
                .map((event) => (
                  <div
                    key={event.id}
                    className={`breakpoint-item ${isBreakpointed(event.id) ? 'breakpoint-active' : ''}`}
                    onClick={() => handleToggleBreakpoint(event.id)}
                  >
                    <div className="breakpoint-indicator">
                      {isBreakpointed(event.id) && <div className="breakpoint-dot" />}
                    </div>
                    <div className="breakpoint-info">
                      <span className="breakpoint-type">{event.event_type}</span>
                      <span className="breakpoint-name">{formatEventHeadline(event)}</span>
                    </div>
                    <button
                      className="breakpoint-toggle-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleToggleBreakpoint(event.id)
                      }}
                      aria-label={isBreakpointed(event.id) ? 'Remove breakpoint' : 'Add breakpoint'}
                    >
                      {isBreakpointed(event.id) ? '−' : '+'}
                    </button>
                  </div>
                ))
            )}
          </div>
        </div>
      )}

      {/* Current Event Breakpoint Indicator */}
      {currentEvent && isBreakpointed(currentEvent.id) && (
        <div className="breakpoint-reached-indicator">
          <div className="breakpoint-reached-dot" />
          <span>Breakpoint: {formatEventHeadline(currentEvent)}</span>
        </div>
      )}

      {blockedActionsVisible && currentEvent && isBlockedEvent(currentEvent) && (
        <div className="breakpoint-reached-indicator blocked-event-indicator">
          <div className="breakpoint-reached-dot blocked-event-dot" />
          <span>
            Blocked action: {currentEvent.blocked_action ?? formatEventHeadline(currentEvent)}
            {currentEvent.reason ? ` (${currentEvent.reason})` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
