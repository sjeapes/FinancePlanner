/**
 * RetirementPlanner.tsx — Phase 4 retirement analysis
 * 4 tabs: Income Coverage · Drawdown Strategy · Annuity vs Drawdown · State Pension
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
  ReferenceLine, Cell,
} from 'recharts'
import { PageHeader } from '../components/layout/PageHeader'
import { useSimulationStore } from '../store/simulationStore'
import { useConfigStore } from '../store/configStore'
import { apiClient } from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(v: number) {
  if (v >= 1_000_000) return `£${(v/1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v/1_000).toFixed(0)}k`
  return `£${Math.round(v).toLocaleString()}`
}

const tipStyle = { background: '#0f1b2d', border: '1px solid #30363d',
                   borderRadius: 8, color: '#e8edf2', fontSize: 11 }

const TEAL='#0e9aad', GOLD='#d4a843', GREEN='#2dbd7e', RED='#e05252',
      PURP='#a78bfa', ORNG='#f97316'

function Card({ title, children, accent=TEAL }: {
  title?: string; children: React.ReactNode; accent?: string
}) {
  return (
    <div style={{ background:'#162236', borderRadius:12, padding:18,
                  borderLeft:`3px solid ${accent}`, marginBottom:14 }}>
      {title && <h3 style={{ color:'#e8edf2', fontSize:11, fontWeight:600,
                              textTransform:'uppercase', letterSpacing:'0.06em',
                              margin:'0 0 14px' }}>{title}</h3>}
      {children}
    </div>
  )
}

function KPI({ label, value, sub, accent=TEAL }: {
  label:string; value:string; sub?:string; accent?:string
}) {
  return (
    <div style={{ background:'#0f1b2d', borderRadius:10, padding:'12px 16px',
                  borderTop:`2px solid ${accent}` }}>
      <div style={{ color:'#8fa3b8', fontSize:10, textTransform:'uppercase',
                    letterSpacing:'0.06em' }}>{label}</div>
      <div style={{ color:'#e8edf2', fontSize:19, fontWeight:700,
                    fontFamily:'DM Mono, monospace', marginTop:4 }}>{value}</div>
      {sub && <div style={{ color:'#8b949e', fontSize:10, marginTop:2 }}>{sub}</div>}
    </div>
  )
}

function Loading({ text='Loading…' }: { text?: string }) {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
                  height:180, color:'#8fa3b8', gap:10, fontSize:13 }}>
      <div style={{ width:16, height:16, border:`2px solid ${TEAL}`,
                    borderTopColor:'transparent', borderRadius:'50%',
                    animation:'spin 0.8s linear infinite' }} />
      {text}
    </div>
  )
}

function Err({ msg }: { msg: string }) {
  return <div style={{ color:RED, background:`${RED}11`, borderRadius:8,
                        padding:'12px 16px', fontSize:13 }}>⚠ {msg}</div>
}

// ── Tab 1: Income Coverage ─────────────────────────────────────────────────────
// Field names below match backend/api/routes/retirement.py's
// IncomeCoverageReportOut/IncomeCoverageRowOut exactly — a previous version
// of this tab used a different, older shape (rows/age/surplus_shortfall)
// that the backend never actually returned, which threw on data.rows.filter(...)
// being undefined and blanked the whole page on load (this tab is the
// default active tab). Always check the actual Pydantic response model in
// retirement.py before changing field references here again.

interface IncomeSource { label: string; source_type: string; annual_gross: number
                          is_taxable: boolean; person_id: string }
interface CovRow { year: number; total_income: number; total_expenses: number
                    coverage_ratio: number; surplus_deficit: number
                    income_breakdown: IncomeSource[]; status: string; months_funded: number }
interface CovData { years: CovRow[]; first_shortfall_year: number|null
                     worst_coverage_year: number; worst_coverage_ratio: number
                     avg_coverage_ratio: number; total_surplus: number
                     total_shortfall: number; warnings: string[] }

function IncomeCoverageTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<CovData>({
    queryKey: ['income-coverage', path],
    queryFn: () => apiClient.get(`/retirement/income-coverage?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Analysing income coverage…" />
  if (isError || !data) return <Err msg="Failed to load income coverage. Run a simulation first." />

  const chartData = data.years.filter(r=>r.year % 2===0).map(r => ({
    year: r.year,
    Income: Math.round(r.total_income),
    Expenses: Math.round(r.total_expenses),
    Surplus: Math.max(0, r.surplus_deficit),
    Shortfall: Math.min(0, r.surplus_deficit),
  }))

  const STATUS_COLOR: Record<string,string> = { covered: GREEN, shortfall: RED, tight: GOLD }
  const yearsBelowTarget = data.years.filter(r => r.coverage_ratio < 1).length

  return (
    <div>
      {data.warnings.map((w,i) => (
        <div key={i} style={{ color: GOLD, fontSize: 12, marginBottom: 10, background: `${GOLD}11`,
                               borderRadius: 6, padding: '8px 12px' }}>⚠ {w}</div>
      ))}

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:16 }}>
        <KPI label="Avg coverage ratio" value={`${(data.avg_coverage_ratio*100).toFixed(0)}%`}
             accent={data.avg_coverage_ratio>=1 ? GREEN : data.avg_coverage_ratio>=0.8 ? GOLD : RED} />
        <KPI label="Years below target" value={String(yearsBelowTarget)}
             sub="< 100% coverage" accent={yearsBelowTarget===0 ? GREEN : RED} />
        <KPI label="Total shortfall" value={data.total_shortfall>0 ? fmt(data.total_shortfall) : '£0'}
             accent={data.total_shortfall>0 ? RED : GREEN} />
        <KPI label="Total surplus" value={fmt(data.total_surplus)} accent={GREEN} />
      </div>

      <Card title="Income vs Expenses by Year (£/yr)">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} barGap={2}>
            <XAxis dataKey="year" tick={{fill:'#8b949e',fontSize:9}} />
            <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
            <Tooltip formatter={(v:number,n:string)=>[`£${v.toLocaleString()}`,n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{fontSize:11,color:'#8fa3b8'}} />
            <Bar dataKey="Income"   fill={TEAL} radius={[2,2,0,0]} />
            <Bar dataKey="Expenses" fill={GOLD} radius={[2,2,0,0]} opacity={0.8} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Surplus / Shortfall by Year">
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={chartData}>
            <XAxis dataKey="year" tick={{fill:'#8b949e',fontSize:9}} />
            <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
            <Tooltip formatter={(v:number)=>[`£${v.toLocaleString()}`, v>=0?'Surplus':'Shortfall']} contentStyle={tipStyle} />
            <ReferenceLine y={0} stroke="#30363d" />
            <Bar dataKey="Surplus"   fill={GREEN} radius={[2,2,0,0]} />
            <Bar dataKey="Shortfall" fill={RED}   radius={[0,0,2,2]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Year-by-year detail">
        <div style={{ overflowX:'auto', maxHeight:300, overflowY:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
            <thead style={{ position:'sticky', top:0, background:'#162236' }}>
              <tr style={{ color:'#8b949e' }}>
                {['Year','Income','Expenses','Coverage','Surplus/Shortfall','Months Funded','Status'].map(h=>(
                  <th key={h} style={{ padding:'6px 8px', fontWeight:500,
                                       borderBottom:'1px solid #1d2f47', textAlign:'right',
                                       whiteSpace:'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.years.map(r=>(
                <tr key={r.year} style={{ borderBottom:'1px solid #0f1b2d' }}>
                  <td style={{ padding:'5px 8px', textAlign:'right', color:TEAL, fontFamily:'DM Mono, monospace' }}>{r.year}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#e8edf2' }}>{fmt(r.total_income)}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#e8edf2' }}>{fmt(r.total_expenses)}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace',
                               color: r.coverage_ratio>=1?GREEN:r.coverage_ratio>=0.8?GOLD:RED }}>
                    {(r.coverage_ratio*100).toFixed(0)}%
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace',
                               color: r.surplus_deficit>=0?GREEN:RED }}>
                    {r.surplus_deficit>=0?'+':''}{fmt(r.surplus_deficit)}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#8fa3b8' }}>
                    {r.months_funded.toFixed(1)}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right' }}>
                    <span style={{ background:`${STATUS_COLOR[r.status]??'#8b949e'}22`,
                                   color:STATUS_COLOR[r.status]??'#8b949e',
                                   border:`1px solid ${STATUS_COLOR[r.status]??'#8b949e'}44`,
                                   borderRadius:3, padding:'1px 6px', fontSize:9, fontWeight:600 }}>
                      {r.status.toUpperCase()}
                    </span>
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

// ── Tab 2: Drawdown Strategy ───────────────────────────────────────────────────
// Backend compares exactly TWO named strategies (A vs B), not an N-strategy
// array — matches DrawdownOrderResultOut in retirement.py.

interface DrawdownYearRow { year: number; income_needed: number
                             strategy_a_tax: number; strategy_b_tax: number; tax_saving: number }
interface DrawdownData { strategy_a_id: string; strategy_a_label: string
                          strategy_b_id: string; strategy_b_label: string
                          year_rows: DrawdownYearRow[]
                          lifetime_tax_a: number; lifetime_tax_b: number; lifetime_tax_saving: number
                          recommended_strategy: string; recommendation_notes: string; warnings: string[] }

function DrawdownTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<DrawdownData>({
    queryKey: ['drawdown-order', path],
    queryFn: () => apiClient.get(`/retirement/drawdown-order?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Optimising drawdown strategy…" />
  if (isError || !data) return <Err msg="Failed to load drawdown analysis. Ensure pension and ISA accounts are configured." />

  const chartData = data.year_rows.map(r => ({
    year: r.year,
    [data.strategy_a_label]: Math.round(r.strategy_a_tax),
    [data.strategy_b_label]: Math.round(r.strategy_b_tax),
  }))

  const recommendedIsA = data.recommended_strategy === data.strategy_a_id
  const recommendedLabel = recommendedIsA ? data.strategy_a_label : data.strategy_b_label

  return (
    <div>
      <div style={{ background:`${GREEN}11`, border:`1px solid ${GREEN}44`, borderRadius:10,
                    padding:'14px 18px', marginBottom:16, display:'flex', alignItems:'center', gap:16 }}>
        <div>
          <div style={{ color:GREEN, fontWeight:700, fontSize:14 }}>
            ✓ Recommended: {recommendedLabel} Strategy
          </div>
          <div style={{ color:'#8fa3b8', fontSize:12, marginTop:4 }}>
            Saves <span style={{ color:GREEN, fontFamily:'DM Mono, monospace', fontWeight:700 }}>
              {fmt(data.lifetime_tax_saving)}
            </span> in lifetime income tax vs the other strategy.
          </div>
        </div>
        {data.recommendation_notes && (
          <div style={{ color:'#8fa3b8', fontSize:11, marginLeft:'auto', maxWidth:280, lineHeight:1.5 }}>
            {data.recommendation_notes}
          </div>
        )}
      </div>

      <Card title="Cumulative income tax by strategy, year by year">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData}>
            <XAxis dataKey="year" tick={{fill:'#8b949e',fontSize:9}} />
            <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
            <Tooltip formatter={(v:number)=>[`£${v.toLocaleString()}`,'Tax']} contentStyle={tipStyle} />
            <Legend wrapperStyle={{fontSize:11,color:'#8fa3b8'}} />
            <Bar dataKey={data.strategy_a_label} fill={recommendedIsA?GREEN:TEAL} radius={[2,2,0,0]} />
            <Bar dataKey={data.strategy_b_label} fill={recommendedIsA?TEAL:GREEN} radius={[2,2,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(2,1fr)', gap:12, marginTop:14 }}>
        {[
          { id: data.strategy_a_id, label: data.strategy_a_label, tax: data.lifetime_tax_a },
          { id: data.strategy_b_id, label: data.strategy_b_label, tax: data.lifetime_tax_b },
        ].map(s => {
          const isRecommended = s.id === data.recommended_strategy
          const col = isRecommended ? GREEN : TEAL
          return (
            <div key={s.id} style={{ background:`${col}0d`, border:`1px solid ${col}${isRecommended?'88':'33'}`,
                                      borderRadius:10, padding:'14px 16px' }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ color:col, fontWeight:700, fontSize:12 }}>{s.label}</div>
                {isRecommended && (
                  <span style={{ background:`${GREEN}22`, color:GREEN, border:`1px solid ${GREEN}44`,
                                  borderRadius:3, padding:'1px 7px', fontSize:9, fontWeight:700 }}>BEST</span>
                )}
              </div>
              <div style={{ color:'#8b949e', fontSize:11 }}>Lifetime income tax</div>
              <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>
                {fmt(s.tax)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tab 3: Annuity vs Drawdown ─────────────────────────────────────────────────
// Backend returns exactly three named annuity options (level, inflation-linked,
// joint life) per pension, not an arbitrary array — matches
// AnnuityVsDrawdownOut in retirement.py. income_at_ages values are
// CUMULATIVE totals by age, not the annual amount at that age.

interface DrawdownProjection { swr: number; fund_at_start: number; income_yr1: number
                                income_at_ages: Record<string, number>; exhaustion_age: number|null }
interface AnnuityOption { annuity_type: string; label: string; fund_at_conversion: number
                           annual_income_yr1: number; inflation_rate: number; survivor_fraction: number
                           guarantee_years: number; income_at_ages: Record<string, number>
                           break_even_age: number|null }
interface AnnuityItem { pension_id: string; conversion_age: number; fund_value: number
                         drawdown: DrawdownProjection
                         annuity_level: AnnuityOption; annuity_inflation: AnnuityOption; annuity_joint: AnnuityOption
                         notes: string }

function AnnuityTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<AnnuityItem[]>({
    queryKey: ['annuity', path],
    queryFn: () => apiClient.get(`/retirement/annuity?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Computing annuity comparison…" />
  if (isError || !data || data.length===0) return <Err msg="No pension funds found. Configure a SIPP or workplace pension first." />

  return (
    <div>
      {data.map(item => {
        const options = [item.annuity_level, item.annuity_inflation, item.annuity_joint]
        return (
          <div key={item.pension_id} style={{ marginBottom: 24 }}>
            <div style={{ color:'#8fa3b8', fontSize:11, marginBottom:10 }}>
              {item.pension_id.replace(/_/g,' ')} — Fund at conversion (age {item.conversion_age}):{' '}
              <span style={{ color:GOLD, fontFamily:'DM Mono, monospace', fontWeight:700 }}>{fmt(item.fund_value)}</span>
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:14 }}>
              <KPI label="Drawdown income (4% SWR), yr 1" value={fmt(item.drawdown.income_yr1)+'/yr'} accent={TEAL} />
              <KPI label="Fund at start" value={fmt(item.drawdown.fund_at_start)} accent={TEAL} />
              <KPI label="Fund exhaustion age" value={item.drawdown.exhaustion_age ? String(item.drawdown.exhaustion_age) : 'Never'} accent={TEAL} />
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:16 }}>
              {options.map(opt => {
                const col = opt.annuity_type==='level' ? GOLD : opt.annuity_type==='inflation_linked' ? GREEN : PURP
                const betterThan4pct = opt.annual_income_yr1 > item.drawdown.income_yr1
                return (
                  <div key={opt.annuity_type} style={{ background:`${col}0d`, border:`1px solid ${col}44`,
                                                        borderRadius:10, padding:'14px 16px' }}>
                    <div style={{ color:col, fontWeight:700, fontSize:12, marginBottom:10 }}>{opt.label}</div>
                    <div style={{ fontSize:11, display:'flex', flexDirection:'column', gap:6 }}>
                      <div>
                        <div style={{ color:'#8b949e' }}>Annual income, yr 1</div>
                        <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:15 }}>
                          {fmt(opt.annual_income_yr1)}/yr
                          <span style={{ color:betterThan4pct?GREEN:RED, fontSize:9, marginLeft:6 }}>
                            {betterThan4pct?'▲ beats SWR':'▼ below SWR'}
                          </span>
                        </div>
                      </div>
                      <div>
                        <div style={{ color:'#8b949e' }}>Break-even age</div>
                        <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace' }}>
                          {opt.break_even_age ?? '—'}
                        </div>
                      </div>
                      {opt.survivor_fraction > 0 && (
                        <div>
                          <div style={{ color:'#8b949e' }}>Survivor benefit</div>
                          <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace' }}>
                            {(opt.survivor_fraction*100).toFixed(0)}%
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            <Card accent="#30363d">
              <p style={{ color:'#8fa3b8', fontSize:12, lineHeight:1.6, margin:0 }}>{item.notes}</p>
              <p style={{ color:'#8fa3b8', fontSize:11, lineHeight:1.6, margin:'10px 0 0' }}>
                <strong style={{ color:'#8fa3b8' }}>Annuity vs Drawdown:</strong> An annuity trades your pension pot for a guaranteed income for life.
                Drawdown keeps the pot invested (4% SWR shown) but runs the risk of exhaustion.
                The break-even age is when cumulative annuity income exceeds the pension pot you gave up.
              </p>
            </Card>
          </div>
        )
      })}
    </div>
  )
}

// ── Tab 4: State Pension ───────────────────────────────────────────────────────
// Matches StatePensionProjectionOut in retirement.py — NI top-up and
// deferral are two separate option lists, not a single per-year series.

interface NiTopUpOption { tax_year: string; cost_gbp: number; weekly_pension_gain: number
                           annual_pension_gain: number; years_to_recoup: number; roi_10yr_pct: number }
interface DeferralOption { claim_age: number; weeks_deferred: number; annual_bonus_pct: number
                            weekly_pension_with_bonus: number; annual_pension_with_bonus: number
                            break_even_years: number }
interface SPPerson { person_id: string; person_name: string; current_ni_years: number
                      ni_years_needed: number; gap_years: number; projected_start_year: number
                      full_weekly_amount: number; projected_weekly: number; projected_annual: number
                      triple_lock_at_ages: Record<string, number>
                      top_up_options: NiTopUpOption[]; deferral_options: DeferralOption[]
                      total_top_up_cost: number; max_pension_if_filled: number; warnings: string[] }

function StatePensionTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<SPPerson[]>({
    queryKey: ['state-pension', path],
    queryFn: () => apiClient.get(`/retirement/state-pension?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Analysing state pension…" />
  if (isError || !data || data.length===0) return <Err msg="No state pension data found. Configure people with state_pension in the scenario." />

  return (
    <div>
      {data.map(p => {
        const tripleLockChart = Object.entries(p.triple_lock_at_ages).map(([age, amount]) => ({ age: Number(age), amount }))
        return (
          <div key={p.person_id} style={{ marginBottom:24 }}>
            <div style={{ color:'#e8edf2', fontWeight:600, fontSize:14, marginBottom:12 }}>{p.person_name}</div>

            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:14 }}>
              <KPI label="NI qualifying years"
                   value={`${p.current_ni_years}/${p.ni_years_needed}`}
                   accent={p.gap_years===0 ? GREEN : p.gap_years<=5 ? GOLD : RED} />
              <KPI label="Projected weekly pension" value={`£${p.projected_weekly.toFixed(2)}`} accent={TEAL} />
              <KPI label="Projected annual pension" value={fmt(p.projected_annual)} accent={TEAL} />
              <KPI label="Starts" value={String(p.projected_start_year)} accent={GOLD} />
            </div>

            {p.gap_years > 0 && (
              <Card title="NI gap top-up options" accent={ORNG}>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12, marginBottom:10 }}>
                  <div>
                    <div style={{ color:'#8b949e', fontSize:10 }}>Gap years</div>
                    <div style={{ color:ORNG, fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>{p.gap_years}</div>
                  </div>
                  <div>
                    <div style={{ color:'#8b949e', fontSize:10 }}>Total top-up cost</div>
                    <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>
                      {fmt(p.total_top_up_cost)}
                    </div>
                  </div>
                  <div>
                    <div style={{ color:'#8b949e', fontSize:10 }}>Max pension if all filled</div>
                    <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>
                      {fmt(p.max_pension_if_filled)}
                    </div>
                  </div>
                </div>
                {p.top_up_options.length > 0 && (
                  <div style={{ overflowX:'auto', maxHeight:160, overflowY:'auto', marginBottom:10 }}>
                    <table style={{ width:'100%', borderCollapse:'collapse', fontSize:10 }}>
                      <thead style={{ position:'sticky', top:0, background:'#162236' }}>
                        <tr style={{ color:'#8b949e' }}>
                          {['Tax Year','Cost','Weekly Gain','Years to Recoup','10yr ROI'].map(h=>(
                            <th key={h} style={{ padding:'4px 6px', fontWeight:500, borderBottom:'1px solid #1d2f47', textAlign:'right' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {p.top_up_options.map(o => (
                          <tr key={o.tax_year} style={{ borderBottom:'1px solid #0f1b2d' }}>
                            <td style={{ padding:'4px 6px', textAlign:'right', color:TEAL }}>{o.tax_year}</td>
                            <td style={{ padding:'4px 6px', textAlign:'right', color:'#e8edf2', fontFamily:'DM Mono, monospace' }}>{fmt(o.cost_gbp)}</td>
                            <td style={{ padding:'4px 6px', textAlign:'right', color:'#e8edf2', fontFamily:'DM Mono, monospace' }}>£{o.weekly_pension_gain.toFixed(2)}</td>
                            <td style={{ padding:'4px 6px', textAlign:'right', color:'#8fa3b8' }}>{o.years_to_recoup.toFixed(1)}</td>
                            <td style={{ padding:'4px 6px', textAlign:'right', color:GREEN, fontWeight:600 }}>{o.roi_10yr_pct.toFixed(0)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p style={{ color:'#8fa3b8', fontSize:11, lineHeight:1.5, margin:0 }}>
                  HMRC allows topping up NI gaps within the last 6 completed tax years.
                  Check <strong style={{ color:TEAL }}>gov.uk/check-state-pension</strong> for your exact gaps.
                </p>
              </Card>
            )}

            {p.deferral_options.length > 0 && (
              <Card title="Deferral options">
                <div style={{ display:'grid', gridTemplateColumns:`repeat(${p.deferral_options.length},1fr)`, gap:10 }}>
                  {p.deferral_options.map(d => (
                    <div key={d.claim_age}>
                      <div style={{ color:'#8b949e', fontSize:10 }}>Claim at {d.claim_age}</div>
                      <div style={{ color:GOLD, fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:14 }}>
                        +{d.annual_bonus_pct.toFixed(1)}%
                      </div>
                      <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:11 }}>
                        {fmt(d.annual_pension_with_bonus)}/yr
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {tripleLockChart.length > 0 && (
              <Card title="Triple-lock projected annual pension by age">
                <ResponsiveContainer width="100%" height={160}>
                  <AreaChart data={tripleLockChart}>
                    <XAxis dataKey="age" tick={{fill:'#8b949e',fontSize:9}} />
                    <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
                    <Tooltip formatter={(v:number)=>[fmt(v),'Annual pension']} contentStyle={tipStyle} />
                    <Area dataKey="amount" stroke={TEAL} fill={TEAL+'20'} strokeWidth={2} dot={false}
                          name="Projected annual pension" />
                  </AreaChart>
                </ResponsiveContainer>
              </Card>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type Tab = 'coverage' | 'drawdown' | 'annuity' | 'pension'

const TABS: { key: Tab; label: string }[] = [
  { key: 'coverage',  label: 'Income Coverage' },
  { key: 'drawdown',  label: 'Drawdown Strategy' },
  { key: 'annuity',   label: 'Annuity vs Drawdown' },
  { key: 'pension',   label: 'State Pension' },
]

export function RetirementPlanner() {
  const [tab, setTab]   = useState<Tab>('coverage')
  const { timeline }    = useSimulationStore()
  const { activeScenarioPath } = useConfigStore()

  const fireYear  = timeline?.fire_year
  // True "as of today" net worth — raw balances, no simulated growth.
  // Deliberately not timeline.years[0]: see backend networth.py.
  const { data: currentNetWorth } = useQuery<{ total_net_worth: number }>({
    queryKey: ['networth-current', activeScenarioPath],
    queryFn: () => apiClient.get('/networth/current', { params: { scenario_path: activeScenarioPath } }).then(r => r.data),
    staleTime: 30_000,
  })
  const latestNW = currentNetWorth?.total_net_worth

  return (
    <div>
      <PageHeader title="Retirement Planner" subtitle="Income coverage · drawdown strategy · state pension" />

      {/* Quick KPIs */}
      {(fireYear || latestNW) && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:20 }}>
          {fireYear && <KPI label="FIRE year" value={String(fireYear)}
                            sub={`${fireYear - new Date().getFullYear()} years away`} accent={GOLD} />}
          {latestNW && <KPI label="Current net worth" value={fmt(latestNW)} accent={TEAL} />}
          <KPI label="Safe withdrawal rate" value="4.0%" sub="classic SWR assumption" accent={GREEN} />
        </div>
      )}

      {/* Tabs */}
      <div style={{ display:'flex', gap:2, background:'#162236', borderRadius:8, padding:4, marginBottom:20 }}>
        {TABS.map(t=>(
          <button key={t.key} onClick={()=>setTab(t.key)} style={{
            flex:1, padding:'8px 4px', borderRadius:6, border:'none', cursor:'pointer',
            fontSize:12, fontWeight:tab===t.key?600:400,
            background: tab===t.key?TEAL:'transparent',
            color: tab===t.key?'#fff':'#8fa3b8',
          }}>{t.label}</button>
        ))}
      </div>

      {tab==='coverage' && <IncomeCoverageTab path={activeScenarioPath} />}
      {tab==='drawdown' && <DrawdownTab       path={activeScenarioPath} />}
      {tab==='annuity'  && <AnnuityTab        path={activeScenarioPath} />}
      {tab==='pension'  && <StatePensionTab   path={activeScenarioPath} />}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
