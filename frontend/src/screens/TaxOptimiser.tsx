/**
 * TaxOptimiser.tsx — Phase 8 Tax Optimisation Screen
 *
 * 4 tabs:
 *   Band-filler   — year-by-year optimal vs naive pension/ISA drawdown
 *   UFPLS vs PCLS — crystallisation strategy comparison
 *   CGT Harvester — annual GIA gain harvest schedule
 *   Summary       — combined savings, top actions, lifetime total
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, Cell,
} from 'recharts'
import { apiClient } from '../api/client'
import { useConfigStore } from '../store/configStore'

// ── Types ─────────────────────────────────────────────────────────────────────

interface BandFillYear {
  year: number; age: number; target_spending: number; other_income: number
  pension_drawn_opt: number; pension_drawn_naive: number
  isa_drawn_opt: number; isa_drawn_naive: number
  tax_opt: number; tax_naive: number; tax_saved: number
  pension_pot_opt: number; pension_pot_naive: number
  isa_pot_opt: number; isa_pot_naive: number
  action: string
}

interface BandFillData {
  years: BandFillYear[]
  lifetime_tax_opt: number; lifetime_tax_naive: number; lifetime_tax_saved: number
  isa_exhausted_year_opt: number | null; pension_exhausted_year_opt: number | null
  warnings: string[]
}

interface UFPLSYear {
  year: number; age: number
  ufpls_tax: number; pcls_tax: number
  ufpls_pot: number; pcls_drawdown_pot: number; pcls_lump_pot: number
  ufpls_total_wealth: number; pcls_total_wealth: number; delta: number
}

interface UFPLSData {
  pcls_lump_sum: number; starting_pot: number
  years: UFPLSYear[]
  lifetime_tax_ufpls: number; lifetime_tax_pcls: number
  terminal_wealth_ufpls: number; terminal_wealth_pcls: number
  preferred_strategy: string; tax_saving_gbp: number
  warnings: string[]
}

interface CGTYear {
  year: number; gia_value: number; unrealised_gain: number
  harvest_amount: number; net_saving: number
  action: string; recommendation: string
}

interface CGTData {
  years: CGTYear[]
  total_cgt_without: number; total_cgt_with: number
  total_lifetime_saving: number; total_trade_costs: number; net_saving: number
  harvest_years: number[]
  warnings: string[]
}

interface SummaryData {
  band_fill_saving_gbp: number; ufpls_saving_gbp: number
  cgt_harvest_saving_gbp: number; total_saving_gbp: number
  top_actions: string[]
  band_fill: BandFillData | null
  ufpls: UFPLSData | null
  cgt_harvest: CGTData | null
  warnings: string[]
}

// ── Shared helpers ────────────────────────────────────────────────────────────

const fmt = (v: number, currency = 'GBP') => {
  const sym = currency === 'USD' ? '$' : '£'
  if (Math.abs(v) >= 1_000_000) return `${sym}${(v / 1_000_000).toFixed(2)}M`
  if (Math.abs(v) >= 1_000) return `${sym}${(v / 1_000).toFixed(0)}k`
  return `${sym}${v.toFixed(0)}`
}

const TEAL = '#0e9aad'; const GOLD = '#d4a843'; const GREEN = '#2dbd7e'
const RED  = '#e05252'; const PURP = '#a78bfa'; const ORNG = '#f97316'

function Card({ title, children, accent = TEAL }: {
  title?: string; children: React.ReactNode; accent?: string
}) {
  return (
    <div style={{ background: '#162236', borderRadius: 12, padding: 20,
                  borderLeft: `3px solid ${accent}` }}>
      {title && <h3 style={{ color: '#e8edf2', fontSize: 12, fontWeight: 600,
                             textTransform: 'uppercase', letterSpacing: '0.06em',
                             margin: 0, marginBottom: 14 }}>{title}</h3>}
      {children}
    </div>
  )
}

function KPI({ label, value, sub, accent = TEAL }: {
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <div style={{ background: '#162236', borderRadius: 10, padding: '14px 18px',
                  borderTop: `2px solid ${accent}` }}>
      <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase',
                    letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ color: '#e8edf2', fontSize: 20, fontWeight: 700,
                    fontFamily: 'DM Mono, monospace', marginTop: 4 }}>{value}</div>
      {sub && <div style={{ color: '#8b949e', fontSize: 10, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Pill({ label, colour }: { label: string; colour: string }) {
  return <span style={{ background: `${colour}22`, color: colour,
                        border: `1px solid ${colour}44`, borderRadius: 4,
                        padding: '2px 8px', fontSize: 10, fontWeight: 600 }}>{label}</span>
}

const tipStyle = { background: '#0f1b2d', border: '1px solid #30363d',
                   borderRadius: 8, color: '#e8edf2', fontSize: 11 }

// ── Loading / Error states ────────────────────────────────────────────────────

function Loading({ text = 'Loading…' }: { text?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                  height: 200, color: '#8fa3b8', gap: 12 }}>
      <div style={{ width: 18, height: 18, border: `2px solid ${TEAL}`,
                    borderTopColor: 'transparent', borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite' }} />
      {text}
    </div>
  )
}

// ── Tab 1: Band-filler ────────────────────────────────────────────────────────

function BandFillerTab({ scenarioPath }: { scenarioPath: string }) {
  const [band, setBand] = useState<'personal_allowance'|'basic_rate'|'higher_rate'>('basic_rate')

  const { data, isLoading, isError } = useQuery<BandFillData>({
    queryKey: ['band-fill', scenarioPath, band],
    queryFn: () => apiClient.get(
      `/tax-optimiser/band-fill?scenario_path=${encodeURIComponent(scenarioPath)}&target_band=${band}`
    ).then(r => r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Computing optimal drawdown schedule…" />
  if (isError || !data) return (
    <div style={{ color: RED, padding: 16, background: `${RED}11`, borderRadius: 8, fontSize: 13 }}>
      Failed to load band-fill data. Check the backend is running and the scenario has pension/ISA accounts.
    </div>
  )

  const chartData = data.years
    .filter(y => y.year % 2 === 0)
    .map(y => ({
      age: y.age,
      Optimal: Math.round(y.tax_opt),
      Naive:   Math.round(y.tax_naive),
      Saved:   Math.round(y.tax_saved),
    }))

  const wealthData = data.years
    .filter(y => y.year % 2 === 0)
    .map(y => ({
      age:         y.age,
      'SIPP (opt)': Math.round(y.pension_pot_opt / 1000),
      'SIPP (naive)': Math.round(y.pension_pot_naive / 1000),
      'ISA (opt)':  Math.round(y.isa_pot_opt / 1000),
      'ISA (naive)': Math.round(y.isa_pot_naive / 1000),
    }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Band selector */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#8b949e', fontSize: 12 }}>Fill up to:</span>
        {(['personal_allowance', 'basic_rate', 'higher_rate'] as const).map(b => (
          <button key={b} onClick={() => setBand(b)} style={{
            padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
            fontSize: 11, background: band === b ? TEAL : '#1d2f47',
            color: band === b ? '#fff' : '#8fa3b8',
          }}>
            {b === 'personal_allowance' ? '£12,570 (0%)' : b === 'basic_rate' ? '£50,270 (20%)' : '£125,140 (40%)'}
          </button>
        ))}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
        <KPI label="Lifetime tax — optimal" value={fmt(data.lifetime_tax_opt)} accent={GREEN} />
        <KPI label="Lifetime tax — naive"   value={fmt(data.lifetime_tax_naive)} accent={GOLD} />
        <KPI label="Total tax saved"        value={fmt(data.lifetime_tax_saved)} accent={TEAL}
             sub="by filling bands strategically" />
      </div>

      {data.warnings.map((w, i) => (
        <div key={i} style={{ color: GOLD, background: `${GOLD}11`, borderRadius: 8,
                              padding: '8px 14px', fontSize: 12, border: `1px solid ${GOLD}33` }}>
          ⚠ {w}
        </div>
      ))}

      {/* Tax per year chart */}
      <Card title="Annual Income Tax — Optimal vs Naive Strategy">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData}>
            <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }} label={{ value: 'Age', position: 'insideBottom', fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v.toLocaleString()}`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v.toLocaleString()}`, n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Bar dataKey="Naive"   fill={GOLD}  opacity={0.7} radius={[2,2,0,0]} />
            <Bar dataKey="Optimal" fill={GREEN}  opacity={0.85} radius={[2,2,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Pot trajectories */}
      <Card title="Pot Trajectories — Optimal vs Naive (£k)">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={wealthData}>
            <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v}k`, n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{ fontSize: 10, color: '#8fa3b8' }} />
            <Line dataKey="SIPP (opt)"   stroke={TEAL}  strokeWidth={2} dot={false} />
            <Line dataKey="SIPP (naive)" stroke={TEAL}  strokeWidth={1} dot={false} strokeDasharray="4 2" opacity={0.5} />
            <Line dataKey="ISA (opt)"    stroke={GOLD}  strokeWidth={2} dot={false} />
            <Line dataKey="ISA (naive)"  stroke={GOLD}  strokeWidth={1} dot={false} strokeDasharray="4 2" opacity={0.5} />
            {data.isa_exhausted_year_opt && (
              <ReferenceLine x={data.isa_exhausted_year_opt - (data.years[0]?.year ?? 2044) + (data.years[0]?.age ?? 60)}
                             stroke={RED} strokeDasharray="3 2"
                             label={{ value: 'ISA exhausted', fill: RED, fontSize: 8 }} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Actions table */}
      <Card title="Year-by-Year Recommended Actions">
        <div style={{ overflowX: 'auto', maxHeight: 300, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead style={{ position: 'sticky', top: 0, background: '#162236', zIndex: 1 }}>
              <tr style={{ color: '#8b949e' }}>
                {['Year','Age','Other Income','Opt Draw (SIPP)','Opt Draw (ISA)','Tax Opt','Tax Naive','Saved','Action'].map(h => (
                  <th key={h} style={{ padding: '6px 8px', fontWeight: 500,
                                       borderBottom: '1px solid #1d2f47', textAlign: h === 'Action' ? 'left' : 'right',
                                       whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.years.map(y => (
                <tr key={y.year} style={{ borderBottom: '1px solid #0f1b2d' }}>
                  <td style={{ padding: '5px 8px', color: TEAL, fontFamily: 'DM Mono, monospace', textAlign: 'right' }}>{y.year}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: '#e8edf2' }}>{y.age}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#8fa3b8' }}>{fmt(y.other_income)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>{fmt(y.pension_drawn_opt)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>{fmt(y.isa_drawn_opt)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: GREEN }}>{fmt(y.tax_opt)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: GOLD }}>{fmt(y.tax_naive)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: y.tax_saved > 100 ? GREEN : '#8b949e' }}>{y.tax_saved > 0 ? fmt(y.tax_saved) : '—'}</td>
                  <td style={{ padding: '5px 8px', color: '#8fa3b8', fontSize: 10, maxWidth: 200 }}>{y.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── Tab 2: UFPLS vs PCLS ──────────────────────────────────────────────────────

function UFPLSTab({ scenarioPath }: { scenarioPath: string }) {
  const { data, isLoading, isError } = useQuery<UFPLSData>({
    queryKey: ['ufpls', scenarioPath],
    queryFn: () => apiClient.get(`/tax-optimiser/ufpls?scenario_path=${encodeURIComponent(scenarioPath)}`).then(r => r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Comparing UFPLS vs PCLS strategies…" />
  if (isError || !data) return (
    <div style={{ color: RED, padding: 16, background: `${RED}11`, borderRadius: 8, fontSize: 13 }}>
      Failed to load UFPLS data. Ensure a pension fund is configured in the scenario.
    </div>
  )

  const chartData = data.years
    .filter(y => y.year % 2 === 0)
    .map(y => ({
      age: y.age,
      'UFPLS wealth': Math.round(y.ufpls_total_wealth / 1000),
      'PCLS wealth':  Math.round(y.pcls_total_wealth  / 1000),
      'UFPLS tax':    Math.round(y.ufpls_tax),
      'PCLS tax':     Math.round(y.pcls_tax),
    }))

  const preferred = data.preferred_strategy.toUpperCase()
  const prefColour = data.preferred_strategy === 'ufpls' ? TEAL : GOLD

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Verdict */}
      <div style={{ background: `${prefColour}11`, border: `1px solid ${prefColour}44`,
                    borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <div>
          <div style={{ color: prefColour, fontSize: 22, fontWeight: 700 }}>
            {preferred} is better
          </div>
          <div style={{ color: '#8fa3b8', fontSize: 13, marginTop: 4 }}>
            Saves <span style={{ color: prefColour, fontFamily: 'DM Mono, monospace', fontWeight: 700 }}>
              {fmt(data.tax_saving_gbp)}
            </span> in lifetime income tax vs the alternative strategy.
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase' }}>PCLS lump sum</div>
          <div style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace', fontWeight: 700, fontSize: 18 }}>
            {fmt(data.pcls_lump_sum)}
          </div>
          <div style={{ color: '#8b949e', fontSize: 10 }}>tax-free at crystallisation</div>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <KPI label="Lifetime tax — UFPLS" value={fmt(data.lifetime_tax_ufpls)} accent={TEAL} />
        <KPI label="Lifetime tax — PCLS"  value={fmt(data.lifetime_tax_pcls)}  accent={GOLD} />
        <KPI label="Terminal wealth UFPLS" value={fmt(data.terminal_wealth_ufpls)} accent={TEAL} />
        <KPI label="Terminal wealth PCLS"  value={fmt(data.terminal_wealth_pcls)}  accent={GOLD} />
      </div>

      {/* Wealth trajectory */}
      <Card title="Pot Trajectory — UFPLS vs PCLS (£k)">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData}>
            <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v}k`, n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Line dataKey="UFPLS wealth" stroke={TEAL} strokeWidth={2} dot={false} />
            <Line dataKey="PCLS wealth"  stroke={GOLD} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Annual tax comparison */}
      <Card title="Annual Income Tax Paid — UFPLS vs PCLS">
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData}>
            <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${(v/1000).toFixed(0)}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Bar dataKey="UFPLS tax" fill={TEAL} radius={[2,2,0,0]} />
            <Bar dataKey="PCLS tax"  fill={GOLD} radius={[2,2,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Explainer */}
      <Card title="How it works" accent={PURP}>
        {[
          { label: 'UFPLS', colour: TEAL, text: 'Each withdrawal is 25% tax-free and 75% taxable. No upfront lump sum — the tax-free element is spread across every payment throughout retirement. Works well when marginal rate is steady and no large lump sum is needed.' },
          { label: 'PCLS', colour: GOLD, text: `Take £${fmt(data.pcls_lump_sum)} (25% of pot) as a single tax-free lump sum at crystallisation. The remaining 75% enters drawdown and every subsequent payment is fully taxable. Better when you need capital upfront (e.g. mortgage payoff) or expect your marginal rate to fall later in retirement.` },
        ].map(r => (
          <div key={r.label} style={{ padding: '10px 0', borderBottom: '1px solid #1d2f47' }}>
            <Pill label={r.label} colour={r.colour} />
            <div style={{ color: '#8fa3b8', fontSize: 12, marginTop: 6 }}>{r.text}</div>
          </div>
        ))}
      </Card>
    </div>
  )
}

