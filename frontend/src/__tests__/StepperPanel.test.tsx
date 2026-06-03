import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { StepperPanel } from '../components/StepperPanel'
import * as api from '../api/client'

// Mock the API client
vi.mock('../api/client', () => ({
  setBreakpoint: vi.fn(),
  clearBreakpoint: vi.fn(),
  clearAllBreakpoints: vi.fn(),
  listBreakpoints: vi.fn(),
  stepExecution: vi.fn(),
  getStepperState: vi.fn(),
  createBranch: vi.fn(),
  listBranches: vi.fn(),
  deleteBranch: vi.fn(),
  resetStepper: vi.fn(),
  getExecutionContext: vi.fn(),
}))

const mockBreakpoints = [
  {
    breakpoint_id: 'bp_1',
    breakpoint_type: 'event_type' as const,
    condition_value: 'decision',
    description: 'Break on decisions',
    enabled: true,
    hit_count: 0,
    created_at: '2024-01-01T00:00:00Z',
  },
]

const mockBranches = [
  {
    branch_id: 'branch_1',
    parent_event_id: 'event_123',
    name: 'Test Branch',
    description: 'Test branch description',
    created_at: '2024-01-01T00:00:00Z',
    replay_events_count: 5,
    branch_result: null,
  },
]

const mockStepperState = {
  current_event_index: 0,
  current_event_id: 'event_123',
  breakpoints: [],
  step_history: [],
  paused: true,
  completed: false,
}

const mockAgentState = {
  completed: false,
  current_position: 0,
  total_events: 10,
  current_event: {
    id: 'event_123',
    session_id: 'test-session',
    event_id: 'event_123',
    event_type: 'decision' as const,
    timestamp: '2024-01-01T00:00:00Z',
    name: 'Test Decision',
    data: {},
    parent_id: null,
    confidence: 0.9,
    reasoning: 'Test reasoning',
    metadata: {},
    importance: 0.5,
    upstream_event_ids: [],
  } as any,
  events_count: 1,
  breakpoints_active: 0,
  paused: true,
}

