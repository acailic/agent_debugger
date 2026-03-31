import { useEffect, useState } from 'react'
import { getSessionCost } from '../api/client'
import type { SessionCost } from '../types'

interface CostPanelProps {
  sessionId: string
}

export default function CostPanel({ sessionId }: CostPanelProps) {
  const [data, setData] = useState<SessionCost | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setLoading(false)
      return
    }

    let ignore = false
    async function fetchData() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSessionCost(sessionId)
        if (!ignore) {
          setData(response)
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load cost data')
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }
    void fetchData()
    return () => {
      ignore = true
    }
  }, [sessionId])

  if (loading) {
    return (
      <div className="cost-panel">
        <h4>Session Cost</h4>
        <div className="cost-loading-skeleton">
          <div className="skeleton-line" />
          <div className="skeleton-line" style={{ width: '60%' }} />
          <div className="skeleton-line" style={{ width: '40%' }} />
          <div className="skeleton-line" style={{ width: '80%' }} />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="cost-panel">
        <h4>Session Cost</h4>
        <p className="cost-error">Cost data unavailable</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="cost-panel">
        <h4>Session Cost</h4>
        <p className="cost-empty">No cost data available</p>
      </div>
    )
  }

  // Calculate cost efficiency hint
  const costPerToken = data.total_tokens > 0 ? data.total_cost_usd / data.total_tokens : 0
  const showEfficiencyHint = costPerToken > 0.00002 // Higher than typical efficient models

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
          <span>{data.llm_calls.toLocaleString()}</span>
        </div>
        <div className="cost-row">
          <span>Tool Calls</span>
          <span>{data.tool_calls.toLocaleString()}</span>
        </div>
      </div>
      {showEfficiencyHint && (
        <p className="cost-efficiency-hint">
          <small>Consider using a smaller model for this task type</small>
        </p>
      )}
    </div>
  )
}
