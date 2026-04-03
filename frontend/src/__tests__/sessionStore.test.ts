import { describe, expect, it } from 'vitest'
import { buildReplayBreakpointParams } from '../stores/sessionStore'

describe('buildReplayBreakpointParams', () => {
  it('normalizes csv breakpoint config into replay params', () => {
    expect(
      buildReplayBreakpointParams({
        breakpointEventTypes: ' error, decision ,, refusal ',
        breakpointToolNames: 'search, lookup',
        breakpointConfidenceBelow: '0.45',
        breakpointSafetyOutcomes: 'warn, block',
        stopAtBreakpoint: true,
      }),
    ).toEqual({
      breakpointEventTypes: ['error', 'decision', 'refusal'],
      breakpointToolNames: ['search', 'lookup'],
      breakpointConfidenceBelow: 0.45,
      breakpointSafetyOutcomes: ['warn', 'block'],
      stopAtBreakpoint: true,
    })
  })

  it('returns null confidence when the threshold is blank', () => {
    expect(
      buildReplayBreakpointParams({
        breakpointEventTypes: '',
        breakpointToolNames: '',
        breakpointConfidenceBelow: ' ',
        breakpointSafetyOutcomes: '',
        stopAtBreakpoint: false,
      }),
    ).toEqual({
      breakpointEventTypes: [],
      breakpointToolNames: [],
      breakpointConfidenceBelow: null,
      breakpointSafetyOutcomes: [],
      stopAtBreakpoint: false,
    })
  })

  it('returns null confidence when the threshold is not numeric', () => {
    expect(
      buildReplayBreakpointParams({
        breakpointEventTypes: 'error',
        breakpointToolNames: '',
        breakpointConfidenceBelow: 'abc',
        breakpointSafetyOutcomes: '',
        stopAtBreakpoint: true,
      }),
    ).toMatchObject({
      breakpointConfidenceBelow: null,
    })
  })
})
