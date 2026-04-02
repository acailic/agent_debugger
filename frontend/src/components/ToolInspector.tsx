import type { TraceEvent } from '../types'
import { formatDuration, formatTime } from '../utils/formatting'

interface ToolInspectorProps {
  event: TraceEvent | null
}

/**
 * Highlights JSON syntax for display.
 *
 * SECURITY: This function uses dangerouslySetInnerHTML, which is safe here because:
 * 1. All data comes from SDK-generated trace events (tool arguments and results)
 * 2. No user-controlled content is rendered without HTML escaping
 * 3. The function escapes special characters (<, >, &) before adding syntax highlighting spans
 * 4. Only trusted SDK trace data is processed, not arbitrary user input
 */
function highlightJSON(obj: unknown): string {
  const json = JSON.stringify(obj ?? null, null, 2) ?? 'null'
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:')
    .replace(/: "([^"]*)"/g, ': <span class="json-string">"$1"</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="json-number">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="json-bool">$1</span>')
}

export function ToolInspector({ event }: ToolInspectorProps) {
  if (!event) {
    return (
      <div className="tool-inspector empty">
        <span className="empty-icon">🔍</span>
        <p>Select a tool call to inspect</p>
      </div>
    )
  }

  const isToolCall = event.event_type === 'tool_call'
  const isToolResult = event.event_type === 'tool_result'
  const toolName = event.tool_name ?? 'Unknown'
  const toolId = event.id
  const arguments_: Record<string, unknown> = (event.arguments as Record<string, unknown> | undefined) ?? {}
  const hasArguments = Object.keys(arguments_).length > 0
  const isError = !!event.error
  const duration = event.duration_ms ?? null
  const timestamp = event.timestamp
  const result = event.result

  // Show loading state for tool calls waiting for results
  if (isToolCall && !isToolResult && !isError) {
    return (
      <div className="tool-inspector loading">
        <div className="tool-header">
          <div className="tool-title">
            <span className="tool-icon">🔧</span>
            <h3>{toolName}</h3>
          </div>
        </div>
        <div className="tool-loading-state">
          <span className="loading-icon">⏳</span>
          <p>Waiting for result...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`tool-inspector ${isError ? 'error-state' : ''}`}>
      <div className="tool-header">
        <div className="tool-title">
          <span className="tool-icon">🔧</span>
          <h3>{toolName}</h3>
        </div>
        <div className="tool-meta">
          {isError ? (
            <span className="status-badge error">✗</span>
          ) : isToolResult ? (
            <span className="status-badge success">✓</span>
          ) : null}
          {duration !== null && (
            <span className="duration">{formatDuration(duration)}</span>
          )}
        </div>
      </div>

      <div className="tool-id-section">
        <span className="label">ID:</span>
        <code className="tool-id">{toolId}</code>
        {timestamp && (
          <span className="timestamp">{formatTime(timestamp)}</span>
        )}
      </div>

      {hasArguments && (
        <div className="tool-section">
          <h4>Arguments</h4>
          <pre
            className="code-block json"
            dangerouslySetInnerHTML={{ __html: highlightJSON(arguments_) }}
          />
        </div>
      )}

      {isToolResult && (
        <div className={`tool-section ${isError ? 'error' : ''}`}>
          <h4>{isError ? 'Error' : 'Result'}</h4>
          {isError ? (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              <span>{event.error}</span>
            </div>
          ) : (
            <pre
              className="code-block json"
              dangerouslySetInnerHTML={{ __html: highlightJSON(result) }}
            />
          )}
        </div>
      )}
    </div>
  )
}
