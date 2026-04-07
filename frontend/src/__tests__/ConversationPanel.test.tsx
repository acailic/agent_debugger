import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConversationPanel } from '../components/ConversationPanel'
import type { TraceEvent } from '../types'

// Helper function to create test events
function createTestEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: `event-${Math.random().toString(36).substr(2, 9)}`,
    session_id: 'test-session',
    timestamp: new Date().toISOString(),
    event_type: 'agent_turn',
    parent_id: null,
    name: 'Test Event',
    data: {},
    metadata: {},
    importance: 0.5,
    upstream_event_ids: [],
    ...overrides,
  }
}

// Helper to create agent turn event
function createAgentTurn(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return createTestEvent({
    event_type: 'agent_turn',
    speaker: 'Agent',
    goal: 'Complete task',
    ...overrides,
  })
}

// Helper to create prompt policy event
function createPromptPolicy(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return createTestEvent({
    event_type: 'prompt_policy',
    template_id: 'default_policy',
    goal: 'Follow guidelines',
    policy_parameters: { temperature: 0.7 },
    ...overrides,
  })
}

describe('ConversationPanel', () => {
  it('renders with empty events list', () => {
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={[]}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('Conversation and policy')).toBeInTheDocument()
    expect(screen.getByText('No agent turns captured')).toBeInTheDocument()
  })

  it('renders event items when events are provided', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Use getAllByText since speakers and goals appear in multiple places
    expect(screen.getAllByText('Alice')).toHaveLength(3)
    expect(screen.getAllByText('Bob')).toHaveLength(3)
    expect(screen.getAllByText('Task 1')).toHaveLength(2)
    expect(screen.getAllByText('Task 2')).toHaveLength(2)
  })

  it('handles click events on event items', async () => {
    const user = userEvent.setup()
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Find the conversation row button (not the filter buttons)
    const eventButtons = screen.getAllByRole('button')
    const conversationRowButton = eventButtons.find(btn =>
      btn.classList.contains('conversation-row')
    )

    if (conversationRowButton) {
      await user.click(conversationRowButton)
      expect(onSelectEvent).toHaveBeenCalledWith('event-1')
    }
  })

  it('shows correct event type labels', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice' }),
      createPromptPolicy({ id: 'event-2', template_id: 'strict_policy' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('agent turn')).toBeInTheDocument()
    expect(screen.getByText('prompt policy')).toBeInTheDocument()
  })

  it('highlights selected event', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    const { container } = render(
      <ConversationPanel
        events={events}
        selectedEventId="event-1"
        onSelectEvent={onSelectEvent}
      />
    )

    // Find the active conversation row
    const activeButton = container.querySelector('.conversation-row.active')
    expect(activeButton).toBeInTheDocument()
  })

  it('handles single event gracefully', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
    ]
    const onSelectEvent = vi.fn()

    const { container } = render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const conversationList = container.querySelector('.conversation-list')
    expect(conversationList).toHaveClass('conversation-list--single')
  })

  it('handles many events', () => {
    const events = Array.from({ length: 10 }, (_, i) =>
      createAgentTurn({
        id: `event-${i}`,
        speaker: `Agent${i}`,
        goal: `Task ${i}`,
      })
    )
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('10 turns')).toBeInTheDocument()
    // Check a few representative agents - they appear in multiple places
    expect(screen.getAllByText('Agent0')).toHaveLength(3)
    expect(screen.getAllByText('Agent5')).toHaveLength(3)
    expect(screen.getAllByText('Agent9')).toHaveLength(3)
  })

  it('renders speaker filter pills when speakers exist', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('Filter by speaker:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bob' })).toBeInTheDocument()
  })

  it('renders policy filter pills when policies exist', () => {
    const events = [
      createPromptPolicy({ id: 'policy-1', template_id: 'strict' }),
      createAgentTurn({ id: 'event-1', speaker: 'Alice' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('Filter by policy:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'strict' })).toBeInTheDocument()
  })

  it('displays policy badge when active policy exists', () => {
    const events = [
      createPromptPolicy({ id: 'policy-1', template_id: 'strict', speaker: 'Alice' }),
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Policy badge appears twice (once in policy event, once in agent turn)
    expect(screen.getAllByText(/📋 strict/)).toHaveLength(2)
  })

  it('displays content when present', () => {
    const events = [
      createAgentTurn({
        id: 'event-1',
        speaker: 'Alice',
        content: 'This is the event content',
      }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('This is the event content')).toBeInTheDocument()
  })

  it('shows turn goal when present', () => {
    const events = [
      createAgentTurn({
        id: 'event-1',
        speaker: 'Alice',
        goal: 'Accomplish objective',
      }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Goal appears in both the p tag and the turn-goal div
    expect(screen.getAllByText('Accomplish objective')).toHaveLength(2)
  })

  it('displays metrics correctly', () => {
    const events = [
      createPromptPolicy({ id: 'policy-1', template_id: 'strict' }),
      createAgentTurn({ id: 'event-1', speaker: 'Alice' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText('2 turns')).toBeInTheDocument()
    expect(screen.getByText('1 prompt policies')).toBeInTheDocument()
    expect(screen.getByText('2 speakers')).toBeInTheDocument()
  })

  it('filters events by speaker', async () => {
    const user = userEvent.setup()
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    const { container } = render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const aliceButton = screen.getByRole('button', { name: 'Alice' })
    await user.click(aliceButton)

    // After filtering, only Alice's task should be visible
    const task1Elements = screen.getAllByText('Task 1')
    expect(task1Elements.length).toBeGreaterThan(0)

    // Bob's task should not be in the filtered conversation list
    const conversationList = container.querySelector('.conversation-list')
    expect(conversationList).not.toContainHTML('Task 2')
  })

  it('filters events by policy template', async () => {
    const user = userEvent.setup()
    const events = [
      createPromptPolicy({ id: 'policy-1', template_id: 'strict', speaker: 'Alice' }),
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    const { container } = render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const strictButton = screen.getByRole('button', { name: 'strict' })
    await user.click(strictButton)

    // After filtering, only Alice's task (with strict policy) should be visible
    const task1Elements = screen.getAllByText('Task 1')
    expect(task1Elements.length).toBeGreaterThan(0)

    // Bob's task should not be in the filtered conversation list
    const conversationList = container.querySelector('.conversation-list')
    expect(conversationList).not.toContainHTML('Task 2')
  })

  it('toggles speaker filter on and off', async () => {
    const user = userEvent.setup()
    const events = [
      createAgentTurn({ id: 'event-1', speaker: 'Alice', goal: 'Task 1' }),
      createAgentTurn({ id: 'event-2', speaker: 'Bob', goal: 'Task 2' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Click Alice filter to activate
    const aliceButton = screen.getByRole('button', { name: 'Alice' })
    await user.click(aliceButton)

    // Alice button should now be active
    expect(aliceButton).toHaveClass('active')

    // Click again to deactivate
    await user.click(aliceButton)

    // Alice button should no longer be active
    expect(aliceButton).not.toHaveClass('active')
  })

  it('displays policy parameters for prompt policy events', () => {
    const events = [
      createPromptPolicy({
        id: 'policy-1',
        template_id: 'strict',
        policy_parameters: { temperature: 0.7, max_tokens: 100 },
      }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    expect(screen.getByText(/"temperature": 0.7/)).toBeInTheDocument()
    expect(screen.getByText(/"max_tokens": 100/)).toBeInTheDocument()
  })

  it('handles events without speaker gracefully', () => {
    const events = [
      createAgentTurn({ id: 'event-1', speaker: undefined, agent_id: 'agent-1', goal: 'Task 1' }),
    ]
    const onSelectEvent = vi.fn()

    render(
      <ConversationPanel
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // agent-1 appears in multiple places (filter button, speaker pill, conversation row)
    expect(screen.getAllByText('agent-1')).toHaveLength(3)
  })
})
