import { useEffect, useCallback, useRef } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import type { TraceEvent } from '../types'

interface SessionReplayProps {
  events: TraceEvent[]
  currentIndex: number
  isPlaying: boolean
  onPlay: () => void
  onPause: () => void
  onStepForward: () => void
  onStepBackward: () => void
  onSeek: (index: number) => void
  speed: number
  onSpeedChange: (speed: number) => void
  onJumpToPrevCheckpoint?: () => void
  onJumpToNextCheckpoint?: () => void
}

const SPEED_OPTIONS = [0.5, 1, 2, 5]

const HIGH_IMPORTANCE_TYPES = ['decision', 'error', 'tool_call']

function isCheckpoint(event: TraceEvent): boolean {
  return event.event_type === 'checkpoint'
}

function getEventLabel(event: TraceEvent): string {
  switch (event.event_type) {
    case 'agent_start':
      return 'Agent Start'
    case 'agent_end':
      return 'Agent End'
    case 'llm_request':
      return 'LLM Request'
    case 'llm_response':
      return 'LLM Response'
    case 'tool_call':
      return `Tool: ${event.tool_name ?? event.name}`
    case 'tool_result':
      return `Result: ${event.tool_name ?? event.name}`
    case 'decision':
      return `Decision: ${event.chosen_action ?? event.name}`
    case 'error':
      return `Error: ${event.error_type ?? event.name}`
    case 'checkpoint':
      return `Checkpoint ${event.data.sequence ?? ''}`.trim()
    case 'safety_check':
      return `Safety: ${event.policy_name ?? event.name}`
    case 'refusal':
      return `Refusal: ${event.policy_name ?? event.name}`
    case 'policy_violation':
      return `Policy: ${event.violation_type ?? event.name}`
    case 'prompt_policy':
      return `Prompt Policy: ${event.template_id ?? event.name}`
    case 'agent_turn':
      return `Turn ${event.turn_index ?? ''}: ${event.speaker ?? event.agent_id ?? event.name}`.trim()
    case 'behavior_alert':
      return `Alert: ${event.alert_type ?? event.name}`
    default:
      return event.event_type
  }
}

export function SessionReplay({
  events,
  currentIndex,
  isPlaying,
  onPlay,
  onPause,
  onStepForward,
  onStepBackward,
  onSeek,
  speed,
  onSpeedChange,
  onJumpToPrevCheckpoint,
  onJumpToNextCheckpoint,
}: SessionReplayProps) {
  const sliderRef = useRef<HTMLInputElement>(null)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const totalEvents = events.length
  const canStepBack = currentIndex > 0
  const canStepForward = currentIndex < totalEvents - 1

  // Checkpoint events computed first for navigation
  const checkpointEvents = events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => isCheckpoint(event))

  // Checkpoint navigation
  const prevCheckpointIndex = checkpointEvents.filter(({ index }) => index < currentIndex).pop()?.index ?? null
  const nextCheckpointIndex = checkpointEvents.find(({ index }) => index > currentIndex)?.index ?? null
  const canJumpToPrevCheckpoint = prevCheckpointIndex !== null
  const canJumpToNextCheckpoint = nextCheckpointIndex !== null

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

  const progressPercent = totalEvents > 1 ? (currentIndex / (totalEvents - 1)) * 100 : 0

  return (
    <div className="session-replay">
      <div className="replay-controls">
        <button
          className="replay-btn jump-prev-checkpoint"
          onClick={() => onJumpToPrevCheckpoint?.()}
          disabled={!canJumpToPrevCheckpoint}
          title="Jump to previous checkpoint"
          aria-label="Jump to previous checkpoint"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
            <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>

        <button
          className="replay-btn step-back-single"
          onClick={onStepBackward}
          disabled={!canStepBack}
          title="Previous event (Left Arrow)"
          aria-label="Previous event"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M15.41 16.59L10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z" />
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
          title="Next event (Right Arrow)"
          aria-label="Next event"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z" />
          </svg>
        </button>

        <button
          className="replay-btn jump-next-checkpoint"
          onClick={() => onJumpToNextCheckpoint?.()}
          disabled={!canJumpToNextCheckpoint}
          title="Jump to next checkpoint"
          aria-label="Jump to next checkpoint"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
            <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>

        <div className="timeline-container">
          <div className="timeline-markers">
            {checkpointEvents.map(({ event, index }) => {
              const markerPercent = totalEvents > 1 ? (index / (totalEvents - 1)) * 100 : 0
              const isHighImportance = HIGH_IMPORTANCE_TYPES.includes(event.event_type)
              return (
                <div
                  key={event.id}
                  className={`timeline-marker ${event.event_type} ${isHighImportance ? 'high-importance' : ''}`}
                  style={{ left: `${markerPercent}%` }}
                  title={getEventLabel(event)}
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
      </div>
    </div>
  )
}
