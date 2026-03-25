import { PageHeader } from '../components/layout/PageHeader'
import { Scale } from 'lucide-react'

export function EstatePlanner() {
  return (
    <div>
      <PageHeader
        title="Estate Planner"
        subtitle="IHT & estate analysis"
      />

      <div
        className="rounded-xl p-10 flex flex-col items-center text-center"
        style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
      >
        <Scale size={40} className="mb-4 opacity-30" style={{ color: '#8fa3b8' }} />
        <h2 className="font-display text-xl font-semibold mb-2" style={{ color: '#e8edf2' }}>
          Estate Planning — Phase 5
        </h2>
        <p className="text-sm max-w-md" style={{ color: '#8fa3b8', lineHeight: 1.6 }}>
          IHT liability estimates, nil-rate band calculations, gifting tracker,
          survivor simulation, and pension-outside-estate analysis will be available
          in Phase 5.
        </p>
        <div
          className="mt-6 px-4 py-2 rounded-full text-xs font-mono"
          style={{
            background: 'rgba(167,139,250,0.1)',
            border: '1px solid rgba(167,139,250,0.25)',
            color: '#a78bfa',
          }}
        >
          Coming in Phase 5
        </div>
      </div>
    </div>
  )
}