// ── Tab 3: CGT Harvester ──────────────────────────────────────────────────────

function CGTTab({ scenarioPath }: { scenarioPath: string }) {
  const { data, isLoading, isError } = useQuery<CGTData>({
    queryKey: ['cgt-harvest', scenarioPath],
    queryFn: () => apiClient.get(`/tax-optimiser/cgt-harvest?scenario_path=${encodeURIComponent(scenarioPath)}`).then(r => r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Computing CGT harvest schedule…" />
  if (isError || !data) return (
    <div style={{ color: '#8fa3b8', padding: 16, background: '#1d2f47', borderRadius: 8, fontSize: 13 }}>
      No GIA (General Investment Account) found in scenario — CGT harvesting is not applicable.
      Add a GIA account in Data Management to use this feature.
    </div>
  )

  const ACTION_COLOUR: Record<string, string> = {
    harvest: GREEN, loss_harvest: TEAL, monitor: GOLD, no_gain: '#8b949e',
  }

  const chartData = data.years.filter(y => y.year % 2 === 0).map(y => ({
    year: y.year,
    'GIA value (£k)': Math.round(y.gia_value / 1000),
    'Unrealised gain (£k)': Math.round(Math.max(0, y.unrealised_gain) / 1000),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
        <KPI label="CGT without harvesting" value={fmt(data.total_cgt_without)} accent={RED} />
        <KPI label="CGT with harvesting"    value={fmt(data.total_cgt_with)}    accent={GREEN} />
        <KPI label="Net lifetime saving"    value={fmt(data.net_saving)}         accent={TEAL}
             sub={`${data.harvest_years.length} harvest years`} />
      </div>

      <Card title="GIA Value and Unrealised Gain Over Time (£k)">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData}>
            <XAxis dataKey="year" tick={{ fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v}k`, n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Line dataKey="GIA value (£k)"            stroke={TEAL} strokeWidth={2} dot={false} />
            <Line dataKey="Unrealised gain (£k)"      stroke={GOLD} strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Harvest Schedule">
        <div style={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead style={{ position: 'sticky', top: 0, background: '#162236' }}>
              <tr style={{ color: '#8b949e' }}>
                {['Year','GIA Value','Unrealised Gain','Harvest Amount','Net Saving','Action','Recommendation'].map(h => (
                  <th key={h} style={{ padding: '6px 8px', fontWeight: 500,
                                       borderBottom: '1px solid #1d2f47', textAlign: h === 'Recommendation' ? 'left' : 'right',
                                       whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.years.map(y => (
                <tr key={y.year} style={{ borderBottom: '1px solid #0f1b2d' }}>
                  <td style={{ padding: '5px 8px', color: TEAL, fontFamily: 'DM Mono, monospace', textAlign: 'right' }}>{y.year}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>{fmt(y.gia_value)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace',
                               color: y.unrealised_gain > 0 ? GOLD : GREEN }}>
                    {y.unrealised_gain >= 0 ? fmt(y.unrealised_gain) : `(${fmt(Math.abs(y.unrealised_gain))})`}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>
                    {y.harvest_amount > 0 ? fmt(y.harvest_amount) : '—'}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'DM Mono, monospace',
                               color: y.net_saving > 0 ? GREEN : '#8b949e' }}>
                    {y.net_saving > 0 ? fmt(y.net_saving) : '—'}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right' }}>
                    <Pill label={y.action.replace('_', ' ').toUpperCase()}
                          colour={ACTION_COLOUR[y.action] ?? '#8b949e'} />
                  </td>
                  <td style={{ padding: '5px 8px', color: '#8fa3b8', fontSize: 10, maxWidth: 240 }}>
                    {y.recommendation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── Tab 4: Summary ────────────────────────────────────────────────────────────

function SummaryTab({ data }: { data: SummaryData }) {
  const breakdown = [
    { label: 'Band-filler (pension/ISA drawdown)',      value: data.band_fill_saving_gbp,     accent: TEAL },
    { label: 'UFPLS vs PCLS strategy selection',       value: data.ufpls_saving_gbp,          accent: GOLD },
    { label: 'CGT annual harvest schedule',            value: data.cgt_harvest_saving_gbp,    accent: GREEN },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Total saving hero */}
      <div style={{ background: '#0e9aad11', border: '1px solid #0e9aad44', borderRadius: 12,
                    padding: '24px 28px', textAlign: 'center' }}>
        <div style={{ color: '#8fa3b8', fontSize: 12, textTransform: 'uppercase',
                      letterSpacing: '0.06em', marginBottom: 8 }}>
          Estimated total lifetime tax saving
        </div>
        <div style={{ color: TEAL, fontSize: 42, fontWeight: 700, fontFamily: 'DM Mono, monospace' }}>
          {fmt(data.total_saving_gbp)}
        </div>
        <div style={{ color: '#8fa3b8', fontSize: 12, marginTop: 6 }}>
          by implementing all three optimisation strategies
        </div>
      </div>

      {/* Breakdown */}
      <Card title="Saving Breakdown">
        {breakdown.map(b => (
          <div key={b.label} style={{ display: 'flex', justifyContent: 'space-between',
                                      alignItems: 'center', padding: '10px 0',
                                      borderBottom: '1px solid #1d2f47' }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>{b.label}</span>
            <span style={{ color: b.value > 0 ? b.accent : '#8b949e',
                           fontFamily: 'DM Mono, monospace', fontSize: 16, fontWeight: 700 }}>
              {b.value > 0 ? fmt(b.value) : 'N/A'}
            </span>
          </div>
        ))}
      </Card>

      {/* Top actions */}
      <Card title="Recommended Actions" accent={GREEN}>
        {data.top_actions.map((action, i) => (
          <div key={i} style={{ display: 'flex', gap: 12, padding: '10px 0',
                                borderBottom: '1px solid #1d2f47' }}>
            <div style={{ width: 22, height: 22, borderRadius: '50%', background: TEAL + '22',
                          color: TEAL, display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
              {i + 1}
            </div>
            <div style={{ color: '#e8edf2', fontSize: 13, lineHeight: 1.5 }}>{action}</div>
          </div>
        ))}
      </Card>

      {/* Methodology note */}
      <div style={{ color: '#8b949e', fontSize: 11, lineHeight: 1.6,
                    padding: '10px 14px', background: '#0f1b2d', borderRadius: 8 }}>
        <strong style={{ color: '#8fa3b8' }}>Methodology:</strong>{' '}
        Band-fill savings are computed using 2024/25 UK tax bands (personal allowance £12,570, basic rate to £50,270).
        UFPLS uses a 25% statutory tax-free fraction per withdrawal; PCLS takes 25% as a lump sum at crystallisation.
        CGT harvest assumes a £3,000 annual exemption (2024/25). All figures are estimates for planning purposes;
        consult an IFA before implementing. Scottish residents: enable Scottish rates in
        <code style={{ color: TEAL }}> config/tax/optimiser_config.yaml</code>.
      </div>

      {data.warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {data.warnings.map((w, i) => (
            <div key={i} style={{ color: GOLD, background: `${GOLD}11`, borderRadius: 8,
                                  padding: '8px 14px', fontSize: 12, border: `1px solid ${GOLD}33` }}>
              ⚠ {w}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

const TABS = ['Band-filler', 'UFPLS vs PCLS', 'CGT Harvester', 'Summary']

export function TaxOptimiser() {
  const [tab, setTab] = useState(3)  // default to Summary
  const { activeScenarioPath } = useConfigStore()

  const { data: summary, isLoading: sumLoading } = useQuery<SummaryData>({
    queryKey: ['tax-optimiser-summary', activeScenarioPath],
    queryFn: () => apiClient.get(`/tax-optimiser/summary?scenario_path=${encodeURIComponent(activeScenarioPath)}`).then(r => r.data),
    staleTime: 120_000,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h2 style={{ color: '#e8edf2', fontSize: 20, fontWeight: 700, margin: 0 }}>
          Tax Optimiser
        </h2>
        <p style={{ color: '#8fa3b8', fontSize: 13, marginTop: 4, marginBottom: 0 }}>
          Band-filling · UFPLS vs PCLS · CGT harvesting · Scottish rates
        </p>
      </div>

      {/* Total saving strip */}
      {summary && !sumLoading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
          <KPI label="Total lifetime saving"     value={fmt(summary.total_saving_gbp)}          accent={TEAL} />
          <KPI label="Band-filler saving"        value={fmt(summary.band_fill_saving_gbp)}       accent={GREEN} />
          <KPI label="UFPLS/PCLS strategy"       value={fmt(summary.ufpls_saving_gbp)}           accent={GOLD} />
          <KPI label="CGT harvest saving"        value={fmt(summary.cgt_harvest_saving_gbp)}     accent={PURP} />
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, background: '#162236', borderRadius: 8, padding: 4 }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)} style={{
            flex: 1, padding: '8px 4px', borderRadius: 6, border: 'none', cursor: 'pointer',
            fontSize: 12, fontWeight: tab === i ? 600 : 400,
            background: tab === i ? TEAL : 'transparent',
            color: tab === i ? '#fff' : '#8fa3b8',
          }}>{t}</button>
        ))}
      </div>

      {tab === 0 && <BandFillerTab scenarioPath={activeScenarioPath} />}
      {tab === 1 && <UFPLSTab scenarioPath={activeScenarioPath} />}
      {tab === 2 && <CGTTab scenarioPath={activeScenarioPath} />}
      {tab === 3 && (
        sumLoading
          ? <Loading text="Running all optimisation strategies…" />
          : summary
          ? <SummaryTab data={summary} />
          : <div style={{ color: RED, fontSize: 13 }}>Failed to load summary.</div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