describe('StepperPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Setup default mock implementations
    vi.mocked(api.listBreakpoints).mockResolvedValue({ session_id: 'test', breakpoints: [] })
    vi.mocked(api.listBranches).mockResolvedValue({ session_id: 'test', branches: [] })
    vi.mocked(api.getStepperState).mockResolvedValue({
      session_id: 'test',
      stepper_state: mockStepperState,
      agent_state: mockAgentState,
    })
  })

  it('renders empty state when no session is selected', () => {
    render(<StepperPanel sessionId={null} />)
    expect(screen.getByText('Select a session to start debugging.')).toBeInTheDocument()
  })

  it('loads stepper state when session is provided', async () => {
    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(api.listBreakpoints).toHaveBeenCalledWith('test-session')
      expect(api.listBranches).toHaveBeenCalledWith('test-session')
      expect(api.getStepperState).toHaveBeenCalledWith('test-session')
    })
  })

  it('displays breakpoints tab by default', async () => {
    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Set New Breakpoint')).toBeInTheDocument()
    })
  })

  it('switches between tabs', async () => {
    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Breakpoints')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Step Controls'))
    await waitFor(() => {
      expect(screen.getByText('Step Controls')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('State Inspector'))
    await waitFor(() => {
      expect(screen.getByText('Agent State')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Branches'))
    await waitFor(() => {
      expect(screen.getByText('Branch Points')).toBeInTheDocument()
    })
  })

  it('sets breakpoint with form', async () => {
    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Set New Breakpoint')).toBeInTheDocument()
    })

    // Fill breakpoint form
    const conditionInput = screen.getByPlaceholderText('e.g., decision, search_tool, 0.5, pass')
    fireEvent.change(conditionInput, { target: { value: 'decision' } })

    const descInput = screen.getByPlaceholderText('Break on all decisions')
    fireEvent.change(descInput, { target: { value: 'Break on decisions' } })

    // Submit form
    vi.mocked(api.setBreakpoint).mockResolvedValue({
      session_id: 'test-session',
      breakpoint: mockBreakpoints[0],
      stepper_state: { ...mockStepperState, breakpoints: mockBreakpoints },
    })

    fireEvent.click(screen.getByText('Set Breakpoint'))

    await waitFor(() => {
      expect(api.setBreakpoint).toHaveBeenCalledWith(
        'test-session',
        'event_type',
        'decision',
        'Break on decisions'
      )
    })
  })

  it('displays breakpoints list', async () => {
    vi.mocked(api.listBreakpoints).mockResolvedValue({
      session_id: 'test',
      breakpoints: mockBreakpoints,
    })

    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Active Breakpoints (1)')).toBeInTheDocument()
      expect(screen.getByText('decision')).toBeInTheDocument()
    })
  })

  it('clears individual breakpoint', async () => {
    vi.mocked(api.listBreakpoints).mockResolvedValue({
      session_id: 'test',
      breakpoints: mockBreakpoints,
    })

    vi.mocked(api.clearBreakpoint).mockResolvedValue({
      session_id: 'test',
      success: true,
      stepper_state: { ...mockStepperState, breakpoints: [] },
    })

    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('decision')).toBeInTheDocument()
    })

    // Find and click the clear button (×)
    const clearButtons = screen.getAllByTitle('Clear breakpoint')
    fireEvent.click(clearButtons[0])

    await waitFor(() => {
      expect(api.clearBreakpoint).toHaveBeenCalledWith('test-session', 'bp_1')
    })
  })

  it('clears all breakpoints', async () => {
    vi.mocked(api.listBreakpoints).mockResolvedValue({
      session_id: 'test',
      breakpoints: mockBreakpoints,
    })

    vi.mocked(api.clearAllBreakpoints).mockResolvedValue({
      session_id: 'test',
      success: true,
      breakpoints_cleared: 1,
      stepper_state: { ...mockStepperState, breakpoints: [] },
    })

    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Active Breakpoints (1)')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Clear All'))

    await waitFor(() => {
      expect(api.clearAllBreakpoints).toHaveBeenCalledWith('test-session')
    })
  })

  it('executes step actions', async () => {
    render(<StepperPanel sessionId="test-session" />)

    // Switch to step controls tab
    fireEvent.click(screen.getByText('Step Controls'))

    await waitFor(() => {
      expect(screen.getByText('Step Into')).toBeInTheDocument()
    })

    vi.mocked(api.stepExecution).mockResolvedValue({
      session_id: 'test-session',
      step_result: {
        success: true,
        current_event: mockAgentState.current_event,
        next_event: null,
        breakpoint_hit: null,
        state: { ...mockStepperState, current_event_index: 1 },
        message: 'Stepped to event_123',
      },
    })

    // Click step into button
    fireEvent.click(screen.getByText('Step Into'))

    await waitFor(() => {
      expect(api.stepExecution).toHaveBeenCalledWith('test-session', 'step_into')
    })
  })

  it('displays step controls', async () => {
    render(<StepperPanel sessionId="test-session" />)

    fireEvent.click(screen.getByText('Step Controls'))

    await waitFor(() => {
      expect(screen.getByText('Step Into')).toBeInTheDocument()
      expect(screen.getByText('Next decision')).toBeInTheDocument()
      expect(screen.getByText('Step Over')).toBeInTheDocument()
      expect(screen.getByText('Skip tool internals')).toBeInTheDocument()
      expect(screen.getByText('Step Out')).toBeInTheDocument()
      expect(screen.getByText('To parent context')).toBeInTheDocument()
      expect(screen.getByText('Continue')).toBeInTheDocument()
      expect(screen.getByText('To next breakpoint')).toBeInTheDocument()
    })
  })

  it('displays agent state', async () => {
    render(<StepperPanel sessionId="test-session" />)

    // Switch to state inspector tab
    fireEvent.click(screen.getByText('State Inspector'))

    await waitFor(() => {
      expect(screen.getByText('Agent State')).toBeInTheDocument()
      expect(screen.getByText('Current Event')).toBeInTheDocument()
    })

    // Should display current event information
    expect(screen.getByText('event_123')).toBeInTheDocument()
    expect(screen.getByText('decision')).toBeInTheDocument()
  })

  it('creates branch', async () => {
    vi.mocked(api.listBranches).mockResolvedValue({
      session_id: 'test',
      branches: [],
    })

    render(<StepperPanel sessionId="test-session" />)

    // Switch to branches tab
    fireEvent.click(screen.getByText('Branches'))

    await waitFor(() => {
      expect(screen.getByText('Branch Points (0)')).toBeInTheDocument()
    })

    // Mock prompt and createBranch
    const promptMock = vi.fn()
      .mockReturnValueOnce('Test Branch')
      .mockReturnValueOnce('Test description')
    globalThis.prompt = promptMock

    vi.mocked(api.createBranch).mockResolvedValue({
      session_id: 'test-session',
      branch: mockBranches[0],
    })

    vi.mocked(api.listBranches).mockResolvedValue({
      session_id: 'test',
      branches: mockBranches,
    })

    fireEvent.click(screen.getByText('Create Branch'))

    await waitFor(() => {
      expect(api.createBranch).toHaveBeenCalledWith(
        'test-session',
        'Test Branch',
        'event_123',
        'Test description'
      )
    })
  })

  it('displays branches list', async () => {
    vi.mocked(api.listBranches).mockResolvedValue({
      session_id: 'test',
      branches: mockBranches,
    })

    render(<StepperPanel sessionId="test-session" />)

    // Switch to branches tab
    fireEvent.click(screen.getByText('Branches'))

    await waitFor(() => {
      expect(screen.getByText('Branch Points (1)')).toBeInTheDocument()
      expect(screen.getByText('Test Branch')).toBeInTheDocument()
      expect(screen.getByText('Test branch description')).toBeInTheDocument()
    })
  })

  it('deletes branch', async () => {
    vi.mocked(api.listBranches).mockResolvedValue({
      session_id: 'test',
      branches: mockBranches,
    })

    vi.mocked(api.deleteBranch).mockResolvedValue({
      session_id: 'test-session',
      branch_id: 'branch_1',
      success: true,
    })

    vi.mocked(api.listBranches).mockResolvedValue({
      session_id: 'test',
      branches: [],
    })

    render(<StepperPanel sessionId="test-session" />)

    // Switch to branches tab
    fireEvent.click(screen.getByText('Branches'))

    await waitFor(() => {
      expect(screen.getByText('Test Branch')).toBeInTheDocument()
    })

    // Click delete button
    const deleteButtons = screen.getAllByTitle('Delete branch')
    fireEvent.click(deleteButtons[0])

    await waitFor(() => {
      expect(api.deleteBranch).toHaveBeenCalledWith('test-session', 'branch_1')
    })
  })

  it('resets stepper', async () => {
    render(<StepperPanel sessionId="test-session" />)

    vi.mocked(api.resetStepper).mockResolvedValue({
      session_id: 'test-session',
      success: true,
      stepper_state: mockStepperState,
    })

    // Mock confirm dialog
    const confirmMock = vi.fn(() => true)
    globalThis.confirm = confirmMock

    fireEvent.click(screen.getByText('Reset'))

    await waitFor(() => {
      expect(api.resetStepper).toHaveBeenCalledWith('test-session')
    })
  })

  it('displays stepper status indicators', async () => {
    vi.mocked(api.getStepperState).mockResolvedValue({
      session_id: 'test',
      stepper_state: mockStepperState,
      agent_state: {
        ...mockAgentState,
        total_events: 10,
      },
    })

    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Position:')).toBeInTheDocument()
      expect(screen.getByText('1 / 10')).toBeInTheDocument()
      expect(screen.getByText('Status:')).toBeInTheDocument()
      expect(screen.getByText('Paused')).toBeInTheDocument()
      expect(screen.getByText('Breakpoints:')).toBeInTheDocument()
      expect(screen.getByText('0 active')).toBeInTheDocument()
    })
  })

  it('handles loading state', () => {
    vi.mocked(api.listBreakpoints).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    )

    render(<StepperPanel sessionId="test-session" />)

    expect(screen.getByText('Loading stepper state...')).toBeInTheDocument()
  })

  it('handles error state', async () => {
    vi.mocked(api.listBreakpoints).mockRejectedValue(
      new Error('Failed to load stepper state')
    )

    render(<StepperPanel sessionId="test-session" />)

    await waitFor(() => {
      expect(screen.getByText('Error: Failed to load stepper state')).toBeInTheDocument()
    })
  })
})