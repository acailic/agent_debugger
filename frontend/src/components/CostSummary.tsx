import { useEffect, useState } from 'react'
import { getCostSummary } from '../api/client'
import type { CostSummary as CostSummaryType } from '../types'

export default function CostSummary() {
  const [data, setData] = useState<CostSummaryType | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCostSummary()
      .then(setData)
      .catch(err => setError(err.message))
  }, [])

  if (error) return <div className="cost-summary-error">Failed to load cost data</div>
  if (!data) return <div className="cost-summary-loading">Loading cost data...</div>

  return (
    <div className="cost-summary">
      <h3>Cost Overview</h3>
      <div className="cost-summary-grid">
        <div className="cost-stat">
          <span className="cost-label">Total Spend</span>
          <span className="cost-value">${data.total_cost_usd.toFixed(4)}</span>
        </div>
        <div className="cost-stat">
          <span className="cost-label">Sessions</span>
          <span className="cost-value">{data.session_count.toLocaleString()}</span>
        </div>
        <div className="cost-stat">
          <span className="cost-label">Avg / Session</span>
          <span className="cost-value">${data.avg_cost_per_session.toFixed(4)}</span>
        </div>
      </div>
      {data.by_framework.length > 0 && (
        <div className="cost-by-framework">
          <h4>By Framework</h4>
          <table>
            <thead>
              <tr>
                <th>Framework</th>
                <th>Sessions</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.by_framework.map(fw => (
                <tr key={fw.framework}>
                  <td>{fw.framework}</td>
                  <td>{fw.session_count}</td>
                  <td>${fw.total_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
