import type { Checkpoint } from '../types'

interface CheckpointStateDiffProps {
  currentCheckpoint: Checkpoint
  nextCheckpoint: Checkpoint | null
  currentState?: Record<string, unknown>
}

interface DiffEntry {
  key: string
  type: 'added' | 'removed' | 'changed' | 'unchanged'
  oldValue: string
  newValue: string
}

function computeDiff(
  before: Record<string, unknown>,
  after: Record<string, unknown>
): DiffEntry[] {
  const allKeys = new Set([...Object.keys(before), ...Object.keys(after)])
  const entries: DiffEntry[] = []

  for (const key of allKeys) {
    const inBefore = key in before
    const inAfter = key in after
    const oldVal = JSON.stringify(before[key], null, 2) ?? 'undefined'
    const newVal = JSON.stringify(after[key], null, 2) ?? 'undefined'

    if (!inBefore && inAfter) {
      entries.push({ key, type: 'added', oldValue: '', newValue: newVal })
    } else if (inBefore && !inAfter) {
      entries.push({ key, type: 'removed', oldValue: oldVal, newValue: '' })
    } else if (oldVal !== newVal) {
      entries.push({ key, type: 'changed', oldValue: oldVal, newValue: newVal })
    }
  }

  // Sort: removed first, then changed, then added
  const typeOrder: Record<string, number> = { removed: 0, changed: 1, added: 2 }
  return entries.sort((a, b) => (typeOrder[a.type] ?? 3) - (typeOrder[b.type] ?? 3))
}

export function CheckpointStateDiff({ currentCheckpoint, nextCheckpoint, currentState }: CheckpointStateDiffProps) {
  const before = currentCheckpoint.state
  const after = nextCheckpoint?.state ?? currentState ?? {}

  const diff = computeDiff(before, after)
  const hasChanges = diff.length > 0
  const added = diff.filter(d => d.type === 'added').length
  const removed = diff.filter(d => d.type === 'removed').length
  const changed = diff.filter(d => d.type === 'changed').length

  return (
    <div className="checkpoint-state-diff panel panel--secondary">
      <div className="panel-head">
        <p className="eyebrow">Checkpoint State Diff</p>
        <h2>State Changes</h2>
      </div>

      {nextCheckpoint ? (
        <div className="diff-context">
          <span className="diff-label">Comparing sequence {currentCheckpoint.sequence} → {nextCheckpoint.sequence}</span>
        </div>
      ) : (
        <div className="diff-context">
          <span className="diff-label">Comparing to current state (last checkpoint)</span>
        </div>
      )}

      {hasChanges ? (
        <div className="diff-summary">
          {added > 0 && <span className="diff-stat diff-added">+{added} added</span>}
          {removed > 0 && <span className="diff-stat diff-removed">-{removed} removed</span>}
          {changed > 0 && <span className="diff-stat diff-changed">~{changed} changed</span>}
        </div>
      ) : (
        <div className="diff-unchanged">
          <span>No state changes between checkpoints</span>
        </div>
      )}

      <div className="diff-entries">
        {diff.map((entry) => (
          <div key={entry.key} className={`diff-entry diff-${entry.type}`}>
            <div className="diff-entry-header">
              <span className="diff-type-badge">{entry.type}</span>
              <span className="diff-key">{entry.key}</span>
            </div>
            {(entry.type === 'removed' || entry.type === 'changed') && (
              <div className="diff-old">
                <span className="diff-label">Before</span>
                <pre>{entry.oldValue}</pre>
              </div>
            )}
            {(entry.type === 'added' || entry.type === 'changed') && (
              <div className="diff-new">
                <span className="diff-label">After</span>
                <pre>{entry.newValue}</pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
