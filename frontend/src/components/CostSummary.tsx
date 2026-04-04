import { useEffect, useState } from 'react'
import { getCostSummary, getTopSessions } from '../api/client'

type TimeRange = '7d' | '30d' | '90d'

// These interfaces match the updated types being added by another worker
interface CostSummary {
  total_cost_usd: number
  session_count: number
  avg_cost_per_session: number
  by_framework: Array<{
    framework: string
    session_count: number
    total_cost_usd: number
    avg_cost_per_session: number
    total_tokens: number
  }>
  daily_cost: DailyCostItem[]
  period_start: string | null
  period_end: string | null
}

interface DailyCostItem {
  date: string
  session_count: number
  total_cost_usd: number
  total_tokens: number
  avg_cost_usd: number
}

interface TopSession {
  session_id: string
  agent_name: string
  framework: string
  total_cost_usd: number
  total_tokens: number
  llm_calls: number
  tool_calls: number
  started_at: string
  status: string
}

export default function CostSummary() {
  const [range, setRange] = useState<TimeRange>('30d')
  const [data, setData] = useState<CostSummary | null>(null)
  const [topSessions, setTopSessions] = useState<TopSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    async function fetchData() {
      setLoading(true)
      setError(null)
      try {
        const [summaryRes, topSessionsRes] = await Promise.all([
          getCostSummary(range),
          getTopSessions(range, 5),
        ])
        if (!ignore) {
          setData(summaryRes as CostSummary)
          setTopSessions(topSessionsRes as TopSession[])
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
  }, [range])

  if (loading) {
    return (
      <section className="panel cost-summary-panel">
        <div className="cost-summary-header">
          <p className="eyebrow">Cost</p>
          <h2>Cost Dashboard</h2>
        </div>
        <p className="cost-summary-loading">Loading cost data...</p>
      </section>
    )
  }

  if (error || !data) {
    return (
      <section className="panel cost-summary-panel">
        <div className="cost-summary-header">
          <p className="eyebrow">Cost</p>
          <h2>Cost Dashboard</h2>
        </div>
        <p className="cost-summary-error">Failed to load cost data</p>
      </section>
    )
  }

  // Calculate total tokens from framework breakdown
  const totalTokens = data.by_framework.reduce((sum, fw) => sum + fw.total_tokens, 0)

  // Format cost with appropriate decimal precision
  function formatCost(cost: number): string {
    if (cost >= 1) return `$${cost.toFixed(2)}`
    if (cost >= 0.01) return `$${cost.toFixed(4)}`
    return `$${cost.toFixed(6)}`
  }

  // Build sparkline from daily cost data
  const maxCost = Math.max(...data.daily_cost.map((d) => d.total_cost_usd), 0.01)
  const sparklineBars = data.daily_cost.map((d) => ({
    height: (d.total_cost_usd / maxCost) * 100,
    date: d.date,
    cost: d.total_cost_usd,
  }))

  // Sort frameworks by total cost descending
  const sortedFrameworks = [...data.by_framework].sort((a, b) => b.total_cost_usd - a.total_cost_usd)

  return (
    <section className="panel cost-summary-panel">
      <div className="cost-summary-header">
        <div>
          <p className="eyebrow">Cost</p>
          <h2>Cost Dashboard</h2>
        </div>
        <div className="time-range-selector">
          {(['7d', '30d', '90d'] as TimeRange[]).map((r) => (
            <button
              key={r}
              type="button"
              className={`time-range-btn ${range === r ? 'active' : ''}`}
              onClick={() => setRange(r)}
            >
              {r === '7d' ? '7 days' : r === '30d' ? '30 days' : '90 days'}
            </button>
          ))}
        </div>
      </div>

      {data.period_start && data.period_end && (
        <div className="cost-period">
          {data.period_start} to {data.period_end}
        </div>
      )}

      <div className="cost-stats">
        <div className="stat-card">
          <span className="stat-value">{formatCost(data.total_cost_usd)}</span>
          <span className="stat-label">Total Spend</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.session_count.toLocaleString()}</span>
          <span className="stat-label">Sessions</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{formatCost(data.avg_cost_per_session)}</span>
          <span className="stat-label">Avg / Session</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{totalTokens.toLocaleString()}</span>
          <span className="stat-label">Total Tokens</span>
        </div>
      </div>

      {data.daily_cost.length > 0 && (
        <div className="cost-section">
          <h3>Daily Cost</h3>
          <div className="sparkline">
            {sparklineBars.map((bar, idx) => (
              <div
                key={idx}
                className="sparkline-bar"
                style={{ height: `${Math.max(bar.height, 5)}%` }}
                title={`${bar.date}: ${formatCost(bar.cost)}`}
              />
            ))}
          </div>
        </div>
      )}

      {sortedFrameworks.length > 0 && (
        <div className="cost-section">
          <h3>By Framework</h3>
          <div className="cost-framework-list">
            {sortedFrameworks.map((fw) => {
              const percentage = data.total_cost_usd > 0 ? (fw.total_cost_usd / data.total_cost_usd) * 100 : 0
              return (
                <div key={fw.framework} className="cost-framework-item">
                  <div className="cost-framework-header">
                    <span className="cost-framework-name">{fw.framework}</span>
                    <span className="cost-framework-cost">{formatCost(fw.total_cost_usd)}</span>
                  </div>
                  <div className="cost-framework-bar-track">
                    <div
                      className="cost-framework-bar-fill"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <div className="cost-framework-details">
                    <span>{fw.session_count} sessions</span>
                    <span>{fw.total_tokens.toLocaleString()} tokens</span>
                    <span>{formatCost(fw.avg_cost_per_session)} / session</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {topSessions.length > 0 && (
        <div className="cost-section">
          <h3>Top Expensive Sessions</h3>
          <div className="cost-top-sessions">
            {topSessions.map((session) => (
              <div key={session.session_id} className="cost-top-session-item">
                <div className="cost-top-session-main">
                  <span className="cost-top-session-name">{session.agent_name}</span>
                  <span className="cost-top-session-cost">{formatCost(session.total_cost_usd)}</span>
                </div>
                <div className="cost-top-session-details">
                  <span className="cost-top-session-framework">{session.framework}</span>
                  <span className="cost-top-session-date">
                    {new Date(session.started_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
