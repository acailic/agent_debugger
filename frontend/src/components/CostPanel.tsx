import { useEffect, useState } from 'react'
import { getSessionCost } from '../api/client'
import type { SessionCost } from '../types'

interface CostPanelProps {
  sessionId: string
}

export default function CostPanel({ sessionId }: CostPanelProps) {
  const [data, setData] = useState<SessionCost | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    getSessionCost(sessionId)
      .then(setData)
      .catch(err => setError(err.message))
  }, [sessionId])

  if (error) return null
  if (!data) return null

  return (
    <div className="cost-panel">
      <h4>Session Cost</h4>
      <div className="cost-details">
        <div className="cost-row">
          <span>Total Cost</span>
          <span className="cost-amount">${data.total_cost_usd.toFixed(6)}</span>
        </div>
        <div className="cost-row">
          <span>Tokens</span>
          <span>{data.total_tokens.toLocaleString()}</span>
        </div>
        <div className="cost-row">
          <span>LLM Calls</span>
          <span>{data.llm_calls}</span>
        </div>
        <div className="cost-row">
          <span>Tool Calls</span>
          <span>{data.tool_calls}</span>
        </div>
      </div>
    </div>
  )
}
