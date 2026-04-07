import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FailureClusterPanel } from '../components/FailureClusterPanel'
import type { FailureCluster, TraceAnalysisCluster, TraceEvent } from '../types'

// Helper function to create a test cluster
function createFailureCluster(overrides: Partial<FailureCluster> = {}): FailureCluster {
  return {
    id: 'cluster-1',
    fingerprint: 'RuntimeError: timeout after 30 seconds',
    session_count: 5,
    event_count: 12,
    avg_severity: 0.8,
    representative_session_id: 'session-1',
    sample_symptom: 'timeout error',
    ...overrides,
  }
}

// Helper function to create a test trace event
function createTraceEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: 'event-1',
    session_id: 'session-1',
    timestamp: '2026-04-07T10:00:00Z',
    event_type: 'error',
    parent_id: null,
    name: 'Runtime error',
    data: {},
    metadata: {},
    importance: 0.8,
    upstream_event_ids: [],
    error: 'timeout after 30 seconds',
    ...overrides,
  }
}

// Helper function to create a test analysis cluster
function createAnalysisCluster(overrides: Partial<TraceAnalysisCluster> = {}): TraceAnalysisCluster {
  return {
    fingerprint: 'RuntimeError: timeout after 30 seconds',
    count: 3,
    event_ids: ['event-1', 'event-2', 'event-3'],
    representative_event_id: 'event-1',
    max_composite: 0.85,
    ...overrides,
  }
}

