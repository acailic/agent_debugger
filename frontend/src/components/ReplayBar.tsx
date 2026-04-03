import { useSessionStore } from '../stores/sessionStore'
import type { ReplayMode } from '../types'
import './ReplayBar.css'

interface ReplayBarProps {
  disabled?: boolean
}

const BREAKPOINT_PRESETS = [
  {
    id: 'errors',
    label: 'Errors',
    config: {
      breakpointEventTypes: 'error,refusal,policy_violation',
      breakpointToolNames: '',
      breakpointConfidenceBelow: '',
      breakpointSafetyOutcomes: '',
      stopAtBreakpoint: true,
    },
  },
  {
    id: 'low-confidence',
    label: 'Low confidence',
    config: {
      breakpointEventTypes: '',
      breakpointToolNames: '',
      breakpointConfidenceBelow: '0.45',
      breakpointSafetyOutcomes: '',
      stopAtBreakpoint: true,
    },
  },
  {
    id: 'safety',
    label: 'Safety',
    config: {
      breakpointEventTypes: '',
      breakpointToolNames: '',
      breakpointConfidenceBelow: '',
      breakpointSafetyOutcomes: 'warn,block',
      stopAtBreakpoint: true,
    },
  },
  {
    id: 'tools',
    label: 'Tools',
    config: {
      breakpointEventTypes: 'tool_call,tool_result',
      breakpointToolNames: '',
      breakpointConfidenceBelow: '',
      breakpointSafetyOutcomes: '',
      stopAtBreakpoint: true,
    },
  },
] as const

export function ReplayBar({ disabled = false }: ReplayBarProps) {
  const {
    replayMode,
    collapseThreshold,
    breakpointEventTypes,
    breakpointToolNames,
    breakpointConfidenceBelow,
    breakpointSafetyOutcomes,
    stopAtBreakpoint,
    setReplayMode,
    setCollapseThreshold,
    setBreakpointEventTypes,
    setBreakpointToolNames,
    setBreakpointConfidenceBelow,
    setBreakpointSafetyOutcomes,
    setStopAtBreakpoint,
  } = useSessionStore()

  const applyPreset = (preset: (typeof BREAKPOINT_PRESETS)[number]['config']) => {
    setBreakpointEventTypes(preset.breakpointEventTypes)
    setBreakpointToolNames(preset.breakpointToolNames)
    setBreakpointConfidenceBelow(preset.breakpointConfidenceBelow)
    setBreakpointSafetyOutcomes(preset.breakpointSafetyOutcomes)
    setStopAtBreakpoint(preset.stopAtBreakpoint)
  }

  const isPresetActive = (preset: (typeof BREAKPOINT_PRESETS)[number]['config']) =>
    breakpointEventTypes === preset.breakpointEventTypes
    && breakpointToolNames === preset.breakpointToolNames
    && breakpointConfidenceBelow === preset.breakpointConfidenceBelow
    && breakpointSafetyOutcomes === preset.breakpointSafetyOutcomes
    && stopAtBreakpoint === preset.stopAtBreakpoint

  return (
    <div className="replay-bar" style={disabled ? { opacity: 0.3, pointerEvents: 'none' as const } : undefined}>
      <div className="mode-switches">
        {(['full', 'focus', 'failure', 'highlights'] as ReplayMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            className={replayMode === mode ? 'active' : ''}
            onClick={() => setReplayMode(mode)}
          >
            {mode}
          </button>
        ))}
        {replayMode === 'highlights' && (
          <div className="threshold-presets">
            {([
              { label: 'Critical', value: 0.7 },
              { label: 'Standard', value: 0.35 },
              { label: 'Show most', value: 0.1 },
            ] as const).map(({ label, value }) => (
              <button
                key={value}
                type="button"
                className={`threshold-preset${collapseThreshold === value ? ' active' : ''}`}
                onClick={() => setCollapseThreshold(value)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="breakpoint-presets" aria-label="Breakpoint presets">
        {BREAKPOINT_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`breakpoint-preset${isPresetActive(preset.config) ? ' active' : ''}`}
            onClick={() => applyPreset(preset.config)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="breakpoint-bar">
        <label htmlFor="breakpoint-events">
          Event breakpoints
          <input
            id="breakpoint-events"
            value={breakpointEventTypes}
            onChange={(event) => setBreakpointEventTypes(event.target.value)}
          />
        </label>
        <label htmlFor="breakpoint-tools">
          Tool breakpoints
          <input
            id="breakpoint-tools"
            value={breakpointToolNames}
            onChange={(event) => setBreakpointToolNames(event.target.value)}
          />
        </label>
        <label htmlFor="breakpoint-confidence">
          Confidence floor
          <input
            id="breakpoint-confidence"
            value={breakpointConfidenceBelow}
            onChange={(event) => setBreakpointConfidenceBelow(event.target.value)}
          />
        </label>
        <label htmlFor="breakpoint-safety">
          Safety outcomes
          <input
            id="breakpoint-safety"
            value={breakpointSafetyOutcomes}
            onChange={(event) => setBreakpointSafetyOutcomes(event.target.value)}
          />
        </label>
        <label className="checkbox-label" htmlFor="stop-at-breakpoint">
          <input
            id="stop-at-breakpoint"
            type="checkbox"
            checked={stopAtBreakpoint}
            onChange={(event) => setStopAtBreakpoint(event.target.checked)}
          />
          Stop at breakpoint
        </label>
      </div>
    </div>
  )
}
