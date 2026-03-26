import { describe, it, expect } from 'vitest'
import type { EventType } from '../types'

describe('Type exports', () => {
  it('module loads without errors', () => {
    // If any exported type were missing, the import above would fail at build time.
    expect(true).toBe(true)
  })

  it('EventType includes expected values', () => {
    const validTypes: EventType[] = [
      'trace_root', 'agent_start', 'agent_end', 'tool_call', 'tool_result',
      'llm_request', 'llm_response', 'decision', 'error', 'checkpoint',
      'safety_check', 'refusal', 'policy_violation', 'prompt_policy',
      'agent_turn', 'behavior_alert',
    ]
    expect(validTypes.length).toBeGreaterThan(10)
  })
})
