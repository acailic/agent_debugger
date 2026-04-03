import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SessionRail } from '../components/SessionRail'
import type { Session, TraceBundle } from '../types'

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockSessions: Session[] = [
  {
    id: 'session-1',
    agent_name: 'Test Agent 1',
    framework: 'langchain',
    started_at: '2024-01-01T10:00:00Z',
    ended_at: '2024-01-01T10:05:00Z',
    status: 'completed',
    total_tokens: 1000,
    total_cost_usd: 0.01,
    tool_calls: 10,
    llm_calls: 5,
    errors: 0,
    config: {},
    tags: [],
    replay_value: 0.85,
    retention_tier: 'full',
    failure_count: 0,
    behavior_alert_count: 1,
    representative_event_id: null,
    fix_note: null,
  },
  {
    id: 'session-2',
    agent_name: 'Test Agent 2',
    framework: 'openai',
    started_at: '2024-01-01T11:00:00Z',
    ended_at: '2024-01-01T11:03:00Z',
    status: 'error',
    total_tokens: 500,
    total_cost_usd: 0.005,
    tool_calls: 5,
    llm_calls: 3,
    errors: 2,
    config: {},
    tags: [],
    replay_value: 0.45,
    retention_tier: 'downsampled',
    failure_count: 2,
    behavior_alert_count: 3,
    representative_event_id: null,
    fix_note: null,
  },
]

const mockBundle: TraceBundle = {
  session: mockSessions[0],
  events: [],
  checkpoints: [],
  tree: null,
  analysis: {
    event_rankings: [],
    failure_clusters: [],
    representative_failure_ids: [],
    high_replay_value_ids: [],
    failure_explanations: [],
    checkpoint_rankings: [],
    session_replay_value: 0.85,
    retention_tier: 'full',
    session_summary: {
      failure_count: 0,
      behavior_alert_count: 1,
      high_severity_count: 0,
      checkpoint_count: 3,
    },
    live_summary: {
      event_count: 10,
      checkpoint_count: 3,
      latest: {
        decision_event_id: null,
        tool_event_id: null,
        safety_event_id: null,
        turn_event_id: null,
        policy_event_id: null,
        checkpoint_id: null,
      },
      rolling_summary: 'Test session running normally',
      recent_alerts: [],
    },
    behavior_alerts: [],
    highlights: [],
  },
}

// ---------------------------------------------------------------------------
// Zustand store mock
// ---------------------------------------------------------------------------

/**
 * The SessionRail onClick handler calls `useSessionStore.getState().secondarySessionId`
 * in addition to the selector-based `useSessionStore(selector)` calls.
 * Both must be mocked from the same state object.
 */

/** Build a default mock state with sensible defaults and overridable fields. */
function buildState(overrides: Record<string, unknown> = {}) {
  return {
    sessions: mockSessions,
    selectedSessionId: null,
    bundle: null,
    loading: false,
    sessionSortMode: 'started_at' as const,
    secondarySessionId: null,
    setSecondarySessionId: vi.fn(),
    setSelectedSessionId: vi.fn(),
    setSessionSortMode: vi.fn(),
    setReplayMode: vi.fn(),
    setSelectedEventId: vi.fn(),
    ...overrides,
  }
}

// Shared mutable state that both the selector mock and getState() read from.
let currentState: ReturnType<typeof buildState>

const mockUseSessionStore = vi.fn((selector: unknown) => {
  if (typeof selector === 'function') {
    return selector(currentState)
  }
  return currentState
}) as unknown as typeof import('../stores/sessionStore').useSessionStore

// The component calls useSessionStore.getState() directly in its onClick handler.
mockUseSessionStore.getState = () => currentState

vi.mock('../stores/sessionStore', () => ({
  get useSessionStore() {
    return mockUseSessionStore
  },
}))

