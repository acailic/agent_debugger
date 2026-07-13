import { describe, it, expect } from 'vitest'
import {
  deriveAuditAnnotations,
  annotationRank,
  annotationTooltip,
} from '../auditAnnotations'
import type { SessionAuditReport } from '../../types'

// ---------------------------------------------------------------------------
// Helpers

function baseReport(overrides: Partial<SessionAuditReport> = {}): SessionAuditReport {
  return {
    session_id: 's1',
    objective: 'do the thing',
    final_outcome: 'done',
    // The util only reads claims/signals/failures; the 5-questions body is irrelevant here,
    // so cast an empty object rather than constructing the full AuditQuestions graph.
    questions: {} as SessionAuditReport['questions'],
    claims: [],
    signals: [],
    failures: [],
    critical_decisions: [],
    trust: {
      score: 0.5,
      band: 'medium',
      components: {},
      explanation: '',
    },
    review_points: [],
    summary: {
      verdict: 'review',
      tldr: 'tldr',
      trust_line: 'trust line',
      markdown: '',
    },
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// deriveAuditAnnotations

describe('deriveAuditAnnotations', () => {
  it('returns empty map for null/undefined report', () => {
    expect(deriveAuditAnnotations(null).size).toBe(0)
    expect(deriveAuditAnnotations(undefined).size).toBe(0)
  })

  it('aggregates claim + signal + failure for the same event into one annotation', () => {
    const report = baseReport({
      claims: [
        {
          event_id: 'e1',
          event_type: 'decision',
          headline: 'd',
          claim: 'c',
          rationale: 'r',
          confidence: 0.9,
          alternatives_considered: 0,
          evidence_refs: [],
          evidence_sources: [],
          verification_status: 'unsupported',
          verification_basis: '',
          contradicted: false,
          timestamp: '',
        },
      ],
      signals: [
        {
          event_id: 'e1',
          type: 'missing_evidence',
          severity: 'high',
          message: 'no evidence',
        },
      ],
      failures: [
        {
          event_id: 'e1',
          event_type: 'tool_call',
          headline: 'h',
          mode: 'tool_misuse',
          symptom: 'bad',
          likely_cause: 'x',
          likely_cause_event_id: null,
          confidence: 0.8,
          supporting_event_ids: [],
          position: 0,
        },
      ],
    })

    const map = deriveAuditAnnotations(report)
    expect(map.size).toBe(1)
    const annotation = map.get('e1')!
    expect(annotation.verificationStatus).toBe('unsupported')
    expect(annotation.failureMode).toBe('tool_misuse')
    expect(annotation.signalTypes).toEqual(['missing_evidence'])
    expect(annotation.topSignalSeverity).toBe('high')
  })

  it('dedupes repeated signal types and keeps the highest severity', () => {
    const report = baseReport({
      signals: [
        { event_id: 'e2', type: 'weak_evidence', severity: 'low', message: '' },
        { event_id: 'e2', type: 'weak_evidence', severity: 'high', message: '' },
        { event_id: 'e2', type: 'plan_drift', severity: 'medium', message: '' },
      ],
    })
    const annotation = deriveAuditAnnotations(report).get('e2')!
    expect(annotation.signalTypes).toEqual(['weak_evidence', 'plan_drift'])
    expect(annotation.topSignalSeverity).toBe('high')
  })
})

// ---------------------------------------------------------------------------
// annotationRank

describe('annotationRank', () => {
  it('is null for undefined annotation (no marker rendered)', () => {
    expect(annotationRank(undefined)).toBeNull()
  })

  it('ranks a localized failure as high', () => {
    const map = deriveAuditAnnotations(
      baseReport({
        failures: [
          {
            event_id: 'f',
            event_type: 'error',
            headline: '',
            mode: 'runtime_error',
            symptom: '',
            likely_cause: '',
            likely_cause_event_id: null,
            confidence: 0.5,
            supporting_event_ids: [],
            position: 0,
          },
        ],
      }),
    )
    expect(annotationRank(map.get('f'))).toBe('high')
  })

  it('ranks contradicted and unsupported claims as high, medium signal as medium', () => {
    const highClaim = deriveAuditAnnotations(
      baseReport({
        claims: [
          {
            event_id: 'c',
            event_type: 'decision',
            headline: '',
            claim: '',
            rationale: '',
            confidence: 0.5,
            alternatives_considered: 0,
            evidence_refs: [],
            evidence_sources: [],
            verification_status: 'contradicted',
            verification_basis: '',
            contradicted: true,
            timestamp: '',
          },
        ],
      }),
    )
    expect(annotationRank(highClaim.get('c'))).toBe('high')

    const medSignal = deriveAuditAnnotations(
      baseReport({
        signals: [{ event_id: 'm', type: 'plan_drift', severity: 'medium', message: '' }],
      }),
    )
    expect(annotationRank(medSignal.get('m'))).toBe('medium')
  })

  it('returns null for a verified decision with no risk signals (no inline noise)', () => {
    const map = deriveAuditAnnotations(
      baseReport({
        claims: [
          {
            event_id: 'v',
            event_type: 'decision',
            headline: '',
            claim: '',
            rationale: '',
            confidence: 0.9,
            alternatives_considered: 1,
            evidence_refs: ['e0'],
            evidence_sources: ['tool_backed'],
            verification_status: 'verified',
            verification_basis: '',
            contradicted: false,
            timestamp: '',
          },
        ],
      }),
    )
    expect(annotationRank(map.get('v'))).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// annotationTooltip

describe('annotationTooltip', () => {
  it('summarizes failure + signal types', () => {
    const map = deriveAuditAnnotations(
      baseReport({
        failures: [
          {
            event_id: 'f',
            event_type: 'error',
            headline: '',
            mode: 'tool_misuse',
            symptom: 'wrong arg',
            likely_cause: '',
            likely_cause_event_id: null,
            confidence: 0.5,
            supporting_event_ids: [],
            position: 0,
          },
        ],
        signals: [
          { event_id: 'f', type: 'unsupported_claim', severity: 'high', message: '' },
        ],
      }),
    )
    const tip = annotationTooltip(map.get('f')!)
    expect(tip).toContain('FAILED — tool_misuse')
    expect(tip).toContain('wrong arg')
    expect(tip).toContain('unsupported_claim')
  })
})
