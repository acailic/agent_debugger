import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DriftAlertsPanel } from '../components/DriftAlertsPanel'
import type { DriftResponse } from '../types'

const driftData: DriftResponse = {
  agent_name: 'weather-agent',
  baseline_session_count: 12,
  recent_session_count: 4,
  baseline: {
    agent_name: 'weather-agent',
    session_count: 12,
    total_llm_calls: 30,
    total_tool_calls: 18,
    total_tokens: 4200,
    total_cost_usd: 1.23,
    avg_llm_calls_per_session: 2.5,
    avg_tool_calls_per_session: 1.5,
    avg_tokens_per_session: 350,
    avg_cost_per_session: 0.1025,
    error_rate: 0.0833,
    avg_duration_seconds: 14.2,
  },
  current: {
    agent_name: 'weather-agent',
    session_count: 4,
    total_llm_calls: 12,
    total_tool_calls: 6,
    total_tokens: 1800,
    total_cost_usd: 0.51,
    avg_llm_calls_per_session: 3,
    avg_tool_calls_per_session: 1.5,
    avg_tokens_per_session: 450,
    avg_cost_per_session: 0.1275,
    error_rate: 0.125,
    avg_duration_seconds: 18.7,
  },
  alerts: [
    {
      metric: 'avg_cost_per_session',
      metric_label: 'Cost per session',
      baseline_value: 0.1025,
      current_value: 0.1275,
      change_percent: 24.4,
      severity: 'warning',
      description: 'Cost per session increased from 0.10 to 0.13',
    },
  ],
  message: 'Drift detected',
}

describe('DriftAlertsPanel', () => {
  it('renders the backend drift contract without requiring removed fields', () => {
    render(<DriftAlertsPanel agentName="weather-agent" driftData={driftData} loading={false} />)

    expect(screen.getByText('Behavior Drift')).toBeInTheDocument()
    expect(screen.getByText('weather-agent')).toBeInTheDocument()
    expect(screen.getByText('Drift detected')).toBeInTheDocument()
    expect(screen.getByText('Sessions: 12')).toBeInTheDocument()
    expect(screen.getByText('LLM/session: 2.500')).toBeInTheDocument()
    expect(screen.getByText('Cost/session: $0.102')).toBeInTheDocument()
    expect(screen.getByText('Current Sessions: 4')).toBeInTheDocument()
    expect(screen.getByText('Duration: 18.7s')).toBeInTheDocument()
    expect(screen.getByText('Cost per session')).toBeInTheDocument()
    expect(screen.queryByText(/Likely cause:/i)).not.toBeInTheDocument()
  })
})
