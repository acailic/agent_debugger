import type { TraceEvent } from '../types'

interface LLMViewerProps {
  request: TraceEvent | null
  response: TraceEvent | null
}

export function LLMViewer({ request, response }: LLMViewerProps) {
  if (!request) {
    return <div className="llm-viewer empty">Select an LLM interaction to view</div>
  }

  return (
    <div className="llm-viewer">
      <div className="llm-header">
        <h3>LLM Interaction</h3>
        <span className="model-name">{request.model}</span>
      </div>

      <div className="llm-section">
        <h4>Request Messages</h4>
        <div className="messages">
          {(request.messages ?? []).map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <span className="role">{msg.role}</span>
              <pre className="content">{msg.content}</pre>
            </div>
          ))}
        </div>
      </div>

      {response && (
        <div className="llm-section">
          <h4>Response</h4>
          {response.content && (
            <pre className="content">{response.content}</pre>
          )}
          {response.tool_calls && response.tool_calls.length > 0 && (
            <div className="tool-calls">
              <h5>Tool Calls</h5>
              {response.tool_calls.map((tc) => (
                <div key={tc.id} className="tool-call">
                  <span className="name">{tc.name}</span>
                  <pre>{JSON.stringify(tc.arguments, null, 2)}</pre>
                </div>
              ))}
            </div>
          )}
          <div className="usage">
            <span>Input: {response.usage?.input_tokens ?? 0} tokens</span>
            <span>Output: {response.usage?.output_tokens ?? 0} tokens</span>
            <span>Cost: ${(response.cost_usd ?? 0).toFixed(4)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
