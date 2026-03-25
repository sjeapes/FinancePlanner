import { useState } from 'react'
import { PageHeader } from '../components/layout/PageHeader'
import { TimelineChart } from '../components/graph/TimelineChart'
import { useSimulationStore } from '../store/simulationStore'
import type { YearSnapshot } from '../types'

const KEY_YEARS = [2025, 2030, 2035, 2040, 2045, 2050, 2060, 2075]

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(1)}k`
  return `£${v.toLocaleString()}`
}

function findSnap(snapshots: YearSnapshot[], year: number): YearSnapshot | undefined {
  // Find nearest available year at or after target
  return snapshots.find((s) => s.year >= year) ?? snapshots.at(-1)
}

export function TimelineGraph() {
  const { timeline, isRunning } = useSimulationStore()
  const [view, setView] = useState<'chart' | 'table'>('chart')

  const snapshots = timeline?.years ?? []

  return (
    <div>
      <PageHeader
        title="Timeline"
        subtitle="50-year projection"
        actions={
          <div className="flex rounded overflow-hidden" style={{ border: '1px solid #243859' }}>
            {(['chart', 'table'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className="px-3 py-1.5 text-xs font-medium capitalize transition-all duration-150 cursor-pointer"
                style={{
                  background: view === v ? '#0e9aad' : 'transparent',
                  color: view === v ? '#fff' : '#8fa3b8',
                  border: 'none',
                }}
              >
                {v}
              </button>
            ))}
          </div>
        }
      />

      {view === 'chart' && (
        <div
          className="rounded-xl p-4"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            Net Worth Projection
          </div>
          {isRunning ? (
            <div
              className="rounded-lg flex items-center justify-center animate-pulse"
              style={{ height: 420, background: '#1d2f47' }}
            >
              <span style={{ color: '#8fa3b8', fontSize: 13 }}>Simulating…</span>
            </div>
          ) : (
            <TimelineChart
              data={snapshots}
              fireYear={timeline?.fire_year}
              height={420}
            />
          )}
        </div>
      )}

      {view === 'table' && (
        <div
          className="rounded-xl overflow-hidden"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #243859' }}>
                {['Year', 'Net Worth', 'Gross Income', 'Net Income', 'FIRE'].map((col) => (
                  <th
                    key={col}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide"
                    style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {KEY_YEARS.map((year) => {
                const snap = findSnap(snapshots, year)
                return (
                  <tr
                    key={year}
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                    className="transition-colors"
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <td className="px-4 py-3 font-mono text-sm" style={{ color: '#8fa3b8' }}>
                      {year}
                    </td>
                    <td className="px-4 py-3 font-mono text-sm" style={{ color: '#e8edf2' }}>
                      {snap ? fmt(snap.total_net_worth) : '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-sm" style={{ color: '#e8edf2' }}>
                      {snap ? fmt(snap.total_gross_income) : '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-sm" style={{ color: '#2dbd7e' }}>
                      {snap ? fmt(snap.total_net_income) : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm font-mono">
                      {snap ? (
                        snap.fire_achieved ? (
                          <span style={{ color: '#2dbd7e' }}>✓</span>
                        ) : (
                          <span style={{ color: '#8fa3b8' }}>–</span>
                        )
                      ) : (
                        <span style={{ color: '#8fa3b8' }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {snapshots.length === 0 && (
            <div
              className="text-center py-8 text-sm"
              style={{ color: '#8fa3b8' }}
            >
              Run a simulation to see projections
            </div>
          )}
        </div>
      )}
    </div>
  )
}
