import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReplayBar } from '../components/ReplayBar'
import { useSessionStore } from '../stores/sessionStore'

describe('ReplayBar', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useSessionStore.getState().reset()
  })

  it('renders persisted breakpoint settings from the store', () => {
    useSessionStore.getState().setBreakpointEventTypes('error,decision')
    useSessionStore.getState().setBreakpointConfidenceBelow('0.25')

    render(<ReplayBar />)

    expect(screen.getByLabelText('Event breakpoints')).toHaveValue('error,decision')
    expect(screen.getByLabelText('Confidence floor')).toHaveValue('0.25')
  })

  it('updates store and localStorage when breakpoint inputs change', async () => {
    render(<ReplayBar />)

    await userEvent.clear(screen.getByLabelText('Event breakpoints'))
    await userEvent.type(screen.getByLabelText('Event breakpoints'), 'error,tool_call')
    await userEvent.clear(screen.getByLabelText('Tool breakpoints'))
    await userEvent.type(screen.getByLabelText('Tool breakpoints'), 'search,lookup')
    await userEvent.clear(screen.getByLabelText('Confidence floor'))
    await userEvent.type(screen.getByLabelText('Confidence floor'), '0.30')
    await userEvent.click(screen.getByLabelText('Stop at breakpoint'))

    const state = useSessionStore.getState()
    expect(state.breakpointEventTypes).toBe('error,tool_call')
    expect(state.breakpointToolNames).toBe('search,lookup')
    expect(state.breakpointConfidenceBelow).toBe('0.30')
    expect(state.stopAtBreakpoint).toBe(false)

    expect(window.localStorage.getItem('peaky-peek:breakpoint-event-types')).toBe('error,tool_call')
    expect(window.localStorage.getItem('peaky-peek:breakpoint-tool-names')).toBe('search,lookup')
    expect(window.localStorage.getItem('peaky-peek:breakpoint-confidence-below')).toBe('0.30')
    expect(window.localStorage.getItem('peaky-peek:stop-at-breakpoint')).toBe('false')
  })

  it('applies quick breakpoint presets to the shared replay config', async () => {
    render(<ReplayBar />)

    await userEvent.click(screen.getByRole('button', { name: 'Safety' }))

    let state = useSessionStore.getState()
    expect(state.breakpointEventTypes).toBe('')
    expect(state.breakpointToolNames).toBe('')
    expect(state.breakpointConfidenceBelow).toBe('')
    expect(state.breakpointSafetyOutcomes).toBe('warn,block')
    expect(state.stopAtBreakpoint).toBe(true)

    await userEvent.click(screen.getByRole('button', { name: 'Tools' }))

    state = useSessionStore.getState()
    expect(state.breakpointEventTypes).toBe('tool_call,tool_result')
    expect(state.breakpointSafetyOutcomes).toBe('')
    expect(state.breakpointConfidenceBelow).toBe('')
    expect(state.stopAtBreakpoint).toBe(true)
  })
})
