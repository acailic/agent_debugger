import type { TraceBundle } from '../types'

interface CheckpointSnapshotProps {
  title: string
  checkpoint: TraceBundle['checkpoints'][number]
}

export function CheckpointSnapshot({ title, checkpoint }: CheckpointSnapshotProps) {
  return (
    <div className="checkpoint-preview">
      <div className="checkpoint-copy">
        <p className="eyebrow">{title}</p>
        <h3>Sequence {checkpoint.sequence}</h3>
      </div>
      <div className="checkpoint-grid">
        <div>
          <h4>State</h4>
          <pre>{JSON.stringify(checkpoint.state, null, 2)}</pre>
        </div>
        <div>
          <h4>Memory</h4>
          <pre>{JSON.stringify(checkpoint.memory, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}
