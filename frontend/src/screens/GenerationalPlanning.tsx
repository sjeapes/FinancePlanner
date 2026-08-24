import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, Legend,
} from 'recharts'
import { apiClient } from '../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface KeyAge {
  year: number; age: number
  uk_wealth_gbp: number; us_wealth_gbp: number; delta_gbp: number
  uk_annual_tax: number; us_annual_tax_gbp: number
  uk_healthcare: number; us_healthcare_gbp: number
}

interface ComparisonReport {
  macro_scenario: string; fx_rate: number
  comparison_key_ages: KeyAge[]
  break_even_year: number | null
  uk_estate_net_gbp: number; us_estate_net_gbp: number
  us_advantage_at_retirement_gbp: number
  lifetime_tax_delta_gbp: number
  lifetime_healthcare_delta_gbp: number
  uk_offspring: OffspringSummary[]
  us_offspring: OffspringSummary[]
  career_paths: CareerSummary[]
  warnings: string[]
}

interface OffspringSummary {
  name: string; career_path: string; country: string
  fire_year: number | null; fire_age: number | null
  peak_net_worth: number; lifetime_tax: number; lifetime_earnings: number
  university_cost: UnivCost
  wealth_at_key_years: Record<number, number>
}

interface UnivCost {
  country: string; total_tuition: number; total_living: number
  parental_outlay: number; loan_taken: number
  loan_balance_at_graduation: number; projected_loan_write_off: boolean
  projected_loan_repayment_years: number
}

interface CareerSummary {
  career_id: string; label: string
  uk_entry: number; uk_peak: number
  us_entry: number; us_peak: number
}