// CostPanel and FixAnnotation are rendered when a session is selected.
vi.mock('../api/client', () => ({
  getSessionCost: vi.fn().mockResolvedValue(null),
  addFixNote: vi.fn().mockResolvedValue({}),
}))

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SessionRail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentState = buildState()
  })

  // -----------------------------------------------------------------------
  // Basic rendering
  // -----------------------------------------------------------------------

  describe('rendering', () => {
    it('renders session rail with header', () => {
      render(<SessionRail />)

      expect(screen.getByText('Sessions')).toBeInTheDocument()
      expect(screen.getByText('Captured Runs')).toBeInTheDocument()
    })

    it('renders session cards for each session', () => {
      render(<SessionRail />)

      expect(screen.getByText('Test Agent 1')).toBeInTheDocument()
      expect(screen.getByText('Test Agent 2')).toBeInTheDocument()
    })

    it('displays session framework', () => {
      render(<SessionRail />)

      expect(screen.getByText('langchain')).toBeInTheDocument()
      expect(screen.getByText('openai')).toBeInTheDocument()
    })

    it('displays session status', () => {
      render(<SessionRail />)

      expect(screen.getByText('completed')).toBeInTheDocument()
      expect(screen.getByText('error')).toBeInTheDocument()
    })

    it('displays replay value badge', () => {
      render(<SessionRail />)

      expect(screen.getByText('Replay 0.85')).toBeInTheDocument()
      expect(screen.getByText('Replay 0.45')).toBeInTheDocument()
    })

    it('displays retention tier pill', () => {
      render(<SessionRail />)

      expect(screen.getByText('full')).toBeInTheDocument()
      expect(screen.getByText('downsampled')).toBeInTheDocument()
    })
  })

  // -----------------------------------------------------------------------
  // Health grade badge
  // -----------------------------------------------------------------------

  describe('health grade badge', () => {
    it('displays health grade badge for each session', () => {
      render(<SessionRail />)

      const gradeBadges = screen.getAllByText(/^[A-F]$/, { selector: '.health-grade-badge' })
      expect(gradeBadges.length).toBeGreaterThan(0)
    })

    it('displays health score numeric value', () => {
      render(<SessionRail />)

      const scoreBadges = screen.getAllByText(/\d{1,3}/, { selector: '.health-score-badge' })
      expect(scoreBadges.length).toBeGreaterThan(0)
    })

    it('shows better grade for healthy session vs unhealthy session', () => {
      render(<SessionRail />)

      const scoreBadges = screen.getAllByText(/\d{1,3}/, { selector: '.health-score-badge' })
      const scores = scoreBadges.map((badge) => {
        const match = badge.textContent?.match(/(\d+)/)
        return match ? parseInt(match[1]) : 0
      })

      // Session 1 (completed, 0 errors, replay 0.85) should score higher than
      // Session 2 (error status, 2 errors, replay 0.45)
      expect(scores[0]).toBeGreaterThan(scores[1])
    })

    it('penalizes errors heavily in health score', () => {
      const sessionWithErrors: Session = {
        ...mockSessions[0],
        errors: 3,
        behavior_alert_count: 0,
        replay_value: 0.8,
        status: 'completed',
      }

      const sessionWithoutErrors: Session = {
        ...mockSessions[0],
        id: 'session-no-errors',
        agent_name: 'Clean Agent',
        errors: 0,
        behavior_alert_count: 0,
        replay_value: 0.8,
        status: 'completed',
      }

      currentState = buildState({
        sessions: [sessionWithErrors, sessionWithoutErrors],
      })

      render(<SessionRail />)

      const scoreBadges = screen.getAllByText(/\d{1,3}/, { selector: '.health-score-badge' })
      const scores = scoreBadges.map((badge) => {
        const match = badge.textContent?.match(/(\d+)/)
        return match ? parseInt(match[1]) : 0
      })

      // Session without errors should score higher
      expect(scores[1]).toBeGreaterThan(scores[0])
    })

    it('applies correct color for grade A (score >= 90)', () => {
      const healthySession: Session = {
        ...mockSessions[0],
        errors: 0,
        behavior_alert_count: 0,
        replay_value: 5.0,
        status: 'completed',
      }

      currentState = buildState({ sessions: [healthySession] })

      render(<SessionRail />)

      const gradeBadge = screen.getByText('A', { selector: '.health-grade-badge' })
      expect(gradeBadge).toBeInTheDocument()
      // Grade A color: #10b981 => rgb(16, 185, 129)
      expect(gradeBadge.style.backgroundColor).toBe('rgb(16, 185, 129)')
    })

    it('applies correct color for grade F (score < 60)', () => {
      const failingSession: Session = {
        ...mockSessions[0],
        errors: 5,
        behavior_alert_count: 5,
        replay_value: 0,
        status: 'error',
      }

      currentState = buildState({ sessions: [failingSession] })

      render(<SessionRail />)

      const gradeBadge = screen.getByText('F', { selector: '.health-grade-badge' })
      expect(gradeBadge).toBeInTheDocument()
      // Grade F color: #ef4444 => rgb(239, 68, 68)
      expect(gradeBadge.style.backgroundColor).toBe('rgb(239, 68, 68)')
    })

    it('shows tooltip with health score and label', () => {
      render(<SessionRail />)

      const gradeBadges = screen.getAllByText(/^[A-F]$/, { selector: '.health-grade-badge' })
      gradeBadges.forEach((badge) => {
        expect(badge.title).toMatch(/Health Score:/)
      })
    })
  })

  // -----------------------------------------------------------------------
  // Session selection
  // -----------------------------------------------------------------------

  describe('session selection', () => {
    it('calls setSelectedSessionId when session card is clicked', async () => {
      const mockSetSelectedSessionId = vi.fn()
      currentState = buildState({ setSelectedSessionId: mockSetSelectedSessionId })

      render(<SessionRail />)

      const sessionCard = screen.getByText('Test Agent 1').closest('button')!
      await userEvent.click(sessionCard)

      expect(mockSetSelectedSessionId).toHaveBeenCalledWith('session-1')
    })

    it('applies active class to selected session', () => {
      currentState = buildState({ selectedSessionId: 'session-1' })

      render(<SessionRail />)

      const sessionCard = screen.getByText('Test Agent 1').closest('button')
      expect(sessionCard).toHaveClass('active')

      const otherCard = screen.getByText('Test Agent 2').closest('button')
      expect(otherCard).not.toHaveClass('active')
    })

    it('resets replay mode and selected event when session is selected', async () => {
      const mockSetReplayMode = vi.fn()
      const mockSetSelectedEventId = vi.fn()

      currentState = buildState({
        setReplayMode: mockSetReplayMode,
        setSelectedEventId: mockSetSelectedEventId,
      })

      render(<SessionRail />)

      const sessionCard = screen.getByText('Test Agent 1').closest('button')!
      await userEvent.click(sessionCard)

      expect(mockSetReplayMode).toHaveBeenCalledWith('full')
      expect(mockSetSelectedEventId).toHaveBeenCalledWith(null)
    })

    it('calls setSecondarySessionId on click using getState', async () => {
      const mockSetSecondarySessionId = vi.fn()

      currentState = buildState({
        secondarySessionId: null,
        setSecondarySessionId: mockSetSecondarySessionId,
      })

      render(<SessionRail />)

      const sessionCard = screen.getByText('Test Agent 1').closest('button')!
      await userEvent.click(sessionCard)

      // The onClick reads secondarySessionId from getState() and passes it to setSecondarySessionId
      // When secondarySessionId is null: setSecondarySessionId(null)
      expect(mockSetSecondarySessionId).toHaveBeenCalledWith(null)
    })
  })

  // -----------------------------------------------------------------------
  // Empty state
  // -----------------------------------------------------------------------

  describe('empty state', () => {
    it('renders empty state when no sessions and not loading', () => {
      currentState = buildState({ sessions: [] })

      render(<SessionRail />)

      expect(screen.getByText('No sessions yet')).toBeInTheDocument()
      expect(screen.getByText(/Capture your first agent run/)).toBeInTheDocument()
    })

    it('shows installation steps in empty state', () => {
      currentState = buildState({ sessions: [] })

      render(<SessionRail />)

      expect(screen.getByText('Install the SDK')).toBeInTheDocument()
      expect(screen.getByText('Add @trace decorator')).toBeInTheDocument()
      expect(screen.getByText('Run your agent')).toBeInTheDocument()
    })

    it('does not show empty state when sessions exist', () => {
      render(<SessionRail />)

      expect(screen.queryByText('No sessions yet')).not.toBeInTheDocument()
    })
  })

  // -----------------------------------------------------------------------
  // Loading state
  // -----------------------------------------------------------------------

  describe('loading state', () => {
    it('renders loading skeleton when loading and no sessions', () => {
      currentState = buildState({ sessions: [], loading: true })

      render(<SessionRail />)

      expect(screen.getByLabelText('Loading sessions')).toBeInTheDocument()
    })

    it('does not show loading skeleton when sessions already loaded', () => {
      currentState = buildState({ sessions: mockSessions, loading: true })

      render(<SessionRail />)

      // When loading=true but sessions exist, skeleton should not appear
      // (the component checks: loading && !sessions.length)
      expect(screen.queryByLabelText('Loading sessions')).not.toBeInTheDocument()
    })
  })

  // -----------------------------------------------------------------------
  // Session sort mode
  // -----------------------------------------------------------------------

  describe('session sort mode', () => {
    it('renders sort mode switches', () => {
      render(<SessionRail />)

      expect(screen.getByRole('button', { name: 'Top replay' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Recent' })).toBeInTheDocument()
    })

    it('applies active class to current sort mode', () => {
      currentState = buildState({ sessionSortMode: 'started_at' as const })

      render(<SessionRail />)

      expect(screen.getByRole('button', { name: 'Recent' })).toHaveClass('active')
      expect(screen.getByRole('button', { name: 'Top replay' })).not.toHaveClass('active')
    })

    it('calls setSessionSortMode when sort mode is clicked', async () => {
      const mockSetSessionSortMode = vi.fn()
      currentState = buildState({
        sessionSortMode: 'started_at' as const,
        setSessionSortMode: mockSetSessionSortMode,
      })

      render(<SessionRail />)

      await userEvent.click(screen.getByRole('button', { name: 'Top replay' }))

      expect(mockSetSessionSortMode).toHaveBeenCalledWith('replay_value')
    })
  })

  // -----------------------------------------------------------------------
  // Current session details panel
  // -----------------------------------------------------------------------

  describe('current session details', () => {
    it('renders session stats when session is selected', () => {
      currentState = buildState({
        selectedSessionId: 'session-1',
        bundle: mockBundle,
      })

      render(<SessionRail />)

      expect(screen.getByText('LLM calls')).toBeInTheDocument()
      expect(screen.getByText('Tool calls')).toBeInTheDocument()
      expect(screen.getByText('Errors')).toBeInTheDocument()
      expect(screen.getByText('Cost')).toBeInTheDocument()
    })

    it('displays metrics for current session', () => {
      currentState = buildState({
        selectedSessionId: 'session-1',
        bundle: mockBundle,
      })

      render(<SessionRail />)

      // Session 1 has llm_calls=5, tool_calls=10, errors=0
      expect(screen.getByText('5')).toBeInTheDocument() // LLM calls
      expect(screen.getByText('10')).toBeInTheDocument() // Tool calls
      expect(screen.getByText('0')).toBeInTheDocument() // Errors
    })
  })

  // -----------------------------------------------------------------------
  // Store integration
  // -----------------------------------------------------------------------

  describe('store integration', () => {
    it('subscribes to store for rendering', () => {
      render(<SessionRail />)

      // useSessionStore should have been called with selectors
      expect(mockUseSessionStore).toHaveBeenCalled()
    })
  })
})
