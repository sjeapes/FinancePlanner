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

interface CovRow {
  year: number; age: number; total_income: number; total_expenses: number
  coverage_ratio: number; surplus_shortfall: number; status: string
  pension_drawdown: number; state_pension: number; rental_income: number
}
interface CovData { rows: CovRow[]; avg_coverage: number; years_below_target: number
                    total_shortfall: number; total_surplus: number }

function IncomeCoverageTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<CovData>({
    queryKey: ['income-coverage', path],
    queryFn: () => apiClient.get(`/retirement/income-coverage?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Analysing income coverage…" />
  if (isError || !data) return <Err msg="Failed to load income coverage. Run a simulation first." />

  const chartData = data.rows.filter(r=>r.year % 2===0).map(r => ({
    age: r.age,
    Income: Math.round(r.total_income),
    Expenses: Math.round(r.total_expenses),
    Surplus: Math.max(0, r.surplus_shortfall),
    Shortfall: Math.min(0, r.surplus_shortfall),
  }))

  const STATUS_COLOR: Record<string,string> = { green: GREEN, amber: GOLD, red: RED }

  return (
    <div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:16 }}>
        <KPI label="Avg coverage ratio" value={`${(data.avg_coverage*100).toFixed(0)}%`}
             accent={data.avg_coverage>=1 ? GREEN : data.avg_coverage>=0.8 ? GOLD : RED} />
        <KPI label="Years below target" value={String(data.years_below_target)}
             sub="< 100% coverage" accent={data.years_below_target===0 ? GREEN : RED} />
        <KPI label="Total shortfall" value={data.total_shortfall>0 ? fmt(data.total_shortfall) : '£0'}
             accent={data.total_shortfall>0 ? RED : GREEN} />
        <KPI label="Total surplus" value={fmt(data.total_surplus)} accent={GREEN} />
      </div>

      <Card title="Income vs Expenses by Age (£/yr)">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} barGap={2}>
            <XAxis dataKey="age" tick={{fill:'#8b949e',fontSize:9}} />
            <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
            <Tooltip formatter={(v:number,n:string)=>[`£${v.toLocaleString()}`,n]} contentStyle={tipStyle} />
            <Legend wrapperStyle={{fontSize:11,color:'#8fa3b8'}} />
            <Bar dataKey="Income"   fill={TEAL} radius={[2,2,0,0]} />
            <Bar dataKey="Expenses" fill={GOLD} radius={[2,2,0,0]} opacity={0.8} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Surplus / Shortfall by Age">
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={chartData}>
            <XAxis dataKey="age" tick={{fill:'#8b949e',fontSize:9}} />
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
                {['Year','Age','Income','Expenses','Coverage','Surplus/Shortfall','Status'].map(h=>(
                  <th key={h} style={{ padding:'6px 8px', fontWeight:500,
                                       borderBottom:'1px solid #1d2f47', textAlign:'right',
                                       whiteSpace:'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map(r=>(
                <tr key={r.year} style={{ borderBottom:'1px solid #0f1b2d' }}>
                  <td style={{ padding:'5px 8px', textAlign:'right', color:TEAL, fontFamily:'DM Mono, monospace' }}>{r.year}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', color:'#8fa3b8' }}>{r.age}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#e8edf2' }}>{fmt(r.total_income)}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#e8edf2' }}>{fmt(r.total_expenses)}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace',
                               color: r.coverage_ratio>=1?GREEN:r.coverage_ratio>=0.8?GOLD:RED }}>
                    {(r.coverage_ratio*100).toFixed(0)}%
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right', fontFamily:'DM Mono, monospace',
                               color: r.surplus_shortfall>=0?GREEN:RED }}>
                    {r.surplus_shortfall>=0?'+':''}{fmt(r.surplus_shortfall)}
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

interface StrategyRow { strategy: string; total_tax: number; pot_at_death: number
                        isa_exhausted_year: number|null; recommendation: string }
interface DrawdownData { strategies: StrategyRow[]; recommended_strategy: string
                         lifetime_tax_saving: number; notes: string }

function DrawdownTab({ path }: { path: string }) {
  const { data, isLoading, isError } = useQuery<DrawdownData>({
    queryKey: ['drawdown-order', path],
    queryFn: () => apiClient.get(`/retirement/drawdown-order?scenario_path=${encodeURIComponent(path)}`).then(r=>r.data),
    staleTime: 120_000,
  })

  if (isLoading) return <Loading text="Optimising drawdown strategy…" />
  if (isError || !data) return <Err msg="Failed to load drawdown analysis. Ensure pension and ISA accounts are configured." />

  const chartData = data.strategies.map(s => ({
    name: s.strategy.replace('_first','').replace('_',' ').replace(/\b\w/g,l=>l.toUpperCase()),
    'Lifetime tax': Math.round(s.total_tax),
    'Pot at death': Math.round(s.pot_at_death),
    strategy: s.strategy,
  }))

  const bestTax   = Math.min(...data.strategies.map(s=>s.total_tax))
  const worstTax  = Math.max(...data.strategies.map(s=>s.total_tax))

  const STRATEGY_COLORS: Record<string,string> = {
    isa_first:'#0e9aad', sipp_first:'#d4a843', gia_first:'#a78bfa', optimised:'#2dbd7e'
  }

  return (
    <div>
      {/* Recommended strategy banner */}
      <div style={{ background:`${GREEN}11`, border:`1px solid ${GREEN}44`, borderRadius:10,
                    padding:'14px 18px', marginBottom:16, display:'flex', alignItems:'center', gap:16 }}>
        <div>
          <div style={{ color:GREEN, fontWeight:700, fontSize:14 }}>
            ✓ Recommended: {data.recommended_strategy.replace('_first','').replace('_',' ')
              .replace(/\b\w/g,l=>l.toUpperCase())} Strategy
          </div>
          <div style={{ color:'#8fa3b8', fontSize:12, marginTop:4 }}>
            Saves <span style={{ color:GREEN, fontFamily:'DM Mono, monospace', fontWeight:700 }}>
              {fmt(data.lifetime_tax_saving)}
            </span> in lifetime income tax vs the worst strategy.
          </div>
        </div>
        {data.notes && (
          <div style={{ color:'#8fa3b8', fontSize:11, marginLeft:'auto', maxWidth:220, lineHeight:1.5 }}>
            {data.notes}
          </div>
        )}
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>
        <Card title="Lifetime income tax by strategy">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} layout="vertical">
              <XAxis type="number" tickFormatter={v=>`£${(v/1000).toFixed(0)}k`}
                     tick={{fill:'#8b949e',fontSize:9}} />
              <YAxis type="category" dataKey="name" tick={{fill:'#8fa3b8',fontSize:10}} width={80} />
              <Tooltip formatter={(v:number)=>[fmt(v),'Tax']} contentStyle={tipStyle} />
              <Bar dataKey="Lifetime tax" radius={[0,4,4,0]}>
                {chartData.map((d,i)=>(
                  <Cell key={i} fill={STRATEGY_COLORS[d.strategy]??TEAL} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Pot remaining at death">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} layout="vertical">
              <XAxis type="number" tickFormatter={v=>`£${(v/1000).toFixed(0)}k`}
                     tick={{fill:'#8b949e',fontSize:9}} />
              <YAxis type="category" dataKey="name" tick={{fill:'#8fa3b8',fontSize:10}} width={80} />
              <Tooltip formatter={(v:number)=>[fmt(v),'Pot']} contentStyle={tipStyle} />
              <Bar dataKey="Pot at death" radius={[0,4,4,0]}>
                {chartData.map((d,i)=>(
                  <Cell key={i} fill={STRATEGY_COLORS[d.strategy]??TEAL} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Strategy detail cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(2,1fr)', gap:12 }}>
        {data.strategies.map(s => {
          const col = STRATEGY_COLORS[s.strategy] ?? TEAL
          const isRecommended = s.strategy === data.recommended_strategy
          return (
            <div key={s.strategy} style={{ background:`${col}0d`, border:`1px solid ${col}${isRecommended?'88':'33'}`,
                                            borderRadius:10, padding:'14px 16px' }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ color:col, fontWeight:700, fontSize:12 }}>
                  {s.strategy.replace('_first','').replace('_',' ').replace(/\b\w/g,l=>l.toUpperCase())}
                </div>
                {isRecommended && (
                  <span style={{ background:`${GREEN}22`, color:GREEN, border:`1px solid ${GREEN}44`,
                                  borderRadius:3, padding:'1px 7px', fontSize:9, fontWeight:700 }}>BEST</span>
                )}
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, fontSize:11 }}>
                <div>
                  <div style={{ color:'#8b949e' }}>Lifetime tax</div>
                  <div style={{ color:s.total_tax===bestTax?GREEN:s.total_tax===worstTax?RED:'#e8edf2',
                                 fontFamily:'DM Mono, monospace', fontWeight:700 }}>{fmt(s.total_tax)}</div>
                </div>
                <div>
                  <div style={{ color:'#8b949e' }}>Pot at death</div>
                  <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace' }}>{fmt(s.pot_at_death)}</div>
                </div>
              </div>
              {s.recommendation && (
                <div style={{ color:'#8fa3b8', fontSize:10, marginTop:8, lineHeight:1.5 }}>{s.recommendation}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tab 3: Annuity vs Drawdown ─────────────────────────────────────────────────

interface AnnuityOpt { label: string; type: string; annual_income: number
                       break_even_age: number|null; income_at_80: number; income_at_90: number }
interface AnnuityItem { person_name: string; pension_pot: number
                        annuity_options: AnnuityOpt[]; drawdown_income: number
                        drawdown_pot_at_80: number; drawdown_pot_at_90: number }

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
      {data.map(item => (
        <div key={item.person_name}>
          <div style={{ color:'#8fa3b8', fontSize:11, marginBottom:10 }}>
            {item.person_name} — Pension pot: <span style={{ color:GOLD, fontFamily:'DM Mono, monospace', fontWeight:700 }}>{fmt(item.pension_pot)}</span>
          </div>

          {/* Drawdown baseline */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:14 }}>
            <KPI label="Drawdown income (4% SWR)" value={fmt(item.drawdown_income)+'/yr'} accent={TEAL} />
            <KPI label="Pot remaining at 80"       value={fmt(item.drawdown_pot_at_80)}   accent={TEAL} />
            <KPI label="Pot remaining at 90"       value={fmt(item.drawdown_pot_at_90)}   accent={TEAL} />
          </div>

          {/* Annuity options */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:16 }}>
            {item.annuity_options.map(opt => {
              const col = opt.type==='level'?GOLD : opt.type==='inflation_linked'?GREEN : PURP
              const betterThan4pct = opt.annual_income > item.drawdown_income
              return (
                <div key={opt.type} style={{ background:`${col}0d`, border:`1px solid ${col}44`,
                                              borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ color:col, fontWeight:700, fontSize:12, marginBottom:10 }}>{opt.label}</div>
                  <div style={{ fontSize:11, display:'flex', flexDirection:'column', gap:6 }}>
                    <div>
                      <div style={{ color:'#8b949e' }}>Annual income</div>
                      <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:15 }}>
                        {fmt(opt.annual_income)}/yr
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
                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                      <div>
                        <div style={{ color:'#8b949e', fontSize:9 }}>Income at 80</div>
                        <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:11 }}>
                          {fmt(opt.income_at_80)}
                        </div>
                      </div>
                      <div>
                        <div style={{ color:'#8b949e', fontSize:9 }}>Income at 90</div>
                        <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:11 }}>
                          {fmt(opt.income_at_90)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <Card accent="#30363d">
            <p style={{ color:'#8fa3b8', fontSize:12, lineHeight:1.6, margin:0 }}>
              <strong style={{ color:'#8fa3b8' }}>Annuity vs Drawdown:</strong> An annuity trades your pension pot for a guaranteed income for life.
              Drawdown keeps the pot invested (4% SWR shown) but runs the risk of exhaustion.
              The break-even age is when cumulative annuity income exceeds the pension pot you gave up.
              Check the Tax Optimiser → UFPLS vs PCLS tab for crystallisation strategy before choosing.
            </p>
          </Card>
        </div>
      ))}
    </div>
  )
}

// ── Tab 4: State Pension ───────────────────────────────────────────────────────

interface SPYear { year: number; qualifying_years: number; cumulative_pension: number
                   gap_cost_to_fill: number; roi_pct: number }
interface SPPerson { person_name: string; current_qualifying_years: number
                     full_qualifying_years: number; shortfall: number
                     weekly_pension: number; annual_pension: number
                     state_pension_start_year: number; deferral_bonus_per_year: number
                     class3_cost_total: number; class3_roi_pct: number
                     years: SPYear[] }

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
      {data.map(p => (
        <div key={p.person_name} style={{ marginBottom:24 }}>
          <div style={{ color:'#e8edf2', fontWeight:600, fontSize:14, marginBottom:12 }}>{p.person_name}</div>

          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:14 }}>
            <KPI label="NI qualifying years"
                 value={`${p.current_qualifying_years}/${p.full_qualifying_years}`}
                 accent={p.shortfall===0 ? GREEN : p.shortfall<=5 ? GOLD : RED} />
            <KPI label="Weekly state pension" value={`£${p.weekly_pension.toFixed(2)}`}
                 accent={TEAL} />
            <KPI label="Annual state pension" value={fmt(p.annual_pension)} accent={TEAL} />
            <KPI label="Starts" value={String(p.state_pension_start_year)} accent={GOLD} />
          </div>

          {p.shortfall > 0 && (
            <Card title="NI gap top-up analysis" accent={ORNG}>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12, marginBottom:10 }}>
                <div>
                  <div style={{ color:'#8b949e', fontSize:10 }}>Years to top up</div>
                  <div style={{ color:ORNG, fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>{p.shortfall}</div>
                </div>
                <div>
                  <div style={{ color:'#8b949e', fontSize:10 }}>Total Class 3 cost</div>
                  <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>
                    {fmt(p.class3_cost_total)}
                  </div>
                </div>
                <div>
                  <div style={{ color:'#8b949e', fontSize:10 }}>ROI (lifetime)</div>
                  <div style={{ color:p.class3_roi_pct>200?GREEN:GOLD,
                                fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:16 }}>
                    {p.class3_roi_pct.toFixed(0)}%
                  </div>
                </div>
              </div>
              <p style={{ color:'#8fa3b8', fontSize:11, lineHeight:1.5, margin:0 }}>
                HMRC allows topping up NI gaps within the last 6 completed tax years.
                Class 3 NI costs £{(17.45*52).toFixed(0)}/yr per qualifying year (2024/25).
                Check <strong style={{ color:TEAL }}>gov.uk/check-state-pension</strong> for your exact gaps.
              </p>
            </Card>
          )}

          {/* Projection chart */}
          {p.years.length > 0 && (
            <Card title="State pension accumulation">
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={p.years.filter(y=>y.year%2===0)}>
                  <XAxis dataKey="year" tick={{fill:'#8b949e',fontSize:9}} />
                  <YAxis tickFormatter={v=>`£${v.toLocaleString()}`} tick={{fill:'#8b949e',fontSize:9}} />
                  <Tooltip formatter={(v:number,n:string)=>[`£${v.toLocaleString()}`,n]} contentStyle={tipStyle} />
                  <Area dataKey="cumulative_pension" stroke={TEAL} fill={TEAL+'20'} strokeWidth={2} dot={false}
                        name="Cumulative pension income" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          )}
        </div>
      ))}
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
  const latestNW  = timeline?.years.at(-1)?.total_net_worth

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