interface FamilyTimeline {
  years: number[]
  combined_family_wealth: number[]
  parent_wealth: number[]
  offspring_wealth: number[]
  fire_years: Record<string, number | null>
  wealth_transfer: { net_to_offspring_gbp: number; net_to_offspring_usd: number; iht_liability_gbp: number }
  warnings: string[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (n: number, currency = 'GBP') => {
  const symbol = currency === 'USD' ? '$' : '£'
  if (Math.abs(n) >= 1_000_000) return `${symbol}${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `${symbol}${(n / 1_000).toFixed(0)}k`
  return `${symbol}${n.toFixed(0)}`
}

const TEAL  = '#0e9aad'
const GOLD  = '#d4a843'
const GREEN = '#2dbd7e'
const RED   = '#e05252'
const PURP  = '#a78bfa'

const TABS = ['Country Comparison', 'Family Timeline', 'Career Paths', 'Estate & IHT', 'Sensitivity']

// ── Shared components ─────────────────────────────────────────────────────────

function Card({ title, children, accent = TEAL }: { title?: string; children: React.ReactNode; accent?: string }) {
  return (
    <div style={{ background: '#162236', borderRadius: 12, padding: 20,
                  borderLeft: `3px solid ${accent}` }}>
      {title && <h3 style={{ color: '#e8edf2', fontSize: 12, fontWeight: 600,
                             textTransform: 'uppercase', letterSpacing: '0.06em',
                             marginBottom: 14, margin: 0, marginBottom: 12 }}>{title}</h3>}
      {children}
    </div>
  )
}

function KPI({ label, value, sub, accent = TEAL }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div style={{ background: '#162236', borderRadius: 10, padding: '14px 18px', borderTop: `2px solid ${accent}` }}>
      <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ color: '#e8edf2', fontSize: 20, fontWeight: 700, fontFamily: 'DM Mono, monospace', marginTop: 4 }}>{value}</div>
      {sub && <div style={{ color: '#8b949e', fontSize: 10, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Pill({ label, colour }: { label: string; colour: string }) {
  return <span style={{ background: `${colour}22`, color: colour, border: `1px solid ${colour}44`,
                        borderRadius: 4, padding: '2px 8px', fontSize: 10, fontWeight: 600 }}>{label}</span>
}

// ── Tab 1: Country Comparison ─────────────────────────────────────────────────

function CountryComparisonTab({ data }: { data: ComparisonReport }) {
  const ka = data.comparison_key_ages
  const chartData = ka.map(k => ({
    age: k.age, UK: Math.round(k.uk_wealth_gbp / 1000), US: Math.round(k.us_wealth_gbp / 1000),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* KPI strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <KPI label="US advantage at retirement" value={fmt(data.us_advantage_at_retirement_gbp)}
             accent={data.us_advantage_at_retirement_gbp > 0 ? GREEN : RED} />
        <KPI label="Break-even year" value={data.break_even_year ? String(data.break_even_year) : 'No crossover'} accent={GOLD} />
        <KPI label="Lifetime tax delta (US−UK)" value={fmt(data.lifetime_tax_delta_gbp)} accent={RED} sub="GBP" />
        <KPI label="Lifetime healthcare delta" value={fmt(data.lifetime_healthcare_delta_gbp)} accent={PURP} sub="GBP — US pays more" />
      </div>

      {/* Wealth trajectory */}
      <Card title="Wealth Trajectory — UK vs US Path (GBP)">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData}>
            <XAxis dataKey="age" tick={{ fill: '#8b949e', fontSize: 9 }} label={{ value: 'Age', position: 'insideBottom', fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v}k`, n + ' path']}
                     contentStyle={{ background: '#0f1b2d', border: '1px solid #30363d', borderRadius: 8, color: '#e8edf2' }} />
            <Legend iconType="line" wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Line dataKey="UK" stroke={TEAL} strokeWidth={2} dot={false} name="UK" />
            <Line dataKey="US" stroke={GOLD} strokeWidth={2} dot={false} name="US" />
            {data.break_even_year && (
              <ReferenceLine x={data.break_even_year - 1980} stroke={GREEN}
                             strokeDasharray="4 2" label={{ value: `Break-even ${data.break_even_year}`, fill: GREEN, fontSize: 9 }} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Key ages table */}
      <Card title="Key Ages — Wealth, Tax, Healthcare Comparison">
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ color: '#8b949e', textAlign: 'right' }}>
                {['Age', 'UK Wealth', 'US Wealth', 'Delta', 'UK Tax', 'US Tax', 'UK Health', 'US Health'].map(h => (
                  <th key={h} style={{ padding: '6px 10px', fontWeight: 500, borderBottom: '1px solid #1d2f47', textAlign: h === 'Age' ? 'left' : 'right' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ka.map(k => (
                <tr key={k.age} style={{ borderBottom: '1px solid #162236' }}>
                  <td style={{ padding: '7px 10px', color: '#0e9aad', fontWeight: 600 }}>{k.age}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>{fmt(k.uk_wealth_gbp)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#e8edf2' }}>{fmt(k.us_wealth_gbp)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: k.delta_gbp > 0 ? GREEN : RED }}>{k.delta_gbp > 0 ? '+' : ''}{fmt(k.delta_gbp)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#8fa3b8' }}>{fmt(k.uk_annual_tax)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#8fa3b8' }}>{fmt(k.us_annual_tax_gbp)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: '#3fb950' }}>{fmt(k.uk_healthcare)}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'DM Mono, monospace', color: RED }}>{fmt(k.us_healthcare_gbp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── Tab 2: Family Timeline ────────────────────────────────────────────────────

function FamilyTimelineTab({ country, macro }: { country: string; macro: string }) {
  const { data, isLoading } = useQuery<FamilyTimeline>({
    queryKey: ['family-timeline', country, macro],
    queryFn: () => apiClient.get(`/generational/family-timeline?country=${country}&macro_scenario=${macro}`).then(r => r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <div style={{ color: '#8fa3b8', padding: 40, textAlign: 'center' }}>Loading family timeline…</div>
  if (!data) return null

  const chartData = data.years
    .filter(y => y % 2 === 0)
    .map(y => {
      const i = data.years.indexOf(y)
      return { year: y, Parents: Math.round((data.parent_wealth[i] || 0) / 1000), Offspring: Math.round((data.offspring_wealth[i] || 0) / 1000), Combined: Math.round((data.combined_family_wealth[i] || 0) / 1000) }
    })

  const transfer = data.wealth_transfer

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
        <KPI label="Estate to offspring (net of IHT)" value={fmt(transfer.net_to_offspring_gbp)} accent={GREEN} />
        <KPI label="IHT paid" value={fmt(transfer.iht_liability_gbp)} accent={RED} />
        <KPI label="US path equivalent" value={fmt(transfer.net_to_offspring_usd, 'USD')} accent={GOLD} />
      </div>
      <Card title={`Combined Family Wealth 2026–2109 (${country.toUpperCase()} path, ${macro})`}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <XAxis dataKey="year" tick={{ fill: '#8b949e', fontSize: 9 }} />
            <YAxis tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
            <Tooltip formatter={(v: number, n: string) => [`£${v}k`, n]}
                     contentStyle={{ background: '#0f1b2d', border: '1px solid #30363d', borderRadius: 8, color: '#e8edf2' }} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8fa3b8' }} />
            <Line dataKey="Combined" stroke={TEAL} strokeWidth={2.5} dot={false} />
            <Line dataKey="Parents"  stroke={GOLD}  strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
            <Line dataKey="Offspring" stroke={GREEN} strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
            {Object.entries(data.fire_years).filter(([,v]) => v).map(([id, yr]) => (
              <ReferenceLine key={id} x={yr!} stroke={PURP} strokeDasharray="3 2"
                             label={{ value: `FIRE ${yr}`, fill: PURP, fontSize: 8 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}

// ── Tab 3: Career Paths ───────────────────────────────────────────────────────

function CareerPathsTab({ data }: { data: ComparisonReport }) {
  const [selected, setSelected] = useState(data.career_paths[0]?.career_id ?? '')
  const careers = data.career_paths
  const sel = careers.find(c => c.career_id === selected)

  // Build salary bar data for selected career
  const salaryData = sel ? [
    { label: 'UK Entry',  value: Math.round(sel.uk_entry / 1000), country: 'UK' },
    { label: 'UK Peak',   value: Math.round(sel.uk_peak / 1000),  country: 'UK' },
    { label: 'US Entry',  value: Math.round(sel.us_entry / 1000), country: 'US' },
    { label: 'US Peak',   value: Math.round(sel.us_peak / 1000),  country: 'US' },
  ] : []

  // Offspring FIRE comparison
  const offspringData = data.uk_offspring.map((o, i) => {
    const us = data.us_offspring[i]
    return { name: o.name, uk_fire: o.fire_age ?? 99, us_fire: us?.fire_age ?? 99,
             uk_peak: Math.round(o.peak_net_worth / 1000), us_peak: Math.round((us?.peak_net_worth ?? 0) / 1000) }
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Career selector */}
      <Card title="Select Career Path">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {careers.map(c => (
            <button key={c.career_id} onClick={() => setSelected(c.career_id)} style={{
              padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12,
              background: selected === c.career_id ? TEAL : '#1d2f47',
              color: selected === c.career_id ? '#fff' : '#8fa3b8',
            }}>{c.label}</button>
          ))}
        </div>
      </Card>

      {sel && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card title={`${sel.label} — Salary Range (£k / $k)`}>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={salaryData}>
                <XAxis dataKey="label" tick={{ fill: '#8b949e', fontSize: 9 }} />
                <YAxis tickFormatter={v => `${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
                <Tooltip formatter={(v: number, n: string) => [`${v}k`, n]}
                         contentStyle={{ background: '#0f1b2d', border: '1px solid #30363d', borderRadius: 8 }} />
                <Bar dataKey="value" radius={[4,4,0,0]}>
                  {salaryData.map((d, i) => <Cell key={i} fill={d.country === 'UK' ? TEAL : GOLD} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Key Metrics">
            {[
              { label: 'UK Entry Salary',  value: fmt(sel.uk_entry),  accent: TEAL },
              { label: 'UK Peak Salary',   value: fmt(sel.uk_peak),   accent: TEAL },
              { label: 'US Entry Salary',  value: `$${(sel.us_entry/1000).toFixed(0)}k`, accent: GOLD },
              { label: 'US Peak Salary',   value: `$${(sel.us_peak/1000).toFixed(0)}k`, accent: GOLD },
              { label: 'US/UK entry ratio', value: `${(sel.us_entry / sel.uk_entry).toFixed(1)}×`, accent: GREEN },
            ].map(m => (
              <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #1d2f47' }}>
                <span style={{ color: '#8fa3b8', fontSize: 12 }}>{m.label}</span>
                <span style={{ color: m.accent, fontFamily: 'DM Mono, monospace', fontSize: 13, fontWeight: 600 }}>{m.value}</span>
              </div>
            ))}
          </Card>
        </div>
      )}

      {/* Offspring outcomes */}
      {offspringData.length > 0 && (
        <Card title="Offspring — UK vs US Outcomes">
          {offspringData.map(o => (
            <div key={o.name} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, padding: '10px 0', borderBottom: '1px solid #1d2f47' }}>
              <div style={{ color: '#e8edf2', fontWeight: 600 }}>{o.name}</div>
              <div><span style={{ color: '#8b949e', fontSize: 11 }}>UK FIRE age: </span><span style={{ color: TEAL, fontFamily: 'DM Mono, monospace' }}>{o.uk_fire === 99 ? 'n/a' : o.uk_fire}</span></div>
              <div><span style={{ color: '#8b949e', fontSize: 11 }}>US FIRE age: </span><span style={{ color: GOLD, fontFamily: 'DM Mono, monospace' }}>{o.us_fire === 99 ? 'n/a' : o.us_fire}</span></div>
              <div><span style={{ color: '#8b949e', fontSize: 11 }}>UK/US peak: </span><span style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace' }}>£{o.uk_peak}k / ${o.us_peak}k</span></div>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

// ── Tab 4: Estate & IHT ────────────────────────────────────────────────────────

function EstateTab({ data }: { data: ComparisonReport }) {
  const estateData = [
    { name: 'UK Net Estate',    value: Math.round(data.uk_estate_net_gbp / 1000),  fill: TEAL },
    { name: 'US Net (in GBP)', value: Math.round(data.us_estate_net_gbp / 1000),  fill: GOLD },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <KPI label="UK estate to offspring (net IHT)" value={fmt(data.uk_estate_net_gbp)} accent={TEAL} />
        <KPI label="US estate to offspring (net, GBP)" value={fmt(data.us_estate_net_gbp)} accent={GOLD} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card title="Net Estate Comparison" accent={GREEN}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={estateData} layout="vertical">
              <XAxis type="number" tickFormatter={v => `£${v}k`} tick={{ fill: '#8b949e', fontSize: 9 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#8b949e', fontSize: 9 }} width={110} />
              <Tooltip formatter={(v: number) => [`£${v}k`, 'Net to offspring']}
                       contentStyle={{ background: '#0f1b2d', border: '1px solid #30363d', borderRadius: 8 }} />
              <Bar dataKey="value" radius={[0,4,4,0]}>
                {estateData.map((d,i) => <Cell key={i} fill={d.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Key Differences">
          {[
            { label: 'UK: IHT rate',           value: '40% above £1M (couple NRB+RNRB)' },
            { label: 'UK: SIPP status',        value: 'Outside estate (pre-2027)' },
            { label: 'UK: 7-year gift rule',   value: 'Gifts become exempt after 7yr' },
            { label: 'US: Exemption (2026)',   value: '$14M per person (OBBBA)' },
            { label: 'US: Rate above exempt',  value: '40% federal estate tax' },
            { label: 'US: Step-up basis',      value: 'Inherited assets: no CGT on gain' },
          ].map(r => (
            <div key={r.label} style={{ padding: '7px 0', borderBottom: '1px solid #1d2f47' }}>
              <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{r.label}</div>
              <div style={{ color: '#e8edf2', fontSize: 12, marginTop: 2 }}>{r.value}</div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}

// ── Tab 5: Sensitivity ────────────────────────────────────────────────────────

function SensitivityTab({ baseMacro, setMacro, baseFx, setFx }: {
  baseMacro: string; setMacro: (m: string) => void
  baseFx: string; setFx: (f: string) => void
}) {
  const fxRates = { low: 1.18, mid: 1.27, high: 1.38 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="Macro Scenario">
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {['low', 'mid', 'high'].map(s => (
            <button key={s} onClick={() => setMacro(s)} style={{
              flex: 1, padding: '10px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: baseMacro === s ? TEAL : '#1d2f47',
              color: baseMacro === s ? '#fff' : '#8fa3b8', fontWeight: 600, textTransform: 'capitalize',
            }}>{s}</button>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, fontSize: 11, color: '#8fa3b8' }}>
          {[{ s: 'low', inf: '3.5%', ret: '3.0%' }, { s: 'mid', inf: '2.5%', ret: '5.0%' }, { s: 'high', inf: '2.0%', ret: '7.5%' }].map(r => (
            <div key={r.s} style={{ padding: 10, background: '#0f1b2d', borderRadius: 8 }}>
              <div style={{ color: '#e8edf2', fontWeight: 600, marginBottom: 4, textTransform: 'capitalize' }}>{r.s}</div>
              <div>Inflation: {r.inf}</div>
              <div>Equity return: {r.ret}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="FX Rate (GBP / USD)">
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {Object.entries(fxRates).map(([s, rate]) => (
            <button key={s} onClick={() => setFx(s)} style={{
              flex: 1, padding: '10px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: baseFx === s ? GOLD : '#1d2f47',
              color: baseFx === s ? '#fff' : '#8fa3b8', fontWeight: 600,
            }}>{s.toUpperCase()} — {rate}</button>
          ))}
        </div>
        <div style={{ color: '#8b949e', fontSize: 12 }}>
          A stronger GBP (high scenario) makes the UK path more competitive in USD terms.
          A weaker GBP (low scenario) reduces the purchasing power of UK wealth internationally.
        </div>
      </Card>

      <Card title="What to Watch" accent={PURP}>
        {[
          { label: 'Healthcare delta is the biggest hidden cost', desc: 'The US ACA bridge ($26k/yr couple, ages 62–65) plus lifetime Medicare adds over £200k in costs absent from the UK path.' },
          { label: 'US step-up basis can exceed UK IHT saving', desc: 'For large portfolios with embedded gains, the US step-up basis (no CGT on death) may be worth more than the UK NRB+RNRB IHT shelter.' },
          { label: 'WA state = 0% state income tax', desc: 'A US working phase in WA can generate $350k+ of additional savings vs CA (9.3% state) over 2–3 years.' },
          { label: 'UK NHS removes longevity tail risk', desc: 'At age 85+, US late-life care ($36k/yr) dramatically outpaces the UK. The NHS effectively caps downside health costs.' },
        ].map(i => (
          <div key={i.label} style={{ padding: '10px 0', borderBottom: '1px solid #1d2f47' }}>
            <div style={{ color: '#e8edf2', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>→ {i.label}</div>
            <div style={{ color: '#8fa3b8', fontSize: 11 }}>{i.desc}</div>
          </div>
        ))}
      </Card>
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export function GenerationalPlanning() {
  const [tab,   setTab]   = useState(0)
  const [macro, setMacro] = useState('mid')
  const [fx,    setFx]    = useState('mid')
  const [timelineCountry, setTimelineCountry] = useState<'uk'|'us'>('uk')

  const { data, isLoading, error } = useQuery<ComparisonReport>({
    queryKey: ['generational-report', macro, fx],
    queryFn: () => apiClient.get(`/generational/report?macro_scenario=${macro}&fx_scenario=${fx}`).then(r => r.data),
    staleTime: 120_000,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ color: '#e8edf2', fontSize: 20, fontWeight: 700, margin: 0 }}>
            Generational & Cross-Jurisdiction Planning
          </h2>
          <p style={{ color: '#8fa3b8', fontSize: 13, marginTop: 4, marginBottom: 0 }}>
            Multi-generation wealth trajectory · UK vs US country comparison · Estate handoff
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ color: '#8b949e', fontSize: 11 }}>Macro:</span>
          {['low','mid','high'].map(s => (
            <button key={s} onClick={() => setMacro(s)} style={{
              padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 11,
              background: macro === s ? TEAL : '#1d2f47',
              color: macro === s ? '#fff' : '#8fa3b8',
            }}>{s}</button>
          ))}
          <span style={{ color: '#8b949e', fontSize: 11, marginLeft: 8 }}>FX:</span>
          {['low','mid','high'].map(s => (
            <button key={s} onClick={() => setFx(s)} style={{
              padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 11,
              background: fx === s ? GOLD : '#1d2f47',
              color: fx === s ? '#fff' : '#8fa3b8',
            }}>{s}</button>
          ))}
        </div>
      </div>

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

      {isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300, color: '#8fa3b8', gap: 12 }}>
          <div style={{ width: 20, height: 20, border: '2px solid #0e9aad', borderTopColor: 'transparent',
                        borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          Running generational projection…
        </div>
      )}

      {error && (
        <div style={{ color: RED, padding: 24, background: `${RED}11`, borderRadius: 8, border: `1px solid ${RED}44` }}>
          Failed to load generational data. Check the API is running and generational_config.yaml is present.
        </div>
      )}

      {data && !isLoading && (
        <>
          {tab === 0 && <CountryComparisonTab data={data} />}
          {tab === 1 && (
            <div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                {(['uk','us'] as const).map(c => (
                  <button key={c} onClick={() => setTimelineCountry(c)} style={{
                    padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
                    background: timelineCountry === c ? TEAL : '#1d2f47',
                    color: timelineCountry === c ? '#fff' : '#8fa3b8', fontSize: 12,
                  }}>{c.toUpperCase()} Path</button>
                ))}
              </div>
              <FamilyTimelineTab country={timelineCountry} macro={macro} />
            </div>
          )}
          {tab === 2 && <CareerPathsTab data={data} />}
          {tab === 3 && <EstateTab data={data} />}
          {tab === 4 && <SensitivityTab baseMacro={macro} setMacro={setMacro} baseFx={fx} setFx={setFx} />}

          {data.warnings.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {data.warnings.map((w, i) => (
                <div key={i} style={{ background: '#f0a50011', border: '1px solid #f0a50044', borderRadius: 8, padding: '10px 14px', color: '#f0a500', fontSize: 12 }}>⚠ {w}</div>
              ))}
            </div>
          )}
        </>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