describe('FailureClusterPanel', () => {
  it('renders empty state when no clusters provided', () => {
    const onSelectSession = vi.fn()
    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(screen.getByText('Failure Clusters')).toBeInTheDocument()
    expect(screen.getByText('Cross-session patterns')).toBeInTheDocument()
    expect(screen.getByText('No patterns detected')).toBeInTheDocument()
    expect(
      screen.getByText('Failure clusters group similar errors across sessions to help you spot systemic issues.')
    ).toBeInTheDocument()
  })

  it('renders cluster list with clusters provided', () => {
    const onSelectSession = vi.fn()
    const clusters = [
      createFailureCluster({
        id: 'cluster-1',
        fingerprint: 'RuntimeError: timeout',
        avg_severity: 0.8,
        session_count: 5,
        event_count: 12,
      }),
      createFailureCluster({
        id: 'cluster-2',
        fingerprint: 'ValueError: invalid input',
        avg_severity: 0.5,
        session_count: 3,
        event_count: 7,
      }),
    ]

    render(
      <FailureClusterPanel
        clusters={clusters}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(screen.getByText('Cross-session patterns (2)')).toBeInTheDocument()
    expect(screen.getByText('RuntimeError: timeout')).toBeInTheDocument()
    expect(screen.getByText('ValueError: invalid input')).toBeInTheDocument()
  })

  it('displays cluster details correctly', () => {
    const onSelectSession = vi.fn()
    const cluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'RuntimeError: timeout after 30 seconds',
      session_count: 5,
      event_count: 12,
      avg_severity: 0.8,
      sample_symptom: 'Connection timeout',
    })

    render(
      <FailureClusterPanel
        clusters={[cluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    // Check fingerprint
    expect(screen.getByText('RuntimeError: timeout after 30 seconds')).toBeInTheDocument()

    // Check severity
    expect(screen.getByText('High severity')).toBeInTheDocument()

    // Check metrics
    expect(screen.getByText('Sessions')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('Events')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
    expect(screen.getByText('0.80')).toBeInTheDocument()

    // Check symptom
    expect(screen.getByText('Connection timeout')).toBeInTheDocument()
  })

  it('shows correct severity labels and colors', () => {
    const onSelectSession = vi.fn()
    const clusters = [
      createFailureCluster({ id: 'cluster-1', avg_severity: 0.8, fingerprint: 'High' }),
      createFailureCluster({ id: 'cluster-2', avg_severity: 0.5, fingerprint: 'Medium' }),
      createFailureCluster({ id: 'cluster-3', avg_severity: 0.2, fingerprint: 'Low' }),
    ]

    render(
      <FailureClusterPanel
        clusters={clusters}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(screen.getByText('High severity')).toBeInTheDocument()
    expect(screen.getByText('Medium severity')).toBeInTheDocument()
    expect(screen.getByText('Low severity')).toBeInTheDocument()
  })

  it('handles onSelectSession callback', async () => {
    const onSelectSession = vi.fn()
    const cluster = createFailureCluster({
      id: 'cluster-1',
      representative_session_id: 'session-123',
      fingerprint: 'RuntimeError: timeout',
    })

    render(
      <FailureClusterPanel
        clusters={[cluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    const button = screen.getByRole('button', {
      name: /failure cluster: RuntimeError: timeout/i,
    })
    await userEvent.click(button)

    expect(onSelectSession).toHaveBeenCalledWith('session-123')
  })

  it('highlights selected session', () => {
    const onSelectSession = vi.fn()
    const cluster = createFailureCluster({
      id: 'cluster-1',
      representative_session_id: 'session-123',
      fingerprint: 'RuntimeError: timeout',
    })

    render(
      <FailureClusterPanel
        clusters={[cluster]}
        onSelectSession={onSelectSession}
        selectedSessionId="session-123"
      />
    )

    const button = screen.getByRole('button', {
      name: /failure cluster: RuntimeError: timeout/i,
    })
    expect(button).toHaveClass('active')
  })

  it('truncates long fingerprints when derived from analysis clusters', () => {
    const onSelectSession = vi.fn()
    const longFingerprint = 'a'.repeat(100)
    const events = [createTraceEvent({ id: 'event-1', error: longFingerprint })]
    const analysisClusters = [
      createAnalysisCluster({
        fingerprint: longFingerprint,
        representative_event_id: 'event-1',
      }),
    ]

    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
        analysisClusters={analysisClusters}
        events={events}
      />
    )

    // The fingerprint should be truncated to 60 chars + ellipsis
    const truncatedText = `${'a'.repeat(60)}...`
    expect(screen.getByText(truncatedText)).toBeInTheDocument()

    // The full text should not be visible in the element text content
    // (it may still be in the title attribute)
    const fingerprintElement = screen.getByText(truncatedText)
    expect(fingerprintElement.textContent).toBe(truncatedText)
  })

  it('shows suggested action based on error type', () => {
    const onSelectSession = vi.fn()

    // Test timeout error
    const timeoutCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'timeout',
      sample_symptom: 'Request timed out after 30 seconds',
    })

    render(
      <FailureClusterPanel
        clusters={[timeoutCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(
      screen.getByText('Suggested action: Check network latency and timeout configuration')
    ).toBeInTheDocument()
  })

  it('shows suggested action for auth errors', () => {
    const onSelectSession = vi.fn()
    const authCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'auth error',
      sample_symptom: '401 Unauthorized',
    })

    render(
      <FailureClusterPanel
        clusters={[authCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(
      screen.getByText('Suggested action: Verify API keys and token expiration')
    ).toBeInTheDocument()
  })

  it('shows suggested action for rate limit errors', () => {
    const onSelectSession = vi.fn()
    const rateLimitCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'rate limit',
      sample_symptom: '429 Too Many Requests',
    })

    render(
      <FailureClusterPanel
        clusters={[rateLimitCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(
      screen.getByText('Suggested action: Consider adding retry logic or request throttling')
    ).toBeInTheDocument()
  })

  it('shows suggested action for validation errors', () => {
    const onSelectSession = vi.fn()
    const validationCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'validation error',
      sample_symptom: 'Validation failed: invalid schema',
    })

    render(
      <FailureClusterPanel
        clusters={[validationCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
    />
    )

    expect(
      screen.getByText("Suggested action: Review input sanitization and schema validation")
    ).toBeInTheDocument()
  })

  it('shows default suggested action for unknown errors', () => {
    const onSelectSession = vi.fn()
    const unknownCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'unknown error',
      sample_symptom: 'Something went wrong',
    })

    render(
      <FailureClusterPanel
        clusters={[unknownCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(
      screen.getByText('Suggested action: Review the error details and stack trace above')
    ).toBeInTheDocument()
  })

  it('shows default suggested action when no symptom', () => {
    const onSelectSession = vi.fn()
    const noSymptomCluster = createFailureCluster({
      id: 'cluster-1',
      fingerprint: 'no symptom',
      sample_symptom: null,
    })

    render(
      <FailureClusterPanel
        clusters={[noSymptomCluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(
      screen.getByText('Suggested action: Review the error details and stack trace above')
    ).toBeInTheDocument()
  })

  it('derives clusters from analysis clusters when clusters prop is empty', () => {
    const onSelectSession = vi.fn()
    const events = [
      createTraceEvent({
        id: 'event-1',
        session_id: 'session-1',
        error: 'timeout error',
      }),
    ]
    const analysisClusters = [
      createAnalysisCluster({
        fingerprint: 'RuntimeError: timeout',
        count: 5,
        representative_event_id: 'event-1',
        max_composite: 0.75,
      }),
    ]

    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
        analysisClusters={analysisClusters}
        events={events}
      />
    )

    expect(screen.getByText('RuntimeError: timeout')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument() // event count from cluster
  })

  it('shows representative event type when available', () => {
    const onSelectSession = vi.fn()

    const events = [
      createTraceEvent({
        id: 'event-1',
        session_id: 'session-1',
        event_type: 'llm_request',
      }),
    ]

    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
        analysisClusters={[
          createAnalysisCluster({
            representative_event_id: 'event-1',
          }),
        ]}
        events={events}
      />
    )

    expect(screen.getByText('Representative')).toBeInTheDocument()
    expect(screen.getByText(/llm request/i)).toBeInTheDocument()
  })

  it('shows "View representative session" link', () => {
    const onSelectSession = vi.fn()
    const cluster = createFailureCluster({
      id: 'cluster-1',
      representative_session_id: 'session-123',
    })

    render(
      <FailureClusterPanel
        clusters={[cluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    expect(screen.getByText('View representative session')).toBeInTheDocument()
  })

  it('sorts clusters by severity (highest first)', () => {
    const onSelectSession = vi.fn()
    const clusters = [
      createFailureCluster({ id: 'cluster-1', avg_severity: 0.3, fingerprint: 'Low' }),
      createFailureCluster({ id: 'cluster-2', avg_severity: 0.9, fingerprint: 'High' }),
      createFailureCluster({ id: 'cluster-3', avg_severity: 0.5, fingerprint: 'Medium' }),
    ]

    render(
      <FailureClusterPanel
        clusters={clusters}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    const clusterElements = screen.getAllByRole('button', { name: /failure cluster:/i })
    expect(clusterElements[0]).toHaveTextContent('High')
    expect(clusterElements[1]).toHaveTextContent('Medium')
    expect(clusterElements[2]).toHaveTextContent('Low')
  })

  it('handles cluster without sample symptom gracefully', () => {
    const onSelectSession = vi.fn()
    const cluster = createFailureCluster({
      id: 'cluster-1',
      sample_symptom: null,
    })

    render(
      <FailureClusterPanel
        clusters={[cluster]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />
    )

    // Should not crash and should show default action
    expect(
      screen.getByText('Suggested action: Review the error details and stack trace above')
    ).toBeInTheDocument()
  })

  it('handles analysis cluster with missing representative event', () => {
    const onSelectSession = vi.fn()
    const analysisClusters = [
      createAnalysisCluster({
        representative_event_id: 'non-existent-event',
      }),
    ]

    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
        analysisClusters={analysisClusters}
        events={[]}
      />
    )

    // Should not crash
    expect(screen.getByText('Cross-session patterns (1)')).toBeInTheDocument()
  })

  it('handles empty events array gracefully', () => {
    const onSelectSession = vi.fn()

    render(
      <FailureClusterPanel
        clusters={[]}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
        analysisClusters={[]}
        events={[]}
      />
    )

    expect(screen.getByText('No patterns detected')).toBeInTheDocument()
  })
})
