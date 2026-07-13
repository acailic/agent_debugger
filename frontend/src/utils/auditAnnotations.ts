import type {
  AuditClaim,
  AuditFailure,
  AuditSeverity,
  AuditSignal,
  AuditSignalType,
  AuditVerificationStatus,
  SessionAuditReport,
} from '../types'

/**
 * Per-event audit annotation, derived client-side from the session audit report.
 *
 * Aggregates the three event-bound audit streams (claims/verification, risk signals,
 * localized failures) into one object keyed by event id so the trace timeline can
 * surface "where it failed / what is unverified" inline, at scan time, without
 * forcing the operator to open each event.
 */
export interface AuditEventAnnotation {
  /** Claim verification status, present only for decision events. */
  verificationStatus?: AuditVerificationStatus
  /** True when the agent's claim was directly contradicted by evidence. */
  contradicted?: boolean
  /** Failure mode (e.g. tool_misuse) when this event is a localized failure. */
  failureMode?: string
  /** Failure symptom headline, when this event is a localized failure. */
  failureSymptom?: string
  /** Risk signal types attached to this event. */
  signalTypes: AuditSignalType[]
  /** Highest signal severity attached to this event. */
  topSignalSeverity?: AuditSeverity
}

/** Ranked severity of an annotation, for inline color coding. `null` = no problem worth flagging. */
export type AnnotationRank = 'high' | 'medium' | null

const SEVERITY_RANK: Record<AuditSeverity, number> = { high: 3, medium: 2, low: 1 }

/**
 * Build a Map<event_id, AuditEventAnnotation> from a session audit report.
 *
 * Deterministic and cheap — pure reduction over the already-fetched report, so the
 * timeline stays in sync with the AuditPanel without any new backend call.
 */
export function deriveAuditAnnotations(
  report: SessionAuditReport | null | undefined,
): Map<string, AuditEventAnnotation> {
  const map = new Map<string, AuditEventAnnotation>()
  if (!report) return map

  const ensure = (eventId: string): AuditEventAnnotation => {
    let existing = map.get(eventId)
    if (!existing) {
      existing = { signalTypes: [] }
      map.set(eventId, existing)
    }
    return existing
  }

  for (const claim of report.claims ?? []) {
    annotateClaim(ensure(claim.event_id), claim)
  }
  for (const signal of report.signals ?? []) {
    annotateSignal(ensure(signal.event_id), signal)
  }
  for (const failure of report.failures ?? []) {
    annotateFailure(ensure(failure.event_id), failure)
  }

  return map
}

function annotateClaim(annotation: AuditEventAnnotation, claim: AuditClaim): void {
  annotation.verificationStatus = claim.verification_status
  annotation.contradicted = annotation.contradicted || claim.contradicted
}

function annotateSignal(annotation: AuditEventAnnotation, signal: AuditSignal): void {
  if (!annotation.signalTypes.includes(signal.type)) {
    annotation.signalTypes.push(signal.type)
  }
  if (
    !annotation.topSignalSeverity ||
    SEVERITY_RANK[signal.severity] > SEVERITY_RANK[annotation.topSignalSeverity]
  ) {
    annotation.topSignalSeverity = signal.severity
  }
}

function annotateFailure(annotation: AuditEventAnnotation, failure: AuditFailure): void {
  annotation.failureMode = failure.mode
  annotation.failureSymptom = failure.symptom
  // A localized failure is at least a high-severity flag on its own event.
  if (!annotation.topSignalSeverity || SEVERITY_RANK['high'] > SEVERITY_RANK[annotation.topSignalSeverity]) {
    annotation.topSignalSeverity = 'high'
  }
}

/**
 * Reduce an annotation to a single inline rank. Returns `null` when the event has
 * no problem worth flagging (verified/unverified decisions with no signals/failures),
 * so the timeline marker only appears on actual risk — keeping scan-time noise low.
 */
export function annotationRank(annotation: AuditEventAnnotation | undefined): AnnotationRank {
  if (!annotation) return null
  if (annotation.failureMode || annotation.contradicted || annotation.verificationStatus === 'contradicted') {
    return 'high'
  }
  if (annotation.verificationStatus === 'unsupported' || annotation.verificationStatus === 'partially_verified') {
    return 'high'
  }
  if (annotation.verificationStatus === 'stale') {
    return 'medium'
  }
  const sev = annotation.topSignalSeverity
  if (sev === 'high') return 'high'
  if (sev === 'medium') return 'medium'
  return null
}

/** Human-readable tooltip summarizing why an event is flagged. */
export function annotationTooltip(annotation: AuditEventAnnotation): string {
  const parts: string[] = []
  if (annotation.failureMode) {
    parts.push(`FAILED — ${annotation.failureMode}${annotation.failureSymptom ? `: ${annotation.failureSymptom}` : ''}`)
  }
  if (annotation.contradicted || annotation.verificationStatus === 'contradicted') {
    parts.push('claim contradicted by evidence')
  } else if (annotation.verificationStatus === 'unsupported') {
    parts.push('unsupported claim — no evidence')
  } else if (annotation.verificationStatus === 'partially_verified') {
    parts.push('partially verified claim')
  } else if (annotation.verificationStatus === 'stale') {
    parts.push('stale claim — built on superseded evidence')
  }
  if (annotation.signalTypes.length > 0) {
    parts.push(`signals: ${annotation.signalTypes.join(', ')}`)
  }
  return parts.length > 0 ? `Audit: ${parts.join('; ')}` : 'Audit flag'
}
