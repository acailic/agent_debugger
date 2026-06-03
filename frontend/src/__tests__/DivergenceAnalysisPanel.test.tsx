import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Mock } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DivergenceAnalysisPanel } from '../components/DivergenceAnalysisPanel'
import type { Session } from '../types'

// Mock API calls to prevent actual network requests
vi.mock('../api/client', () => ({
  getDivergenceAnalysis: vi.fn(),
  getStructuralDivergence: vi.fn(),
  getTemporalDivergence: vi.fn(),
  getBehavioralDivergence: vi.fn(),
  getBaselineDivergence: vi.fn(),
}))

// Helper function to create a test session
function createTestSession(overrides: Partial<Session> = {}): Session {
  return {
    id: 'session-1',
    agent_name: 'test-agent',
    framework: 'test-framework',
    started_at: '2026-06-03T10:00:00Z',
    ended_at: '2026-06-03T10:05:00Z',
    status: 'completed',
    total_tokens: 1000,
    total_cost_usd: 0.05,
    tool_calls: 5,
    llm_calls: 3,
    errors: 0,
    config: {},
    tags: [],
    ...overrides,
  }
}

describe('DivergenceAnalysisPanel', () => {
  let onSelectSecondarySession: Mock<(sessionId: string | null) => void>

  beforeEach(() => {
    onSelectSecondarySession = vi.fn() as Mock<(sessionId: string | null) => void>
  })

  it('renders empty state when no primary session selected', () => {
    render(
      <DivergenceAnalysisPanel
        primarySessionId={null}
        secondarySessionId={null}
        sessions={[]}
        onSelectSecondarySession={onSelectSecondarySession}
      />
    )

    expect(screen.getByText('Select a primary session to analyze divergences.')).toBeInTheDocument()
  })

  it('renders secondary session selector when primary session selected', () => {
    const sessions = [
      createTestSession({ id: 'session-1' }),
      createTestSession({ id: 'session-2' }),
    ]

    render(
      <DivergenceAnalysisPanel
        primarySessionId="session-1"
        secondarySessionId={null}
        sessions={sessions}
        onSelectSecondarySession={onSelectSecondarySession}
      />
    )

    expect(screen.getByText('Select comparison session')).toBeInTheDocument()
    // The component renders session as "agent_name · started_at"
    expect(screen.getByText('test-agent · 2026-06-03T10:00:00Z')).toBeInTheDocument()
  })

  it('calls onSelectSecondarySession when secondary session is chosen', async () => {
    const user = await userEvent.setup()
    const sessions = [
      createTestSession({ id: 'session-1' }),
      createTestSession({ id: 'session-2' }),
    ]

    render(
      <DivergenceAnalysisPanel
        primarySessionId="session-1"
        secondarySessionId={null}
        sessions={sessions}
        onSelectSecondarySession={onSelectSecondarySession}
      />
    )

    const select = screen.getByRole('combobox')
    await user.selectOptions(select, 'session-2')

    expect(onSelectSecondarySession).toHaveBeenCalledWith('session-2')
  })

  it('does not show primary session in secondary options', () => {
    const sessions = [
      createTestSession({ id: 'session-1' }),
      createTestSession({ id: 'session-2' }),
    ]

    render(
      <DivergenceAnalysisPanel
        primarySessionId="session-1"
        secondarySessionId={null}
        sessions={sessions}
        onSelectSecondarySession={onSelectSecondarySession}
      />
    )

    const options = screen.getAllByRole('option')
    const optionValues = options.map(option => option.getAttribute('value'))

    expect(optionValues).not.toContain('session-1')
    expect(optionValues).toContain('session-2')
  })

  it('prompts to select secondary session when only primary is selected', () => {
    const sessions = [
      createTestSession({ id: 'session-1' }),
      createTestSession({ id: 'session-2' }),
    ]

    render(
      <DivergenceAnalysisPanel
        primarySessionId="session-1"
        secondarySessionId={null}
        sessions={sessions}
        onSelectSecondarySession={onSelectSecondarySession}
      />
    )

    expect(screen.getByText('Select a secondary session to compare and analyze divergences.')).toBeInTheDocument()
  })
})