import { useEffect, useState } from 'react'
import { getAnalytics } from '../api/client'
import type { AnalyticsResponse } from '../types'

type TimeRange = '7d' | '30d' | '90d'

export function AnalyticsPanel() {
  const [range, setRange] = useState<TimeRange>('30d')
  const [data, setData] = useState<AnalyticsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    async function fetchData() {
      setLoading(true)
      setError(null)
      try {
        const response = await getAnalytics(range)
        if (!ignore) {
          setData(response)
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load analytics')
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
      <section className="panel analytics-panel">
        <div className="analytics-header">
          <p className="eyebrow">Analytics</p>
          <h2>Usage Insights</h2>
        </div>
        <p className="analytics-loading">Loading...</p>
      </section>
    )
  }

  if (error || !data) {
    return (
      <section className="panel analytics-panel">
        <div className="analytics-header">
          <p className="eyebrow">Analytics</p>
          <h2>Usage Insights</h2>
        </div>
        <p className="analytics-error">Analytics unavailable</p>
      </section>
    )
  }

  const { metrics, derived, daily_breakdown } = data

  // Calculate NL Queries adoption rate (derived from nl_queries_made / sessions_created)
  const nlQueriesRate = metrics.sessions_created > 0
    ? metrics.nl_queries_made / metrics.sessions_created
    : 0

  // Build sparkline from daily breakdown
  const maxSessions = Math.max(...daily_breakdown.map(d => d.sessions), 1)
  const sparklineBars = daily_breakdown.map(d => ({
    height: (d.sessions / maxSessions) * 100,
    date: d.date
  }))

  return (
    <section className="panel analytics-panel">
      <div className="analytics-header">
        <div>
          <p className="eyebrow">Analytics</p>
          <h2>Usage Insights</h2>
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

      <div className="analytics-period">
        {data.period_start} to {data.period_end}
      </div>

      <div className="analytics-stats">
        <div className="stat-card">
          <span className="stat-value">{metrics.sessions_created}</span>
          <span className="stat-label">Sessions</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{derived.estimated_time_saved_minutes}</span>
          <span className="stat-label">Time Saved (min)</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{metrics.why_button_clicks}</span>
          <span className="stat-label">Why Clicks</span>
        </div>
      </div>

      <div className="analytics-section">
        <h3>Feature Adoption</h3>
        <div className="adoption-bars">
          <AdoptionBar label="Why Button" rate={derived.adoption_rate.why_button} />
          <AdoptionBar label="Replay Highlights" rate={derived.adoption_rate.replay_highlights} />
          <AdoptionBar label="Failure Memory" rate={derived.adoption_rate.failure_memory} />
          <AdoptionBar label="NL Queries" rate={nlQueriesRate} />
        </div>
      </div>

      <div className="analytics-section">
        <h3>Sessions over time</h3>
        <div className="sparkline">
          {sparklineBars.length > 0 ? (
            sparklineBars.map((bar, idx) => (
              <div
                key={idx}
                className="sparkline-bar"
                style={{ height: `${Math.max(bar.height, 5)}%` }}
                title={`${bar.date}: ${daily_breakdown[idx]?.sessions ?? 0} sessions`}
              />
            ))
          ) : (
            <p className="sparkline-empty">No activity yet</p>
          )}
        </div>
      </div>
    </section>
  )
}

function AdoptionBar({ label, rate }: { label: string; rate: number }) {
  const percentage = Math.round(rate * 100)
  return (
    <div className="adoption-bar-row">
      <div className="adoption-bar-track">
        <div
          className="adoption-bar-fill"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="adoption-bar-label">{label}</span>
      <span className="adoption-bar-percent">{percentage}%</span>
    </div>
  )
}
