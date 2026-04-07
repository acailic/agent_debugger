import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MultiAgentCoordinationPanel } from '../components/MultiAgentCoordinationPanel'
import type { TraceBundle, TraceEvent } from '../types'

const createMockSession = (id: string = 'session-1') => ({
  id,
  agent_name: 'TestAgent',
  framework: 'test-framework',
  started_at: '2024-01-01T10:00:00Z',
  ended_at: '2024-01-01T11:00:00Z',
  status: 'completed' as const,
  total_tokens: 1000,
  total_cost_usd: 0.01,
  tool_calls: 5,
  llm_calls: 10,
  errors: 0,
  config: {},
  tags: [],
})

const createMockEvent = (overrides: Partial<TraceEvent> = {}): TraceEvent => ({
  id: 'event-1',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:00:00Z',
  event_type: 'agent_turn',
  parent_id: null,
  name: 'Test Event',
  data: {},
  metadata: {},
  importance: 0.5,
  upstream_event_ids: [],
  ...overrides,
})

const createMockAnalysis = () => ({
  event_rankings: [],
  failure_clusters: [],
  representative_failure_ids: [],
  high_replay_value_ids: [],
  failure_explanations: [],
  checkpoint_rankings: [],
  session_replay_value: 0.5,
  retention_tier: 'full' as const,
  session_summary: {
    failure_count: 0,
    behavior_alert_count: 0,
    high_severity_count: 0,
    checkpoint_count: 0,
  },
  live_summary: {
    event_count: 0,
    checkpoint_count: 0,
    latest: {
      decision_event_id: null,
      tool_event_id: null,
      safety_event_id: null,
      turn_event_id: null,
      policy_event_id: null,
      checkpoint_id: null,
    },
    rolling_summary: '',
    recent_alerts: [],
  },
  behavior_alerts: [],
  highlights: [],
})

const createMockBundle = (events: TraceEvent[]): TraceBundle => ({
  session: createMockSession(),
  events,
  checkpoints: [],
  tree: null,
  analysis: createMockAnalysis(),
})

describe('MultiAgentCoordinationPanel', () => {
  it('renders empty state when bundle is null', () => {
    render(<MultiAgentCoordinationPanel bundle={null} />)

    expect(screen.getByText('Multi-Agent Coordination')).toBeInTheDocument()
    expect(screen.getByText('Speaker patterns')).toBeInTheDocument()
    expect(screen.getByText('👥')).toBeInTheDocument()
    expect(screen.getByText('No session data available')).toBeInTheDocument()
    expect(screen.getByText('Select a session with multiple agents or speakers to view coordination patterns.')).toBeInTheDocument()
  })

  it('renders empty state when bundle has no events', () => {
    const bundle = createMockBundle([])
    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Multi-Agent Coordination')).toBeInTheDocument()
    expect(screen.getByText('Speaker patterns')).toBeInTheDocument()
    expect(screen.getByText('🔗')).toBeInTheDocument()
    expect(screen.getByText('No coordination data available')).toBeInTheDocument()
    expect(screen.getByText('This session has no agent turns, policy templates, or coordination events to analyze.')).toBeInTheDocument()
  })

  it('renders coordination metrics with agent turn events', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
        goal: 'Complete task',
        content: 'Working on task',
      }),
      createMockEvent({
        id: 'turn-2',
        event_type: 'agent_turn',
        speaker: 'Agent B',
        turn_index: 1,
        goal: 'Review work',
        content: 'Reviewing task',
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Multi-Agent Coordination')).toBeInTheDocument()
    expect(screen.getByText('Speaker patterns')).toBeInTheDocument()
    expect(screen.getByText('Total turns')).toBeInTheDocument()
    expect(screen.getByText('Speakers')).toBeInTheDocument()
    expect(screen.getAllByText('2')).toHaveLength(2)
  })

  it('renders speaker topology with multiple speakers', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'turn-2',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 1,
      }),
      createMockEvent({
        id: 'turn-3',
        event_type: 'agent_turn',
        speaker: 'Agent B',
        turn_index: 2,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Speaker topology')).toBeInTheDocument()
    const agentANames = screen.getAllByText('Agent A')
    const agentBNames = screen.getAllByText('Agent B')
    expect(agentANames.length).toBeGreaterThan(0)
    expect(agentBNames.length).toBeGreaterThan(0)
  })

  it('renders turn timeline strip', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'turn-2',
        event_type: 'agent_turn',
        speaker: 'Agent B',
        turn_index: 1,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Turn sequence')).toBeInTheDocument()
  })

  it('renders policy templates when present', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-1',
        event_type: 'prompt_policy',
        template_id: 'policy-template-1',
        name: 'Policy 1',
        turn_index: 0,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Policy templates')).toBeInTheDocument()
    expect(screen.getByText('policy-template-1')).toBeInTheDocument()
  })

  it('displays escalation count when escalations are detected', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
        goal: 'ESCALATE: Need help',
        content: 'This is urgent',
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Escalations')).toBeInTheDocument()
    const escalationValues = screen.getAllByText('1')
    expect(escalationValues.length).toBeGreaterThan(0)
  })

  it('displays stance shifts when policy templates change', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-1',
        event_type: 'prompt_policy',
        template_id: 'policy-template-1',
        name: 'Policy 1',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-2',
        event_type: 'prompt_policy',
        template_id: 'policy-template-2',
        name: 'Policy 2',
        turn_index: 1,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Stance shifts')).toBeInTheDocument()
    const stanceShiftValues = screen.getAllByText('1')
    expect(stanceShiftValues.length).toBeGreaterThan(0)
  })

  it('displays evidence grounding metrics with decisions', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'decision-1',
        event_type: 'decision',
        evidence_event_ids: ['ev1', 'ev2'],
      }),
      createMockEvent({
        id: 'decision-2',
        event_type: 'decision',
        evidence_event_ids: [],
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Evidence grounding')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('(1/2)')).toBeInTheDocument()
  })

  it('displays policies count', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-1',
        event_type: 'prompt_policy',
        template_id: 'policy-1',
        name: 'Policy 1',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-2',
        event_type: 'prompt_policy',
        template_id: 'policy-2',
        name: 'Policy 2',
        turn_index: 1,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Policies')).toBeInTheDocument()
    const policyValues = screen.getAllByText('2')
    expect(policyValues.length).toBeGreaterThan(0)
  })

  it('renders turn legend with escalation indicator when escalations exist', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
        goal: 'ESCALATE: Need help',
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    expect(screen.getByText('Escalation')).toBeInTheDocument()
  })

  it('renders turn legend with policy shift indicator when policy shifts exist', () => {
    const events = [
      createMockEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'turn-2',
        event_type: 'agent_turn',
        speaker: 'Agent A',
        turn_index: 1,
      }),
      createMockEvent({
        id: 'policy-1',
        event_type: 'prompt_policy',
        template_id: 'policy-1',
        name: 'Policy 1',
        turn_index: 0,
      }),
      createMockEvent({
        id: 'policy-2',
        event_type: 'prompt_policy',
        template_id: 'policy-2',
        name: 'Policy 2',
        turn_index: 1,
      }),
    ]
    const bundle = createMockBundle(events)

    render(<MultiAgentCoordinationPanel bundle={bundle} />)

    const policyShiftLabels = screen.queryAllByText('Policy shift')
    expect(policyShiftLabels.length).toBeGreaterThan(0)
  })
})
