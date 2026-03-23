import type { ReactNode } from 'react'
import type { TraceEvent } from '../types'

interface ToolInspectorProps {
  event: TraceEvent | null
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

/**
 * Safely renders JSON as highlighted React elements without using innerHTML.
 * This avoids XSS vulnerabilities associated with dangerouslySetInnerHTML.
 */
function JsonHighlight({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  if (value === null) {
    return <span className="json-bool">null</span>
  }

  if (value === undefined) {
    return <span className="json-bool">undefined</span>
  }

  if (typeof value === 'boolean') {
    return <span className="json-bool">{value.toString()}</span>
  }

  if (typeof value === 'number') {
    return <span className="json-number">{value}</span>
  }

  if (typeof value === 'string') {
    // Escape the string for safe display but render as text, not HTML
    return <span className="json-string">"{value}"</span>
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return '[]'
    }
    const indent = '  '.repeat(depth)
    const childIndent = '  '.repeat(depth + 1)
    return (
      <>
        {'[\n'}
        {value.map((item, index) => (
          <span key={index}>
            {childIndent}
            <JsonHighlight value={item} depth={depth + 1} />
            {index < value.length - 1 ? ',' : ''}
            {'\n'}
          </span>
        ))}
        {indent}]
      </>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) {
      return '{}'
    }
    const indent = '  '.repeat(depth)
    const childIndent = '  '.repeat(depth + 1)
    return (
      <>
        {'{\n'}
        {entries.map(([key, val], index) => (
          <span key={key}>
            {childIndent}
            <span className="json-key">"{key}"</span>: <JsonHighlight value={val} depth={depth + 1} />
            {index < entries.length - 1 ? ',' : ''}
            {'\n'}
          </span>
        ))}
        {indent}{'}'}
      </>
    )
  }

  // Fallback for any other types
  return String(value)
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
  const arguments_ = event.arguments ?? {}
  const hasArguments = Object.keys(arguments_).length > 0
  const isError = !!event.error
  const duration = event.duration_ms ?? null
  const timestamp = event.timestamp

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
          <span className="timestamp">{formatTimestamp(timestamp)}</span>
        )}
      </div>

      {hasArguments && (
        <div className="tool-section">
          <h4>Arguments</h4>
          <pre className="code-block json">
            <JsonHighlight value={arguments_} />
          </pre>
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
            <pre className="code-block json">
              <JsonHighlight value={event.result} />
            </pre>
          )}
        </div>
      )}

      {isToolCall && (
        <div className="tool-section pending">
          <span className="pending-icon">⏳</span>
          <span>Waiting for result...</span>
        </div>
      )}
    </div>
  )
}
