/**
 * TimelineGraph.tsx
 * 50-year projection screen with three views:
 *   Chart    — net worth trajectory line chart
 *   Table    — key-year snapshot table
 *   Backtest — historical sequence backtest (1929 / 1966 / 2000 / 2008)
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, AreaChart, Area,
} from 'recharts'
import { PageHeader } from '../components/layout/PageHeader'
import { TimelineChart } from '../components/graph/TimelineChart'
import { useSimulationStore } from '../store/simulationStore'
import { useConfigStore } from '../store/configStore'
import { apiClient } from '../api/client'
import type { YearSnapshot } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

const KEY_YEARS = [2025, 2030, 2035, 2040, 2045, 2050, 2060, 2075]

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v / 1_000).toFixed(1)}k`
  return `£${v.toLocaleString()}`
}

function findSnap(snapshots: YearSnapshot[], year: number): YearSnapshot | undefined {
  return snapshots.find((s) => s.year >= year) ?? snapshots.at(-1)
}

const tipStyle = {
  background: '#0f1b2d', border: '1px solid #30363d',
  borderRadius: 8, color: '#e8edf2', fontSize: 11,
}

// ── Backtest types ────────────────────────────────────────────────────────────

interface BTYear {
  year: number; age: number; portfolio: number
  return_rate: number; drawdown: number; fire_sustained: boolean
}
interface BTScenario {
  scenario_id: string; label: string; description: string; colour: string
  years: BTYear[]; terminal_value: number
  ruin_year: number | null; survived: boolean
  min_value: number; min_value_year: number
}
interface BTResult {
  base_label: string; base_years: BTYear[]; base_terminal: number
  scenarios: BTScenario[]
  all_survived: boolean; worst_scenario_id: string; warnings: string[]
}

// ── Backtest view ─────────────────────────────────────────────────────────────

function BacktestView({ scenarioPath }: { scenarioPath: string }) {
  const [equityPct, setEquityPct] = useState(80)
  const [ready, setReady]         = useState(false)
  const [showTable, setShowTable] = useState(false)

  const { data, isLoading, isError } = useQuery<BTResult>({
    queryKey: ['backtest', scenarioPath, equityPct],
    queryFn: () =>
      apiClient
        .get(`/backtest/run?scenario_path=${encodeURIComponent(scenarioPath)}&equity_fraction=${equityPct / 100}`)
        .then(r => r.data),
    enabled: ready,
    staleTime: 120_000,
  })

  // Build chart data aligned by age
  const chartData = (() => {
    if (!data) return []
    return data.base_years
      .filter(y => y.age % 2 === 0)
      .map(y => {
        const row: Record<string, number | null> = {
          age: y.age,
          Base: Math.round(y.portfolio / 1000),
        }
        for (const s of data.scenarios) {
          const match = s.years.find(sy => sy.age === y.age)
          row[s.scenario_id] = match ? Math.round(match.portfolio / 1000) : null
        }
        return row
      })
  })()

  // Annual return series chart (year 1-15 only — the crash window)
  const returnData = data?.scenarios[0]?.years
    .slice(0, 20)
    .map((_y, i) => {
      const row: Record<string, any> = { year: `Y${i + 1}` }
      for (const s of data!.scenarios) {
        const sy = s.years[i]
        row[s.scenario_id] = sy ? Math.round(sy.return_rate * 1000) / 10 : null
      }
      return row
    }) ?? []

  return (
    <div>
      {/* Controls */}
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-end', marginBottom: 20,
                    background: '#162236', borderRadius: 12, padding: '16px 20px',
                    border: '1px solid rgba(255,255,255,0.07)' }}>
        <div>
          <div style={{ color: '#8fa3b8', fontSize: 11, marginBottom: 6, fontWeight: 500 }}>
            Equity allocation in retirement
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <input
              type="range" min={20} max={100} step={5} value={equityPct}
              onChange={e => { setEquityPct(Number(e.target.value)); setReady(false) }}
              style={{ width: 180, accentColor: '#0e9aad', cursor: 'pointer' }}
            />
            <span style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace',
                           fontSize: 16, fontWeight: 700, minWidth: 44 }}>{equityPct}%</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9,
                        color: '#8b949e', width: 180, marginTop: 2 }}>
            <span>20% (conservative)</span><span>100% (aggressive)</span>
          </div>
        </div>

        <button
          onClick={() => setReady(true)}
          disabled={isLoading}
          style={{
            background: '#0e9aad', color: '#fff', border: 'none', borderRadius: 8,
            padding: '10px 24px', fontSize: 13, fontWeight: 600,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            opacity: isLoading ? 0.7 : 1, whiteSpace: 'nowrap',
          }}
        >
          {isLoading ? 'Running…' : ready && data ? 'Re-run' : 'Run Backtest'}
        </button>

        {data && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ color: data.all_survived ? '#2dbd7e' : '#e05252', fontWeight: 700, fontSize: 14 }}>
              {data.all_survived ? '✓ All scenarios survived' : '⚠ Portfolio exhaustion detected'}
            </div>
            <div style={{ color: '#8b949e', fontSize: 11 }}>
              at {equityPct}% equity allocation
            </div>
          </div>
        )}
      </div>

      {/* What is this? */}
      {!ready && (
        <div style={{ background: '#162236', borderRadius: 12, padding: '20px 24px',
                      border: '1px solid rgba(255,255,255,0.07)', marginBottom: 16 }}>
          <h3 style={{ color: '#e8edf2', fontSize: 14, fontWeight: 600, margin: '0 0 10px' }}>
            What is the historical sequence backtest?
          </h3>
          <p style={{ color: '#8fa3b8', fontSize: 13, lineHeight: 1.6, margin: 0 }}>
            Monte Carlo uses random return distributions to stress-test your plan. This backtest
            instead uses <strong style={{ color: '#e8edf2' }}>real historical equity returns</strong> from
            four of the worst periods in market history — showing exactly what would have happened
            to your portfolio had retirement started in those years.
          </p>
          <p style={{ color: '#8fa3b8', fontSize: 13, lineHeight: 1.6, margin: '10px 0 0' }}>
            This tests <em>sequence-of-returns risk</em>: the same average return can produce very
            different outcomes depending on whether bad years occur early or late in retirement.
            A crash in year 1 is far more damaging than an identical crash in year 20.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginTop: 16 }}>
            {[
              { id: '1929', label: 'Great Depression', col: '#e05252', worst: '-43%', year: '1931' },
              { id: '1966', label: 'UK Stagflation',   col: '#f97316', worst: '-73% real', year: '1974' },
              { id: '2000', label: 'Dot-com bust',     col: '#d4a843', worst: '-22%', year: '2002' },
              { id: '2008', label: 'GFC',              col: '#0e9aad', worst: '-37%', year: '2008' },
            ].map(s => (
              <div key={s.id} style={{ background: `${s.col}11`, border: `1px solid ${s.col}33`,
                                       borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ color: s.col, fontWeight: 600, fontSize: 12, marginBottom: 4 }}>{s.label}</div>
                <div style={{ color: '#8b949e', fontSize: 10 }}>
                  Peak drawdown: <span style={{ color: s.col }}>{s.worst}</span> ({s.year})
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isLoading && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: 24,
                      background: '#162236', borderRadius: 12, color: '#8fa3b8', fontSize: 13,
                      border: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ width: 18, height: 18, border: '2px solid #0e9aad',
                        borderTopColor: 'transparent', borderRadius: '50%',
                        animation: 'spin 0.8s linear infinite' }} />
          Replaying portfolio through historical return sequences…
        </div>
      )}

      {isError && (
        <div style={{ background: '#e0525211', border: '1px solid #e0525244', borderRadius: 12,
                      padding: '16px 20px', color: '#e05252', fontSize: 13 }}>
          ⚠ Backtest failed. Ensure a scenario with pension/savings accounts and expense buckets is configured.
        </div>
      )}

      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Survival cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
            {data.scenarios.map(s => (
              <div key={s.scenario_id}
                   style={{ background: `${s.colour}0d`, border: `1px solid ${s.colour}44`,
                            borderRadius: 12, padding: '14px 16px' }}>
                <div style={{ color: s.colour, fontWeight: 700, fontSize: 12, marginBottom: 6 }}>
                  {s.label}
                </div>
                <div style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace',
                              fontSize: 18, fontWeight: 700 }}>
                  {s.survived ? fmt(s.terminal_value) : '⚠ RUIN'}
                </div>
                <div style={{ color: '#8b949e', fontSize: 10, marginTop: 2 }}>
                  {s.survived ? 'terminal wealth' : `portfolio exhausted`}
                </div>
                <div style={{ marginTop: 8, borderTop: `1px solid ${s.colour}22`, paddingTop: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                    <span style={{ color: '#8b949e' }}>Trough</span>
                    <span style={{ color: s.colour, fontFamily: 'DM Mono, monospace' }}>
                      {fmt(s.min_value)} ({s.min_value_year})
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 3 }}>
                    <span style={{ color: '#8b949e' }}>vs base</span>
                    <span style={{
                      color: s.terminal_value >= data.base_terminal ? '#2dbd7e' : '#e05252',
                      fontFamily: 'DM Mono, monospace',
                    }}>
                      {s.terminal_value >= data.base_terminal ? '+' : ''}
                      {fmt(s.terminal_value - data.base_terminal)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Portfolio trajectory chart */}
          <div style={{ background: '#162236', borderRadius: 12, padding: '16px 20px',
                        border: '1px solid rgba(255,255,255,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ color: '#8fa3b8', fontSize: 11, fontWeight: 600,
                           textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0, flex: 1 }}>
                Portfolio Trajectory — All Scenarios (£k)
              </h3>
              <button
                onClick={() => setShowTable(t => !t)}
                style={{ background: showTable ? '#0e9aad' : 'rgba(255,255,255,0.06)',
                         color: showTable ? '#fff' : '#8fa3b8', border: 'none',
                         borderRadius: 6, padding: '4px 12px', fontSize: 11, cursor: 'pointer' }}>
                {showTable ? 'Hide table' : 'Show table'}
              </button>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }}
                       label={{ value: 'Age', position: 'insideBottom', fill: '#8b949e', fontSize: 9, dy: 6 }} />
                <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} width={60} />
                <Tooltip
                  formatter={(v: number, n: string) => {
                    const labels: Record<string, string> = {
                      Base: 'Mean returns', '1929': 'Great Depression',
                      '1966': 'Stagflation', '2000': 'Dot-com bust', '2008': 'GFC 2008',
                    }
                    return [`£${v}k`, labels[n] ?? n]
                  }}
                  contentStyle={tipStyle}
                />
                <Legend
                  formatter={(v) => {
                    const labels: Record<string, string> = {
                      Base: 'Mean returns', '1929': 'Great Depression',
                      '1966': 'Stagflation', '2000': 'Dot-com bust', '2008': 'GFC 2008',
                    }
                    return labels[v] ?? v
                  }}
                  wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }}
                />
                <ReferenceLine y={0} stroke="#e05252" strokeDasharray="3 2" strokeWidth={1} />
                <Line dataKey="Base" stroke="#8fa3b8" strokeWidth={1.5} dot={false}
                      strokeDasharray="6 3" connectNulls />
                {data.scenarios.map(s => (
                  <Line key={s.scenario_id} dataKey={s.scenario_id}
                        stroke={s.colour} strokeWidth={2} dot={false} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Year-by-year comparison table */}
          {showTable && (
            <div style={{ background: '#162236', borderRadius: 12, padding: '16px 20px',
                          border: '1px solid rgba(255,255,255,0.07)' }}>
              <h3 style={{ color: '#8fa3b8', fontSize: 11, fontWeight: 600,
                           textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>
                Year-by-Year Comparison
              </h3>
              <div style={{ overflowX: 'auto', maxHeight: 360, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, minWidth: 700 }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#162236', zIndex: 1 }}>
                    <tr style={{ color: '#8b949e' }}>
                      <th style={{ padding: '6px 10px', textAlign: 'right', borderBottom: '1px solid #1d2f47', fontWeight: 500 }}>Age</th>
                      <th style={{ padding: '6px 10px', textAlign: 'right', borderBottom: '1px solid #1d2f47', fontWeight: 500, color: '#8fa3b8' }}>Base</th>
                      {data.scenarios.map(s => (
                        <th key={s.scenario_id} style={{ padding: '6px 10px', textAlign: 'right',
                                                         borderBottom: '1px solid #1d2f47', fontWeight: 500,
                                                         color: s.colour }}>
                          {s.label.split(' (')[0]}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.base_years.filter(y => y.age % 2 === 0).map(y => (
                      <tr key={y.age} style={{ borderBottom: '1px solid #0f1b2d' }}>
                        <td style={{ padding: '5px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace',
                                     color: '#8fa3b8' }}>{y.age}</td>
                        <td style={{ padding: '5px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace',
                                     color: '#e8edf2' }}>{fmt(y.portfolio)}</td>
                        {data.scenarios.map(s => {
                          const sy = s.years.find(sy => sy.age === y.age)
                          const val = sy?.portfolio ?? 0
                          return (
                            <td key={s.scenario_id}
                                style={{ padding: '5px 10px', textAlign: 'right',
                                         fontFamily: 'DM Mono, monospace',
                                         color: val > y.portfolio ? '#2dbd7e' : val === 0 ? '#e05252' : s.colour }}>
                              {val === 0 && !sy?.fire_sustained ? '⚠ £0' : fmt(val)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Annual returns (crash window, first 20 years) */}
          <div style={{ background: '#162236', borderRadius: 12, padding: '16px 20px',
                        border: '1px solid rgba(255,255,255,0.07)' }}>
            <h3 style={{ color: '#8fa3b8', fontSize: 11, fontWeight: 600,
                         textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>
              Annual Equity Returns — Retirement Years 1–20 (%)
            </h3>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={returnData}>
                <XAxis dataKey="year" tick={{ fill: '#8b949e', fontSize: 9 }} />
                <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#8b949e', fontSize: 9 }} width={44} />
                <Tooltip formatter={(v: number, n: string) => [`${v.toFixed(1)}%`, n]} contentStyle={tipStyle} />
                <ReferenceLine y={0} stroke="#30363d" />
                {data.scenarios.map(s => (
                  <Area key={s.scenario_id} type="monotone" dataKey={s.scenario_id}
                        stroke={s.colour} fill={`${s.colour}18`} strokeWidth={1.5}
                        dot={false} connectNulls />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Sequence description cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {data.scenarios.map(s => (
              <div key={s.scenario_id}
                   style={{ background: '#0f1b2d', borderRadius: 10, padding: '14px 16px',
                            borderLeft: `3px solid ${s.colour}` }}>
                <div style={{ color: s.colour, fontWeight: 600, fontSize: 12, marginBottom: 6 }}>
                  {s.label}
                </div>
                <p style={{ color: '#8fa3b8', fontSize: 12, lineHeight: 1.5, margin: 0 }}>
                  {s.description}
                </p>
                <div style={{ marginTop: 10, display: 'flex', gap: 16, fontSize: 10 }}>
                  <div>
                    <span style={{ color: '#8b949e' }}>Terminal: </span>
                    <span style={{
                      color: s.survived ? s.colour : '#e05252',
                      fontFamily: 'DM Mono, monospace', fontWeight: 700,
                    }}>
                      {s.survived ? fmt(s.terminal_value) : 'RUIN'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: '#8b949e' }}>Trough: </span>
                    <span style={{ color: s.colour, fontFamily: 'DM Mono, monospace' }}>
                      {fmt(s.min_value)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Warnings */}
          {data.warnings.map((w, i) => (
            <div key={i} style={{ background: '#e0525211', border: '1px solid #e0525244',
                                  borderRadius: 8, padding: '10px 16px', color: '#e05252', fontSize: 12 }}>
              ⚠ {w}
            </div>
          ))}

          {/* Safe withdrawal rate note */}
          <div style={{ background: '#0f1b2d', borderRadius: 10, padding: '14px 16px',
                        border: '1px solid rgba(255,255,255,0.05)', fontSize: 12, color: '#8fa3b8', lineHeight: 1.6 }}>
            <strong style={{ color: '#8fa3b8' }}>Methodology:</strong> Returns are blended as{' '}
            <span style={{ fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>
              {equityPct}% × historical + {100 - equityPct}% × {data.base_years.length > 0 ? '7%' : '—'}
            </span>{' '}
            (your scenario growth rate). After the historical sequence ends, the projection reverts
            to the configured mean return. Drawdown is inflation-uprated at 2.5%/yr.
            Based on Shiller S&P 500 data (US) and Barclays Equity Gilt Study (UK).
            Results are for planning illustration only.
          </div>
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

// ── Table view (unchanged from original) ─────────────────────────────────────

function TableView({ snapshots }: { snapshots: YearSnapshot[] }) {
  return (
    <div className="rounded-xl overflow-hidden"
         style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
      <table className="w-full border-collapse">
        <thead>
          <tr style={{ borderBottom: '1px solid #243859' }}>
            {['Year', 'Net Worth', 'Gross Income', 'Net Income', 'FIRE'].map(col => (
              <th key={col}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide"
                  style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {KEY_YEARS.map(year => {
            const snap = findSnap(snapshots, year)
            return (
              <tr key={year} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  className="transition-colors"
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                <td className="px-4 py-3 font-mono text-sm" style={{ color: '#8fa3b8' }}>{year}</td>
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
                    snap.fire_achieved
                      ? <span style={{ color: '#2dbd7e' }}>✓</span>
                      : <span style={{ color: '#8fa3b8' }}>–</span>
                  ) : <span style={{ color: '#8fa3b8' }}>—</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {snapshots.length === 0 && (
        <div className="text-center py-8 text-sm" style={{ color: '#8fa3b8' }}>
          Run a simulation to see projections
        </div>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type View = 'chart' | 'table' | 'backtest'

export function TimelineGraph() {
  const { timeline, isRunning } = useSimulationStore()
  const { activeScenarioPath }  = useConfigStore()
  const [view, setView]         = useState<View>('chart')

  const snapshots = timeline?.years ?? []

  const tabs: { key: View; label: string }[] = [
    { key: 'chart',    label: 'Chart'    },
    { key: 'table',    label: 'Table'    },
    { key: 'backtest', label: '🕰 Backtest' },
  ]

  return (
    <div>
      <PageHeader
        title="Timeline"
        subtitle="50-year projection"
        actions={
          <div className="flex rounded overflow-hidden" style={{ border: '1px solid #243859' }}>
            {tabs.map(t => (
              <button key={t.key} onClick={() => setView(t.key)}
                      className="px-3 py-1.5 text-xs font-medium capitalize transition-all duration-150 cursor-pointer"
                      style={{
                        background: view === t.key ? '#0e9aad' : 'transparent',
                        color:      view === t.key ? '#fff' : '#8fa3b8',
                        border: 'none',
                      }}>
                {t.label}
              </button>
            ))}
          </div>
        }
      />

      {view === 'chart' && (
        <div className="rounded-xl p-4"
             style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
          <div className="text-xs font-semibold uppercase tracking-wide mb-4"
               style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}>
            Net Worth Projection
          </div>
          {isRunning ? (
            <div className="rounded-lg flex items-center justify-center animate-pulse"
                 style={{ height: 420, background: '#1d2f47' }}>
              <span style={{ color: '#8fa3b8', fontSize: 13 }}>Simulating…</span>
            </div>
          ) : (
            <TimelineChart data={snapshots} fireYear={timeline?.fire_year} height={420} />
          )}
        </div>
      )}

      {view === 'table' && <TableView snapshots={snapshots} />}

      {view === 'backtest' && <BacktestView scenarioPath={activeScenarioPath} />}
    </div>
  )
}
