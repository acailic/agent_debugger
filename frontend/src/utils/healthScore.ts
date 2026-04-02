import type { Session } from '../types'

interface BundleAnalysis {
  analysis: {
    session_summary: {
      failure_count: number
      behavior_alert_count: number
    }
  }
}

export function computeHealthScore(
  session: Session,
  bundle?: BundleAnalysis
): number {
  const failureCount = session.errors ?? 0
  const alertCount =
    bundle?.analysis.session_summary.behavior_alert_count ??
    session.behavior_alert_count ??
    0
  const replayValue = session.replay_value ?? 0

  let score = 100
  score -= failureCount * 10
  score -= alertCount * 5
  score += Math.min(replayValue * 2, 10)

  if (session.status === 'completed') score += 5
  if (session.status === 'error') score -= 20

  return Math.max(0, Math.min(100, score))
}

export function getHealthGrade(score: number): {
  grade: string
  color: string
  label: string
} {
  if (score >= 90) return { grade: 'A', color: '#10b981', label: 'Excellent' }
  if (score >= 80) return { grade: 'B', color: '#22c55e', label: 'Good' }
  if (score >= 70) return { grade: 'C', color: '#f59e0b', label: 'Fair' }
  if (score >= 60) return { grade: 'D', color: '#f97316', label: 'Poor' }
  return { grade: 'F', color: '#ef4444', label: 'Critical' }
}
