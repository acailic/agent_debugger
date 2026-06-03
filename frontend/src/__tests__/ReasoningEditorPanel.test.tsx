import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Mock } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReasoningEditorPanel } from '../components/ReasoningEditorPanel'
import type { TraceEvent } from '../types'

// Mock API calls with proper return values
const mockListScenarios = vi.fn().mockResolvedValue({
  session_id: 'session-1',
  scenarios: [],
  total_count: 0
})

vi.mock('../api/client', () => ({
  editReasoning: vi.fn(),
  createScenarioBranch: vi.fn(),
  getHierarchicalReasoning: vi.fn(),
  listScenarios: () => mockListScenarios(),
  compareScenarios: vi.fn(),
  exportScenario: vi.fn(),
}))

// Helper function to create a test event
function createTestEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: 'event-1',
    event_type: 'decision',
    timestamp: '2026-06-03T10:00:00Z',
    name: 'Test Decision',
    data: {},
    metadata: {},
    parent_id: null,
    upstream_event_ids: [],
    session_id: 'session-1',
    importance: 1.0,
    ...overrides,
  }
}

describe('ReasoningEditorPanel', () => {
  let mockOnError: Mock<(error: string) => void>
  let mockOnSuccess: Mock<(message: string) => void>

  beforeEach(() => {
    mockOnError = vi.fn() as Mock<(error: string) => void>
    mockOnSuccess = vi.fn() as Mock<(message: string) => void>
    // Reset mock before each test
    mockListScenarios.mockResolvedValue({
      session_id: 'session-1',
      scenarios: [],
      total_count: 0
    })
  })

  it('renders empty state when no session selected', () => {
    render(
      <ReasoningEditorPanel
        sessionId={null}
        events={[]}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    expect(screen.getByText('Select a session to edit reasoning and manage scenarios.')).toBeInTheDocument()
  })

  it('renders editor tabs when session is selected', () => {
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    expect(screen.getByText('Edit Reasoning')).toBeInTheDocument()
    expect(screen.getByText(/Scenarios \(/)).toBeInTheDocument()
    expect(screen.getByText('Hierarchy')).toBeInTheDocument()
    expect(screen.getByText('Compare')).toBeInTheDocument()
  })

  it('renders event selector with available events', () => {
    const events = [
      createTestEvent({ id: 'event-1', name: 'First Decision' }),
      createTestEvent({ id: 'event-2', name: 'Second Decision' }),
    ]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    expect(screen.getByText('Select an event...')).toBeInTheDocument()
    expect(screen.getByText('First Decision - decision')).toBeInTheDocument()
    expect(screen.getByText('Second Decision - decision')).toBeInTheDocument()
  })

  it('shows error when trying to edit without selecting event', async () => {
    const user = await userEvent.setup()
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    const applyButton = screen.getByRole('button', { name: 'Apply Edit' })
    await user.click(applyButton)

    expect(screen.getByText('Please select an event to edit')).toBeInTheDocument()
  })

  it('switches between tabs correctly', async () => {
    const user = await userEvent.setup()
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    // Click on Scenarios tab
    const scenariosTab = screen.getByText('Scenarios')
    await user.click(scenariosTab)

    expect(screen.getByText('Scenario Branches')).toBeInTheDocument()

    // Click on Hierarchy tab
    const hierarchyTab = screen.getByText('Hierarchy')
    await user.click(hierarchyTab)

    expect(screen.getByText('Load Hierarchy')).toBeInTheDocument()
  })

  it('renders empty state for scenarios when none exist', async () => {
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    // Switch to scenarios tab
    const scenariosTab = screen.getByText('Scenarios')
    await scenariosTab.click()

    await waitFor(() => {
      expect(screen.getByText('No scenario branches created yet. Create one from the Edit tab.')).toBeInTheDocument()
    })
  })

  it('disables edit button when no event is selected', () => {
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    const applyButton = screen.getByRole('button', { name: 'Apply Edit' })
    expect(applyButton).toBeDisabled()
  })

  it('enables edit button when event is selected', async () => {
    const user = await userEvent.setup()
    const events = [
      createTestEvent({ id: 'event-1', name: 'Test Decision' }),
    ]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    const eventSelectLabel = screen.getByLabelText('Select Event:')
    const eventSelect = eventSelectLabel.nextElementSibling as HTMLSelectElement
    await user.selectOptions(eventSelect, 'event-1')

    const applyButton = screen.getByRole('button', { name: 'Apply Edit' })
    expect(applyButton).not.toBeDisabled()
  })

  it('shows position input for insert operation', async () => {
    const user = await userEvent.setup()
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    // Select insert operation
    const operationSelectLabel = screen.getByLabelText('Operation:')
    const operationSelect = operationSelectLabel.nextElementSibling as HTMLSelectElement

    await user.selectOptions(operationSelect, 'insert')

    expect(screen.getByLabelText('Position:')).toBeInTheDocument()
  })

  it('shows new value textarea for non-delete operations', async () => {
    const user = await userEvent.setup()
    const events = [createTestEvent()]

    render(
      <ReasoningEditorPanel
        sessionId="session-1"
        events={events}
        onError={mockOnError}
        onSuccess={mockOnSuccess}
      />
    )

    expect(screen.getByPlaceholderText('Enter new reasoning content...')).toBeInTheDocument()

    // Switch to delete operation
    const operationSelectLabel = screen.getByLabelText('Operation:')
    const operationSelect = operationSelectLabel.nextElementSibling as HTMLSelectElement

    await user.selectOptions(operationSelect, 'delete')

    expect(screen.queryByPlaceholderText('Enter new reasoning content...')).not.toBeInTheDocument()
  })
})