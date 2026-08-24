import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie,
} from 'recharts'
import { apiClient } from '../api/client'
import { useConfigStore } from '../store/configStore'

// ── Types ─────────────────────────────────────────────────────────────────────

interface IhtOpportunity {
  strategy: string
  estimated_saving: number
  priority: 'high' | 'medium' | 'low'
  notes: string
}

interface GiftRecord {
  gift_date: string
  amount: number
  recipient: string
  years_elapsed: number
  is_outside_estate: boolean
  taper_relief_pct: number
  effective_iht_rate: number
  iht_at_risk: number
  years_to_exempt: number
  notes: string
}

interface EstateResult {
  calculation_year: number
  gross_estate: number
  pension_outside_estate: number
  gifts_outside_estate: number
  net_estate: number
  nrb_available: number
  rnrb_available: number
  total_allowances: number
  taxable_estate: number
  iht_liability: number
  net_to_beneficiaries: number
  effective_iht_rate: number
  gift_tracker: GiftRecord[]
  gift_iht_at_risk: number
  annual_gift_allowance_remaining: number
  iht_reduction_opportunities: IhtOpportunity[]
  us_estate_tax: number
  warnings: string[]
}

interface SurvivorResult {
  deceased_person_id: string
  death_year: number
  total_income_lost: number
  survivor_gross_income: number
  survivor_pension_income: number
  expense_reduction: number
  recommended_life_cover: number
  life_cover_breakdown: Record<string, number>
  key_risks: string[]
  recommendations: string[]
  mortgage_affordability: {
    monthly_payment: number
    survivor_net_monthly: number
    affordability_ratio: number
    is_affordable: boolean
    monthly_shortfall: number
    outstanding_balance: number
  } | null
  warnings: string[]
}

interface RebalanceAlert {
  account_id: string
  account_name: string
  total_value: number
  current_allocation: Record<string, number>
  target_allocation: Record<string, number>
  drift: Record<string, number>
  max_drift: number
  status: 'ok' | 'amber' | 'rebalance_needed'
  trades_needed: Record<string, number>
  glide_adjusted: boolean
}

