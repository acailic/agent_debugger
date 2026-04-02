import { describe, it, expect } from 'vitest'
import { computeHealthScore, getHealthGrade } from '../healthScore'
import type { Session } from '../../types'

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-1',
    agent_name: 'test-agent',
    framework: 'openai',
    started_at: '2025-01-01T00:00:00Z',
    ended_at: null,
    status: 'running',
    total_tokens: 0,
    total_cost_usd: 0,
    tool_calls: 0,
    llm_calls: 0,
    errors: 0,
    config: {},
    tags: [],
    ...overrides,
  }
}

const makeBundle = (alertCount = 0) => ({
  analysis: {
    session_summary: {
      failure_count: 0,
      behavior_alert_count: alertCount,
    },
  },
})

// ---------------------------------------------------------------------------
// computeHealthScore
// ---------------------------------------------------------------------------
describe('computeHealthScore', () => {
  it('returns 100 for a pristine running session with no bundle', () => {
    const session = makeSession()
    expect(computeHealthScore(session)).toBe(100)
  })

  it('clamps completed session bonus to 100', () => {
    // 100 base + 5 completed bonus = 105, but clamped to 100
    const session = makeSession({ status: 'completed' })
    expect(computeHealthScore(session)).toBe(100)
  })

  it('returns 80 for a running session with error status', () => {
    const session = makeSession({ status: 'error' })
    expect(computeHealthScore(session)).toBe(80)
  })

  it('deducts 10 points per error count from session.errors', () => {
    const session = makeSession({ errors: 3 })
    expect(computeHealthScore(session)).toBe(70) // 100 - 30
  })

  it('deducts 5 points per behavior alert from bundle', () => {
    const session = makeSession()
    expect(computeHealthScore(session, makeBundle(4))).toBe(80) // 100 - 20
  })

  it('falls back to session.behavior_alert_count when bundle is absent', () => {
    const session = makeSession({ behavior_alert_count: 2 })
    expect(computeHealthScore(session)).toBe(90) // 100 - 10
  })

  it('prefers bundle alert count over session field', () => {
    const session = makeSession({ behavior_alert_count: 10 })
    const bundle = makeBundle(1)
    expect(computeHealthScore(session, bundle)).toBe(95) // 100 - 5
  })

  it('adds replay value bonus but result is clamped to 100', () => {
    // 100 base + min(2*2, 10) = 104, but clamped to 100 since already at cap
    const lowReplay = makeSession({ replay_value: 2 })
    expect(computeHealthScore(lowReplay)).toBe(100)

    // 100 base + min(10*2, 10) = 110, but clamped to 100
    const highReplay = makeSession({ replay_value: 10 })
    expect(computeHealthScore(highReplay)).toBe(100)
  })

  it('replay bonus can offset penalties below 100', () => {
    // 100 - 10 (1 error) + min(2*2, 10) = 94
    const session = makeSession({ errors: 1, replay_value: 2 })
    expect(computeHealthScore(session)).toBe(94)
  })

  it('clamps score to a minimum of 0', () => {
    const session = makeSession({ errors: 20, status: 'error' })
    // 100 - 200 - 20 = -120 -> clamped to 0
    expect(computeHealthScore(session)).toBe(0)
  })

  it('clamps score to a maximum of 100', () => {
    const session = makeSession({
      status: 'completed',
      replay_value: 100,
    })
    // 100 + 10 (cap) + 5 = 115 -> clamped to 100
    expect(computeHealthScore(session)).toBe(100)
  })

  it('combines all penalties and bonuses correctly', () => {
    const session = makeSession({
      status: 'error',
      errors: 2,
      replay_value: 3,
      behavior_alert_count: 1,
    })
    // 100 - 20 (errors) - 5 (alerts) + 6 (replay) - 20 (error status) = 61
    expect(computeHealthScore(session)).toBe(61)
  })

  it('treats undefined optional fields as zero', () => {
    const session = makeSession({
      errors: undefined as unknown as number,
      replay_value: undefined as unknown as number,
      behavior_alert_count: undefined as unknown as number,
    })
    expect(computeHealthScore(session)).toBe(100)
  })
})

// ---------------------------------------------------------------------------
// getHealthGrade
// ---------------------------------------------------------------------------
describe('getHealthGrade', () => {
  it('returns grade A for score >= 90', () => {
    const result = getHealthGrade(95)
    expect(result).toEqual({ grade: 'A', color: '#10b981', label: 'Excellent' })
  })

  it('returns grade A for score exactly 90', () => {
    expect(getHealthGrade(90).grade).toBe('A')
  })

  it('returns grade B for score >= 80', () => {
    const result = getHealthGrade(85)
    expect(result).toEqual({ grade: 'B', color: '#22c55e', label: 'Good' })
  })

  it('returns grade B for score exactly 80', () => {
    expect(getHealthGrade(80).grade).toBe('B')
  })

  it('returns grade C for score >= 70', () => {
    const result = getHealthGrade(75)
    expect(result).toEqual({ grade: 'C', color: '#f59e0b', label: 'Fair' })
  })

  it('returns grade D for score >= 60', () => {
    const result = getHealthGrade(65)
    expect(result).toEqual({ grade: 'D', color: '#f97316', label: 'Poor' })
  })

  it('returns grade F for score below 60', () => {
    const result = getHealthGrade(30)
    expect(result).toEqual({ grade: 'F', color: '#ef4444', label: 'Critical' })
  })

  it('returns grade F for score of 0', () => {
    expect(getHealthGrade(0).grade).toBe('F')
  })

  it('returns grade A for score of 100', () => {
    expect(getHealthGrade(100).grade).toBe('A')
  })

  it('each grade has a unique color', () => {
    const grades = [100, 85, 75, 65, 30].map(getHealthGrade)
    const colors = new Set(grades.map((g) => g.color))
    expect(colors.size).toBe(5)
  })
})
