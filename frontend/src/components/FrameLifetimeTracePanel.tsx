import type { TraceEvent } from '../types'

interface FrameLifetimeTracePanelProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
}

interface FrameLifetime {
  event_id: string
  function_name: string
  entry_time: string
  exit_time: string | null
  duration_ms: number | null
  parent_frame_id: string | null
  depth: number
  token_usage: number
  children: FrameLifetime[]
  is_active: boolean
}

/**
 * Parse events into frame lifetime tree structure
 * This enables function-level tracing for the Frame Lifetime Trace feature
 */
function buildFrameLifetimes(events: TraceEvent[]): FrameLifetime[] {
  const frameMap = new Map<string, FrameLifetime>()
  const rootFrames: FrameLifetime[] = []

  // Sort events by timestamp to ensure proper ordering
  const sortedEvents = [...events].sort((a, b) =>
    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  for (const event of sortedEvents) {
    // Check if this is a function entry/exit event
    const functionName = event.data?.function_name as string | undefined
    const isEntry = event.data?.phase === 'entry'
    const isExit = event.data?.phase === 'exit'

    if (!functionName || (!isEntry && !isExit)) {
      continue
    }

    if (isEntry) {
      const frame: FrameLifetime = {
        event_id: event.id,
        function_name: functionName,
        entry_time: event.timestamp,
        exit_time: null,
        duration_ms: null,
        parent_frame_id: event.parent_id,
        depth: 0,
        token_usage: (event.usage?.input_tokens || 0) + (event.usage?.output_tokens || 0),
        children: [],
        is_active: true,
      }

      frameMap.set(event.id, frame)

      // Find parent frame
      if (event.parent_id && frameMap.has(event.parent_id)) {
        const parentFrame = frameMap.get(event.parent_id)!
        parentFrame.children.push(frame)
        frame.depth = parentFrame.depth + 1
      } else {
        rootFrames.push(frame)
      }
    } else if (isExit) {
      // Find corresponding entry frame and close it
      const entryFrame = frameMap.get(event.parent_id || '')
      if (entryFrame && entryFrame.is_active) {
        entryFrame.exit_time = event.timestamp
        entryFrame.is_active = false
        entryFrame.duration_ms = new Date(event.timestamp).getTime() -
                               new Date(entryFrame.entry_time).getTime()
      }
    }
  }

  return rootFrames
}

function collectAllFrames(frames: FrameLifetime[]): FrameLifetime[] {
  const result: FrameLifetime[] = []

  function collect(frame: FrameLifetime) {
    result.push(frame)
    for (const child of frame.children) {
      collect(child)
    }
  }

  for (const frame of frames) {
    collect(frame)
  }

  return result
}

function getDurationColor(durationMs: number | null): string {
  if (!durationMs) return 'var(--muted)'
  if (durationMs > 5000) return 'var(--danger)'
  if (durationMs > 2000) return 'var(--warning)'
  return 'var(--olive)'
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function FrameNode({
  frame,
  level,
  selectedEventId,
  onEventSelect
}: {
  frame: FrameLifetime
  level: number
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
}) {
  const durationColor = getDurationColor(frame.duration_ms)
  const isSelected = selectedEventId === frame.event_id
  const hasChildren = frame.children.length > 0

  return (
    <div className="frame-node" style={{ marginLeft: `${level * 20}px` }}>
      <button
        type="button"
        className={`frame-row ${isSelected ? 'selected' : ''} ${frame.is_active ? 'active' : 'completed'}`}
        onClick={() => onEventSelect(frame.event_id)}
        aria-label={`Function: ${frame.function_name}, duration: ${frame.duration_ms ? formatDuration(frame.duration_ms) : 'active'}`}
      >
        <span className="frame-expand">
          {hasChildren ? (frame.is_active ? '▶' : '▼') : '•'}
        </span>
        <span className="frame-name">{frame.function_name}</span>
        <span className="frame-duration" style={{ color: durationColor }}>
          {frame.duration_ms ? formatDuration(frame.duration_ms) : 'active'}
        </span>
        <span className="frame-tokens">{frame.token_usage} tokens</span>
        <span className={`frame-status ${frame.is_active ? 'active' : 'completed'}`}>
          {frame.is_active ? '⏳' : '✓'}
        </span>
      </button>

      {hasChildren && (
        <div className="frame-children">
          {frame.children.map(child => (
            <FrameNode
              key={child.event_id}
              frame={child}
              level={level + 1}
              selectedEventId={selectedEventId}
              onEventSelect={onEventSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FrameLifetimeTracePanel({
  events,
  selectedEventId,
  onEventSelect,
}: FrameLifetimeTracePanelProps) {

  const frameLifetimes = buildFrameLifetimes(events)
  const allFrames = collectAllFrames(frameLifetimes)

  // Group frames by function name for summary
  const functionGroups = new Map<string, FrameLifetime[]>()
  for (const frame of allFrames) {
    if (!functionGroups.has(frame.function_name)) {
      functionGroups.set(frame.function_name, [])
    }
    functionGroups.get(frame.function_name)!.push(frame)
  }

  if (frameLifetimes.length === 0) {
    return (
      <section className="panel frame-lifetime-panel">
        <div className="panel-head">
          <p className="eyebrow">Function Tracing</p>
          <h2>Frame Lifetime Trace</h2>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <h3>No function traces available</h3>
          <p>Frame lifetime tracing provides function-level execution tracking with duration analysis and token usage.</p>
          <small>Function traces will appear here when instrumented code is executed</small>
        </div>
      </section>
    )
  }

  return (
    <section className="panel frame-lifetime-panel">
      <div className="panel-head">
        <p className="eyebrow">Function Tracing</p>
        <h2>Frame Lifetime Trace ({allFrames.length})</h2>
      </div>

      <div className="frame-lifetime-content">
        <div className="frame-tree">
          <h3>Function Call Tree</h3>
          <div className="frame-tree-content">
            {frameLifetimes.map(frame => (
              <FrameNode
                key={frame.event_id}
                frame={frame}
                level={0}
                selectedEventId={selectedEventId}
                onEventSelect={onEventSelect}
              />
            ))}
          </div>
        </div>

        <div className="frame-summary">
          <h3>Summary</h3>
          <div className="summary-stats">
            <div className="stat-item">
              <span className="stat-label">Total Functions</span>
              <strong>{functionGroups.size}</strong>
            </div>
            <div className="stat-item">
              <span className="stat-label">Active Functions</span>
              <strong>{allFrames.filter(f => f.is_active).length}</strong>
            </div>
            <div className="stat-item">
              <span className="stat-label">Total Tokens</span>
              <strong>{allFrames.reduce((sum, f) => sum + f.token_usage, 0)}</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}