interface RebalanceResult {
  alerts: RebalanceAlert[]
  global_allocation: Record<string, number>
  global_target: Record<string, number>
  global_drift: Record<string, number>
  accounts_needing_action: string[]
  total_portfolio_value: number
  warnings: string[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  n >= 1_000_000
    ? `£${(n / 1_000_000).toFixed(2)}M`
    : n >= 1_000
    ? `£${(n / 1_000).toFixed(0)}k`
    : `£${n.toFixed(0)}`

const PRIORITY_COLOUR: Record<string, string> = {
  high:   '#3fb950',
  medium: '#f0a500',
  low:    '#8b949e',
}

const ALLOC_COLOURS: Record<string, string> = {
  equities:     '#0e9aad',
  bonds:        '#3fb950',
  cash:         '#f0a500',
  property:     '#a78bfa',
  alternatives: '#f97316',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Card({ title, children, accent }: {
  title: string; children: React.ReactNode; accent?: string
}) {
  return (
    <div style={{
      background: '#162236', borderRadius: 12, padding: 20,
      borderLeft: `3px solid ${accent ?? '#0e9aad'}`,
    }}>
      <h3 style={{ color: '#e8edf2', fontSize: 13, fontWeight: 600,
                   textTransform: 'uppercase', letterSpacing: '0.05em',
                   marginBottom: 16, margin: 0, marginBottom: 14 }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function MetricRow({ label, value, sub, highlight }: {
  label: string; value: string; sub?: string; highlight?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between',
                  alignItems: 'baseline', padding: '6px 0',
                  borderBottom: '1px solid #1d2f47' }}>
      <span style={{ color: '#8fa3b8', fontSize: 12 }}>{label}</span>
      <div style={{ textAlign: 'right' }}>
        <span style={{
          color: highlight ? '#f85149' : '#e8edf2',
          fontSize: 14, fontFamily: 'DM Mono, monospace', fontWeight: 600,
        }}>{value}</span>
        {sub && <div style={{ color: '#8b949e', fontSize: 10 }}>{sub}</div>}
      </div>
    </div>
  )
}

function Pill({ label, colour }: { label: string; colour: string }) {
  return (
    <span style={{
      background: colour + '22', color: colour,
      border: `1px solid ${colour}44`,
      borderRadius: 4, padding: '2px 8px', fontSize: 10, fontWeight: 600,
    }}>{label}</span>
  )
}

function EstateWaterfall({ data }: { data: EstateResult }) {
  const bars = [
    { name: 'Gross Estate',       value: data.gross_estate,             fill: '#0e9aad' },
    { name: 'Pension Excluded',   value: -data.pension_outside_estate,  fill: '#3fb950' },
    { name: 'Gifts (>7yr)',       value: -data.gifts_outside_estate,    fill: '#3fb950' },
    { name: 'Net Estate',         value: data.net_estate,               fill: '#58a6ff' },
    { name: 'Allowances',         value: -data.total_allowances,        fill: '#3fb950' },
    { name: 'Taxable Estate',     value: data.taxable_estate,           fill: '#f0a500' },
    { name: 'IHT (40%)',          value: -data.iht_liability,           fill: '#f85149' },
    { name: 'To Beneficiaries',   value: data.net_to_beneficiaries,     fill: '#2dbd7e' },
  ]
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={bars} margin={{ top: 4, right: 8, bottom: 24, left: 8 }}>
        <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 9 }}
               angle={-30} textAnchor="end" interval={0} />
        <YAxis tickFormatter={v => fmt(Math.abs(v))}
               tick={{ fill: '#8b949e', fontSize: 9 }} />
        <Tooltip
          formatter={(v: number) => [fmt(Math.abs(v)), '']}
          contentStyle={{ background: '#0f1b2d', border: '1px solid #30363d',
                          borderRadius: 8, color: '#e8edf2' }}
        />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {bars.map((b, i) => <Cell key={i} fill={b.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function AllocationDonut({ alloc, target }: {
  alloc: Record<string, number>; target: Record<string, number>
}) {
  const classes = ['equities', 'bonds', 'cash', 'property', 'alternatives']
  const data = classes
    .filter(c => (alloc[c] ?? 0) > 0)
    .map(c => ({ name: c, value: alloc[c] ?? 0 }))

  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
      <ResponsiveContainer width={160} height={160}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name"
               cx="50%" cy="50%" innerRadius={45} outerRadius={70}
               paddingAngle={2}>
            {data.map((d, i) => (
              <Cell key={i} fill={ALLOC_COLOURS[d.name] ?? '#8b949e'} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div style={{ flex: 1 }}>
        {classes.map(c => {
          const cur = alloc[c] ?? 0
          const tgt = target[c] ?? 0
          const drift = cur - tgt
          return (
            <div key={c} style={{ display: 'flex', justifyContent: 'space-between',
                                  padding: '3px 0', fontSize: 11 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2,
                               background: ALLOC_COLOURS[c] ?? '#8b949e' }} />
                <span style={{ color: '#8fa3b8', textTransform: 'capitalize' }}>{c}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, fontFamily: 'DM Mono, monospace' }}>
                <span style={{ color: '#e8edf2' }}>{cur.toFixed(1)}%</span>
                <span style={{ color: Math.abs(drift) >= 5 ? '#f85149' : '#8b949e' }}>
                  {drift >= 0 ? '+' : ''}{drift.toFixed(1)}pp
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export function EstatePlanner() {
  const { activeScenarioPath } = useConfigStore()
  const [survivorTab, setSurvivorTab] = useState<'person1' | 'person2'>('person1')

  const params = `?scenario_path=${encodeURIComponent(activeScenarioPath)}`

  const estate = useQuery<EstateResult>({
    queryKey: ['estate', activeScenarioPath],
    queryFn: () => apiClient.get(`/planning/estate${params}`).then(r => r.data),
    staleTime: 60_000,
  })

  const survivor1 = useQuery<SurvivorResult>({
    queryKey: ['survivor', 'person1', activeScenarioPath],
    queryFn: () =>
      apiClient.get(`/planning/survivor${params}&deceased_person_id=person1&death_year=2060`)
               .then(r => r.data),
    staleTime: 60_000,
  })

  const survivor2 = useQuery<SurvivorResult>({
    queryKey: ['survivor', 'person2', activeScenarioPath],
    queryFn: () =>
      apiClient.get(`/planning/survivor${params}&deceased_person_id=person2&death_year=2060`)
               .then(r => r.data),
    staleTime: 60_000,
  })

  const rebalance = useQuery<RebalanceResult>({
    queryKey: ['rebalancing', activeScenarioPath],
    queryFn: () => apiClient.get(`/planning/rebalancing${params}&owner_age=43`).then(r => r.data),
    staleTime: 60_000,
  })

  const loading = estate.isLoading || survivor1.isLoading || rebalance.isLoading
  const error   = estate.error || survivor1.error || rebalance.error

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                  height: 300, color: '#8fa3b8', gap: 12 }}>
      <div style={{ width: 20, height: 20, border: '2px solid #0e9aad',
                    borderTopColor: 'transparent', borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite' }} />
      Loading estate analysis…
    </div>
  )

  if (error) return (
    <div style={{ color: '#f85149', padding: 24, background: '#f8514922',
                  borderRadius: 8, border: '1px solid #f8514944' }}>
      Failed to load estate data. Check the API is running and the scenario is valid.
    </div>
  )

  const est = estate.data!
  const sv  = survivorTab === 'person1' ? survivor1.data : survivor2.data
  const rb  = rebalance.data!

  const globalDriftOk = Math.max(...Object.values(rb.global_drift).map(Math.abs)) < 5

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Header */}
      <div>
        <h2 style={{ color: '#e8edf2', fontSize: 20, fontWeight: 700, margin: 0 }}>
          Estate &amp; Advanced Planning
        </h2>
        <p style={{ color: '#8fa3b8', fontSize: 13, marginTop: 4, marginBottom: 0 }}>
          IHT liability, survivor impact, gift tracker, and portfolio rebalancing —
          updated for {est.calculation_year}
        </p>
      </div>

      {/* Top KPI strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { label: 'Gross Estate',         value: fmt(est.gross_estate),       accent: '#0e9aad' },
          { label: 'IHT Liability',         value: fmt(est.iht_liability),      accent: '#f85149' },
          { label: 'Net to Beneficiaries',  value: fmt(est.net_to_beneficiaries), accent: '#2dbd7e' },
          { label: 'Effective IHT Rate',    value: `${(est.effective_iht_rate * 100).toFixed(1)}%`, accent: '#f0a500' },
        ].map(k => (
          <div key={k.label} style={{
            background: '#162236', borderRadius: 10, padding: '14px 18px',
            borderTop: `2px solid ${k.accent}`,
          }}>
            <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase',
                          letterSpacing: '0.06em' }}>{k.label}</div>
            <div style={{ color: '#e8edf2', fontSize: 22, fontWeight: 700,
                          fontFamily: 'DM Mono, monospace', marginTop: 4 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Warnings */}
      {est.warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {est.warnings.map((w, i) => (
            <div key={i} style={{ background: '#f0a50011', border: '1px solid #f0a50044',
                                  borderRadius: 8, padding: '10px 14px',
                                  color: '#f0a500', fontSize: 12 }}>
              ⚠ {w}
            </div>
          ))}
        </div>
      )}

      {/* Row 1: Waterfall + IHT breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 16 }}>
        <Card title="Estate Waterfall">
          <EstateWaterfall data={est} />
        </Card>

        <Card title="IHT Breakdown">
          <MetricRow label="Gross Estate"         value={fmt(est.gross_estate)} />
          <MetricRow label="Pension (excl.)"      value={`-${fmt(est.pension_outside_estate)}`} />
          <MetricRow label="Gifts outside 7yr"    value={`-${fmt(est.gifts_outside_estate)}`} />
          <MetricRow label="Net Estate"           value={fmt(est.net_estate)} />
          <MetricRow label="NRB Available"        value={fmt(est.nrb_available)} />
          <MetricRow label="RNRB Available"       value={fmt(est.rnrb_available)} />
          <MetricRow label="Total Allowances"     value={fmt(est.total_allowances)} />
          <MetricRow label="Taxable Estate"       value={fmt(est.taxable_estate)} highlight={est.taxable_estate > 0} />
          <MetricRow label="IHT @ 40%"            value={fmt(est.iht_liability)} highlight={est.iht_liability > 0} />
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #0e9aad44' }}>
            <MetricRow label="Net to Beneficiaries" value={fmt(est.net_to_beneficiaries)} />
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: '#8b949e' }}>
            Annual gift allowance remaining:{' '}
            <span style={{ color: '#3fb950', fontFamily: 'DM Mono, monospace' }}>
              {fmt(est.annual_gift_allowance_remaining)}
            </span>
          </div>
        </Card>
      </div>

      {/* Row 2: IHT reduction opportunities */}
      <Card title="IHT Reduction Opportunities">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {est.iht_reduction_opportunities.map((op, i) => (
            <div key={i} style={{
              background: '#0f1b2d', borderRadius: 8, padding: 14,
              border: `1px solid ${PRIORITY_COLOUR[op.priority]}33`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            alignItems: 'flex-start', marginBottom: 8 }}>
                <Pill label={op.priority.toUpperCase()} colour={PRIORITY_COLOUR[op.priority]} />
                <span style={{ color: '#3fb950', fontFamily: 'DM Mono, monospace',
                               fontSize: 13, fontWeight: 700 }}>
                  Save {fmt(op.estimated_saving)}
                </span>
              </div>
              <div style={{ color: '#e8edf2', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
                {op.strategy}
              </div>
              <div style={{ color: '#8b949e', fontSize: 11, lineHeight: 1.5 }}>
                {op.notes}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Row 3: Gift tracker */}
      {est.gift_tracker.length > 0 && (
        <Card title="Gift Tracker — 7-Year Rule">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: '#8b949e', textAlign: 'left' }}>
                  {['Date', 'Recipient', 'Amount', 'Years Elapsed',
                    'Taper Relief', 'IHT at Risk', 'Status'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', fontWeight: 500,
                                        borderBottom: '1px solid #1d2f47' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {est.gift_tracker.map((g, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #162236' }}>
                    <td style={{ padding: '7px 10px', color: '#8fa3b8' }}>{g.gift_date}</td>
                    <td style={{ padding: '7px 10px', color: '#e8edf2' }}>{g.recipient}</td>
                    <td style={{ padding: '7px 10px', fontFamily: 'DM Mono, monospace',
                                 color: '#e8edf2' }}>{fmt(g.amount)}</td>
                    <td style={{ padding: '7px 10px', fontFamily: 'DM Mono, monospace',
                                 color: '#e8edf2' }}>{g.years_elapsed.toFixed(1)} yr</td>
                    <td style={{ padding: '7px 10px', fontFamily: 'DM Mono, monospace',
                                 color: g.taper_relief_pct > 0 ? '#3fb950' : '#8b949e' }}>
                      {g.taper_relief_pct.toFixed(0)}%
                    </td>
                    <td style={{ padding: '7px 10px', fontFamily: 'DM Mono, monospace',
                                 color: g.iht_at_risk > 0 ? '#f85149' : '#3fb950' }}>
                      {g.iht_at_risk > 0 ? fmt(g.iht_at_risk) : '—'}
                    </td>
                    <td style={{ padding: '7px 10px' }}>
                      {g.is_outside_estate
                        ? <Pill label="EXEMPT" colour="#3fb950" />
                        : <Pill label={`${g.years_to_exempt.toFixed(1)}yr to exempt`} colour="#f0a500" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {est.gift_iht_at_risk > 0 && (
              <div style={{ marginTop: 10, fontSize: 11, color: '#f85149' }}>
                Total IHT at risk from recent gifts: {fmt(est.gift_iht_at_risk)}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Row 4: Survivor simulation */}
      <Card title="Survivor Impact Simulation">
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {(['person1', 'person2'] as const).map(p => (
            <button key={p} onClick={() => setSurvivorTab(p)} style={{
              padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: survivorTab === p ? '#0e9aad' : '#1d2f47',
              color: survivorTab === p ? '#fff' : '#8fa3b8', fontSize: 12,
            }}>
              If {p === 'person1' ? 'Person 1' : 'Person 2'} dies
            </button>
          ))}
        </div>

        {sv && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div>
              <MetricRow label="Income lost"            value={fmt(sv.total_income_lost)} highlight />
              <MetricRow label="Survivor gross income"  value={fmt(sv.survivor_gross_income)} />
              <MetricRow label="Survivor pension income" value={fmt(sv.survivor_pension_income)} />
              <MetricRow label="Expense reduction"      value={`-${fmt(sv.expense_reduction)}`} />
              <MetricRow label="Recommended life cover" value={fmt(sv.recommended_life_cover)} />
              {sv.mortgage_affordability && (
                <MetricRow
                  label="Mortgage affordability"
                  value={sv.mortgage_affordability.is_affordable ? 'Affordable' : 'AT RISK'}
                  highlight={!sv.mortgage_affordability.is_affordable}
                  sub={`${(sv.mortgage_affordability.affordability_ratio * 100).toFixed(0)}% of net income`}
                />
              )}
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 8,
                            textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Key Risks
              </div>
              {sv.key_risks.length === 0
                ? <div style={{ color: '#3fb950', fontSize: 12 }}>No significant risks identified.</div>
                : sv.key_risks.map((r, i) => (
                    <div key={i} style={{ color: '#f85149', fontSize: 12, padding: '3px 0',
                                          borderBottom: '1px solid #1d2f47' }}>⚠ {r}</div>
                  ))}
              <div style={{ fontSize: 11, color: '#8b949e', marginTop: 12, marginBottom: 8,
                            textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Recommendations
              </div>
              {sv.recommendations.map((r, i) => (
                <div key={i} style={{ color: '#8fa3b8', fontSize: 11, padding: '3px 0',
                                      borderBottom: '1px solid #1d2f47' }}>
                  → {r}
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Row 5: Portfolio rebalancing */}
      <Card title="Portfolio Rebalancing" accent={globalDriftOk ? '#3fb950' : '#f0a500'}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', marginBottom: 16 }}>
          <span style={{ color: '#8fa3b8', fontSize: 12 }}>
            Total portfolio: {' '}
            <span style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace', fontWeight: 700 }}>
              {fmt(rb.total_portfolio_value)}
            </span>
          </span>
          {rb.accounts_needing_action.length > 0
            ? <Pill label={`${rb.accounts_needing_action.length} account(s) need rebalancing`} colour="#f0a500" />
            : <Pill label="Portfolio on target" colour="#3fb950" />}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <AllocationDonut alloc={rb.global_allocation} target={rb.global_target} />
          </div>
          <div>
            {rb.alerts.map(alert => (
              <div key={alert.account_id} style={{
                background: '#0f1b2d', borderRadius: 8, padding: 12, marginBottom: 8,
                border: `1px solid ${
                  alert.status === 'rebalance_needed' ? '#f8514944'
                  : alert.status === 'amber' ? '#f0a50044' : '#1d2f47'
                }`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between',
                              alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ color: '#e8edf2', fontSize: 12, fontWeight: 600 }}>
                    {alert.account_name}
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {alert.glide_adjusted && <Pill label="GLIDE PATH" colour="#a78bfa" />}
                    <Pill
                      label={alert.status === 'ok' ? 'ON TARGET' : alert.status === 'amber' ? 'AMBER' : 'REBALANCE'}
                      colour={alert.status === 'ok' ? '#3fb950' : alert.status === 'amber' ? '#f0a500' : '#f85149'}
                    />
                  </div>
                </div>
                <div style={{ fontSize: 11, color: '#8fa3b8' }}>
                  Max drift: {' '}
                  <span style={{
                    fontFamily: 'DM Mono, monospace',
                    color: alert.max_drift >= 10 ? '#f85149' : alert.max_drift >= 5 ? '#f0a500' : '#3fb950',
                  }}>
                    {alert.max_drift.toFixed(1)}pp
                  </span>
                  {' · '}
                  {fmt(alert.total_value)}
                </div>
                {alert.status !== 'ok' && (
                  <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {Object.entries(alert.trades_needed)
                      .filter(([, v]) => Math.abs(v) > 100)
                      .map(([cls, amt]) => (
                        <span key={cls} style={{
                          fontSize: 10, fontFamily: 'DM Mono, monospace',
                          color: amt > 0 ? '#3fb950' : '#f85149',
                          background: amt > 0 ? '#3fb95011' : '#f8514911',
                          padding: '2px 6px', borderRadius: 4,
                        }}>
                          {cls} {amt > 0 ? '+' : ''}{fmt(amt)}
                        </span>
                      ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </Card>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
