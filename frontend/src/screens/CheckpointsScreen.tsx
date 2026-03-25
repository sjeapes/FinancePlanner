import { PageHeader } from '../components/layout/PageHeader'
import { useCheckpoints } from '../api/hooks/useCheckpoints'
import { CheckCircle, Plus } from 'lucide-react'

export function CheckpointsScreen() {
  const { data: checkpoints, isLoading } = useCheckpoints()

  const items: string[] = checkpoints ?? []

  return (
    <div>
      <PageHeader
        title="Checkpoints"
        subtitle="Actual vs projected"
        actions={
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 cursor-pointer"
            style={{
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#8fa3b8',
            }}
            onClick={() => alert('Add checkpoint — Phase 4 feature')}
          >
            <Plus size={12} />
            Add Checkpoint
          </button>
        }
      />

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl p-4 animate-pulse"
              style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)', height: 64 }}
            />
          ))}
        </div>
      ) : items.length > 0 ? (
        <div className="space-y-2">
          {items.map((cp) => (
            <div
              key={cp}
              className="rounded-xl px-4 py-3 flex items-center gap-3"
              style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
            >
              <CheckCircle size={16} style={{ color: '#2dbd7e', flexShrink: 0 }} />
              <span className="font-mono text-sm" style={{ color: '#e8edf2' }}>
                {cp}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div
          className="rounded-xl p-10 flex flex-col items-center text-center"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <CheckCircle size={36} className="mb-3 opacity-30" style={{ color: '#8fa3b8' }} />
          <h3 className="text-sm font-semibold mb-1" style={{ color: '#e8edf2' }}>
            No checkpoints yet
          </h3>
          <p className="text-xs max-w-sm" style={{ color: '#8fa3b8', lineHeight: 1.6 }}>
            Checkpoints record your actual net worth at a point in time. Add one to anchor
            the historical/projected boundary and enable divergence analysis.
          </p>
          <div
            className="mt-4 px-3 py-1.5 rounded text-xs font-mono"
            style={{
              background: 'rgba(212,168,67,0.08)',
              border: '1px solid rgba(212,168,67,0.2)',
              color: '#d4a843',
            }}
          >
            Full checkpoint UI in Phase 4
          </div>
        </div>
      )}
    </div>
  )
}
