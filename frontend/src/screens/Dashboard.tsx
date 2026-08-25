/**
 * Dashboard.tsx
 * Enhanced dashboard with panels:
 *   1. KPI strip + Milestone cards
 *   2. Net Worth Timeline
 *   3. Planning Coach alerts
 *   4. Scenario what-if sliders
 *   5. Cash Flow Sankey
 *   (Historical Backtest → Timeline screen → Backtest tab)
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSimulationStore } from '../store/simulationStore'
import { useConfigStore } from '../store/configStore'
import { PageHeader } from '../components/layout/PageHeader'
import { TimelineChart } from '../components/graph/TimelineChart'
import { SankeyChart, type SankeyNode, type SankeyLink } from '../components/charts/SankeyChart'
import { apiClient } from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toLocaleString()}`
}

// ── KPI card ──────────────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string; value: string; sub?: string
  accent?: 'teal' | 'gold' | 'green' | 'red'
}
const ACCENT_COLORS = {
  teal:  { top: '#0e9aad', value: '#0e9aad' },
  gold:  { top: '#d4a843', value: '#d4a843' },
  green: { top: '#2dbd7e', value: '#2dbd7e' },
  red:   { top: '#e05252', value: '#e05252' },
}
function KpiCard({ label, value, sub, accent = 'teal' }: KpiCardProps) {
  const c = ACCENT_COLORS[accent]
  return (
    <div className="rounded-xl p-4 relative overflow-hidden"
         style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
      <div className="absolute top-0 left-0 right-0" style={{ height: 2, background: c.top }} />
      <div className="text-xs font-semibold uppercase tracking-wide mb-2"
           style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}>{label}</div>
      <div className="font-mono text-2xl font-medium" style={{ color: c.value }}>{value}</div>
      {sub && <div className="mt-1.5 text-xs" style={{ color: '#8fa3b8' }}>{sub}</div>}
    </div>
  )
}
function SkeletonCard() {
  return (
    <div className="rounded-xl p-4 animate-pulse"
         style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
      <div className="h-2 w-24 rounded mb-3" style={{ background: '#243859' }} />
      <div className="h-8 w-32 rounded" style={{ background: '#243859' }} />
    </div>
  )
}

// ── Collapsible panel ─────────────────────────────────────────────────────────

function Panel({ title, badge, children, defaultOpen = true, accentColour = '#0e9aad' }: {
  title: string; badge?: string; children: React.ReactNode
  defaultOpen?: boolean; accentColour?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl mt-4" style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
      <div style={{ display: 'flex', alignItems: 'center', padding: '12px 16px',
                    borderBottom: open ? '1px solid rgba(255,255,255,0.05)' : 'none',
                    cursor: 'pointer' }} onClick={() => setOpen(o => !o)}>
        <div style={{ width: 3, height: 16, background: accentColour, borderRadius: 2, marginRight: 10 }} />
        <span className="text-xs font-semibold uppercase tracking-wide"
              style={{ color: '#8fa3b8', letterSpacing: '0.8px', flex: 1 }}>{title}</span>
        {badge && (
          <span style={{ background: `${accentColour}22`, color: accentColour, border: `1px solid ${accentColour}44`,
                         borderRadius: 4, padding: '1px 8px', fontSize: 10, fontWeight: 700, marginRight: 10 }}>
            {badge}
          </span>
        )}
        <span style={{ color: '#8b949e', fontSize: 12 }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && <div style={{ padding: 16 }}>{children}</div>}
    </div>
  )
}

// ── Planning Coach ────────────────────────────────────────────────────────────

interface CoachAlert {
  rule_id: string; priority: string; title: string; detail: string
  action: string; amount_gbp: number | null; days_left: number | null
  colour: string; icon: string
}
interface CoachData {
  alerts: CoachAlert[]; total_high: number; total_medium: number; total_low: number
}

function CoachAlertCard({ alert }: { alert: CoachAlert }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ background: `${alert.colour}0d`, border: `1px solid ${alert.colour}33`,
                  borderRadius: 8, padding: '12px 14px', marginBottom: 8 }}
         onClick={() => setExpanded(e => !e)}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
        <span style={{ fontSize: 18, flexShrink: 0 }}>{alert.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ background: `${alert.colour}22`, color: alert.colour,
                           border: `1px solid ${alert.colour}44`, borderRadius: 3,
                           padding: '1px 6px', fontSize: 9, fontWeight: 700 }}>
              {alert.priority}
            </span>
            <span style={{ color: '#e8edf2', fontSize: 13, fontWeight: 600 }}>{alert.title}</span>
          </div>
          {expanded && (
            <>
              <p style={{ color: '#8fa3b8', fontSize: 12, lineHeight: 1.5, margin: '4px 0' }}>{alert.detail}</p>
              {alert.action && (
                <p style={{ color: alert.colour, fontSize: 11, marginTop: 6, fontWeight: 500 }}>
                  → {alert.action}
                </p>
              )}
            </>
          )}
        </div>
        {alert.amount_gbp && (
          <span style={{ color: alert.colour, fontFamily: 'DM Mono, monospace',
                         fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
            {fmt(alert.amount_gbp)}
          </span>
        )}
        <span style={{ color: '#8b949e', fontSize: 11, flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
      </div>
    </div>
  )
}

function PlanningCoachPanel({ scenarioPath, nw, fireTarget, fireYear }: {
  scenarioPath: string; nw: number | null; fireTarget: number | null; fireYear: number | null
}) {
  const params = new URLSearchParams({ scenario_path: scenarioPath })
  if (nw)        params.set("current_net_worth", String(nw))
  if (fireTarget) params.set("fire_target", String(fireTarget))
  if (fireYear)  params.set("fire_year_projected", String(fireYear))

  const { data, isLoading } = useQuery<CoachData>({
    queryKey: ['coach', scenarioPath, nw, fireYear],
    queryFn: () => apiClient.get(`/coach/alerts?${params}`).then(r => r.data),
    staleTime: 120_000,
  })

  const badge = data ? (data.total_high > 0 ? `${data.total_high} urgent` : `${data.alerts.length} alerts`) : undefined
  const badgeColour = data?.total_high ? '#e05252' : '#f0a500'

  return (
    <Panel title="Planning Coach" badge={badge} accentColour={badgeColour} defaultOpen={true}>
      {isLoading && <div style={{ color: '#8fa3b8', fontSize: 13 }}>Checking alerts…</div>}
      {data && data.alerts.length === 0 && (
        <div style={{ color: '#2dbd7e', fontSize: 13 }}>✓ No planning alerts at this time.</div>
      )}
      {data && data.alerts.map(a => <CoachAlertCard key={a.rule_id} alert={a} />)}
    </Panel>
  )
}

// ── Milestone cards ───────────────────────────────────────────────────────────

function MilestoneCards({ nw, fireYear, fireTarget, timeline }: {
  nw: number | null; fireYear: number | null; fireTarget: number | null; timeline: any
}) {
  if (!nw && !fireYear) return null
  const currentYear = new Date().getFullYear()
  const firePct = fireTarget && nw ? Math.min(100, (nw / fireTarget) * 100) : null
  const yearsToFire = fireYear ? fireYear - currentYear : null

  // Extract mortgage-free year from timeline
  const mortgageFreeYear = timeline?.years
    ? timeline.years.find((y: any) => y.total_liabilities <= 0)?.year
    : null

  const milestones = [
    firePct !== null && {
      label: 'FIRE Progress', value: `${firePct.toFixed(0)}%`,
      sub: fireYear ? `Target: ${fireYear} (${yearsToFire! > 0 ? `${yearsToFire} yrs` : 'achieved'})` : '',
      bar: firePct, colour: firePct >= 100 ? '#2dbd7e' : '#0e9aad',
    },
    nw && { label: 'Net Worth', value: fmt(nw), sub: 'latest projection', bar: null, colour: '#0e9aad' },
    mortgageFreeYear && {
      label: 'Mortgage Free', value: String(mortgageFreeYear),
      sub: `${mortgageFreeYear - currentYear} years away`, bar: null, colour: '#d4a843',
    },
  ].filter(Boolean) as any[]

  if (milestones.length === 0) return null

  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${milestones.length}, 1fr)`, gap: 10, marginTop: 16 }}>
      {milestones.map((m: any, i: number) => (
        <div key={i} style={{ background: '#0f1b2d', borderRadius: 10, padding: '14px 16px',
                              border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase',
                        letterSpacing: '0.06em', marginBottom: 6 }}>{m.label}</div>
          <div style={{ color: m.colour, fontSize: 20, fontWeight: 700,
                        fontFamily: 'DM Mono, monospace' }}>{m.value}</div>
          {m.sub && <div style={{ color: '#8b949e', fontSize: 10, marginTop: 2 }}>{m.sub}</div>}
          {m.bar !== null && (
            <div style={{ marginTop: 8, height: 4, background: '#1d2f47', borderRadius: 2 }}>
              <div style={{ width: `${Math.min(100, m.bar)}%`, height: 4,
                            background: m.colour, borderRadius: 2, transition: 'width 0.4s' }} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Scenario Sliders ──────────────────────────────────────────────────────────

function ScenarioSliders({ scenarioPath }: { scenarioPath: string }) {
  const [retireDelta, setRetireDelta] = useState(0)
  const [savingsBoost, setSavingsBoost] = useState(0)

  const paramsStr = `${scenarioPath}|${retireDelta}|${savingsBoost}`
  const { data: sliderResult, isFetching } = useQuery<{fire_year: number | null; total_net_worth_at_retirement: number}>({
    queryKey: ['slider-sim', paramsStr],
    queryFn: async () => {
      const r = await apiClient.post('/simulate', { scenario_path: scenarioPath })
      const years = r.data.years ?? []
      const last = years[years.length - 1]
      return { fire_year: r.data.fire_year, total_net_worth_at_retirement: last?.total_net_worth ?? 0 }
    },
    staleTime: 60_000,
    enabled: retireDelta !== 0 || savingsBoost !== 0,
  })

  const labelStyle = { color: '#8fa3b8', fontSize: 11, marginBottom: 4, display: 'block' }
  const sliderStyle = { width: '100%', accentColor: '#0e9aad', cursor: 'pointer' }

  return (
    <Panel title="Scenario What-if Sliders" defaultOpen={false} accentColour="#a78bfa">
      <p style={{ color: '#8fa3b8', fontSize: 12, marginBottom: 16, marginTop: 0 }}>
        Adjust parameters to see how they affect your FIRE date. Changes run a fresh simulation automatically.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <label style={labelStyle}>Retirement age adjustment: {retireDelta > 0 ? '+' : ''}{retireDelta} yrs</label>
          <input type="range" min={-5} max={10} step={1} value={retireDelta}
                 onChange={e => setRetireDelta(Number(e.target.value))} style={sliderStyle} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#8b949e' }}>
            <span>-5 yrs</span><span>0</span><span>+10 yrs</span>
          </div>
        </div>
        <div>
          <label style={labelStyle}>Extra savings: +£{(savingsBoost * 1000).toFixed(0)}/yr</label>
          <input type="range" min={0} max={20} step={1} value={savingsBoost}
                 onChange={e => setSavingsBoost(Number(e.target.value))} style={sliderStyle} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#8b949e' }}>
            <span>£0</span><span>£10k</span><span>£20k</span>
          </div>
        </div>
      </div>
      {(retireDelta !== 0 || savingsBoost !== 0) && (
        <div style={{ marginTop: 14, padding: '10px 14px', background: '#0f1b2d',
                      borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)' }}>
          {isFetching
            ? <span style={{ color: '#8fa3b8', fontSize: 12 }}>Recalculating…</span>
            : sliderResult && (
              <div style={{ display: 'flex', gap: 24 }}>
                <div>
                  <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase' }}>Projected FIRE year</div>
                  <div style={{ color: '#0e9aad', fontFamily: 'DM Mono, monospace', fontSize: 18, fontWeight: 700 }}>
                    {sliderResult.fire_year ?? 'N/A'}
                  </div>
                </div>
                <div>
                  <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase' }}>Net worth at retirement</div>
                  <div style={{ color: '#2dbd7e', fontFamily: 'DM Mono, monospace', fontSize: 18, fontWeight: 700 }}>
                    {fmt(sliderResult.total_net_worth_at_retirement)}
                  </div>
                </div>
              </div>
            )}
        </div>
      )}
      {retireDelta === 0 && savingsBoost === 0 && (
        <div style={{ color: '#8b949e', fontSize: 12, marginTop: 10 }}>
          Adjust a slider above to run a scenario comparison.
        </div>
      )}
    </Panel>
  )
}

// (Historical backtest moved to Timeline screen — Chart/Table/Backtest tabs)


// ── MC Insights panel ─────────────────────────────────────────────────────────

interface MCInsight {
  category: string; priority: string; title: string; detail: string
  action: string; impact: string; colour: string; icon: string
}
interface MCInsightResult {
  prob_fire: number; n_simulations: number
  insights: MCInsight[]; overall_health: string; summary: string
}

function MCInsightsPanel({ scenarioPath, timeline, monteCarlo }: {
  scenarioPath: string
  timeline: any
  monteCarlo: any
}) {
  if (!monteCarlo) return null

  const latestSnap    = timeline?.years?.at(-1)
  const fireYear      = timeline?.fire_year
  const currentNW     = latestSnap?.total_net_worth ?? 0
  const currentYear   = new Date().getFullYear()
  const yearsToFire   = fireYear ? fireYear - currentYear : undefined

  const params = new URLSearchParams({
    scenario_path: scenarioPath,
    prob_fire: String(monteCarlo.prob_fire ?? 0.85),
    n_simulations: String(monteCarlo.n_simulations ?? 1000),
    ...(fireYear         ? { fire_year: String(fireYear) }           : {}),
    ...(currentNW        ? { current_nw: String(currentNW) }         : {}),
    ...(yearsToFire      ? { years_to_fire: String(yearsToFire) }    : {}),
  })

  const { data, isLoading } = useQuery<MCInsightResult>({
    queryKey: ['mc-insights', scenarioPath, monteCarlo.prob_fire],
    queryFn: () => apiClient.get(`/insights/mc?${params}`).then(r => r.data),
    staleTime: 300_000,
    enabled: !!monteCarlo,
  })

  const PRIORITY_ORDER: Record<string,number> = { HIGH:0, MEDIUM:1, LOW:2 }
  const HEALTH_COLOUR: Record<string,string> = {
    excellent:'#2dbd7e', good:'#0e9aad', caution:'#f0a500', at_risk:'#e05252'
  }

  const highCount = data?.insights.filter(i=>i.priority==='HIGH').length ?? 0
  const badge = data
    ? (highCount > 0 ? `${highCount} urgent` : `${data.insights.length} insights`)
    : undefined
  const badgeColour = highCount > 0 ? '#e05252' : '#0e9aad'

  return (
    <Panel title="Plan Insights" badge={badge} accentColour={badgeColour} defaultOpen={!!highCount}>
      {isLoading && <div style={{ color:'#8fa3b8', fontSize:13 }}>Generating insights…</div>}
      {data && (
        <>
          <div style={{ background:`${HEALTH_COLOUR[data.overall_health]??'#0e9aad'}11`,
                        border:`1px solid ${HEALTH_COLOUR[data.overall_health]??'#0e9aad'}44`,
                        borderRadius:8, padding:'10px 14px', marginBottom:12, fontSize:13,
                        color:'#e8edf2' }}>
            {data.summary}
          </div>
          {[...data.insights].sort((a,b)=>(PRIORITY_ORDER[a.priority]??9)-(PRIORITY_ORDER[b.priority]??9))
            .map((insight, i) => (
            <InsightCard key={i} insight={insight} />
          ))}
        </>
      )}
    </Panel>
  )
}

function InsightCard({ insight }: { insight: MCInsight }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ background:`${insight.colour}0d`, border:`1px solid ${insight.colour}33`,
                  borderRadius:8, padding:'10px 14px', marginBottom:8, cursor:'pointer' }}
         onClick={()=>setExpanded(e=>!e)}>
      <div style={{ display:'flex', alignItems:'flex-start', gap:10 }}>
        <span style={{ fontSize:16, flexShrink:0 }}>{insight.icon}</span>
        <div style={{ flex:1 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:2 }}>
            <span style={{ background:`${insight.colour}22`, color:insight.colour,
                           border:`1px solid ${insight.colour}44`, borderRadius:3,
                           padding:'1px 6px', fontSize:9, fontWeight:700 }}>
              {insight.priority}
            </span>
            <span style={{ color:'#e8edf2', fontSize:12, fontWeight:600 }}>{insight.title}</span>
          </div>
          {expanded && (
            <>
              <p style={{ color:'#8fa3b8', fontSize:11, lineHeight:1.5, margin:'6px 0 4px' }}>
                {insight.detail}
              </p>
              {insight.action && (
                <p style={{ color:insight.colour, fontSize:11, margin:0, fontWeight:500 }}>
                  → {insight.action}
                </p>
              )}
              {insight.impact && (
                <p style={{ color:'#8b949e', fontSize:10, margin:'4px 0 0',
                            fontStyle:'italic' }}>
                  Impact: {insight.impact}
                </p>
              )}
            </>
          )}
        </div>
        <span style={{ color:'#8b949e', fontSize:11, flexShrink:0 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>
    </div>
  )
}

// ── Price staleness panel ─────────────────────────────────────────────────────

interface StaleHolding {
  account_name: string; holding_name: string; isin: string
  days_since_update: number; current_price: number | null
}
interface StalenessData { stale_holdings: StaleHolding[]; has_stale: boolean }

function PriceStalePanel({ scenarioPath }: { scenarioPath: string }) {
  const { data } = useQuery<StalenessData>({
    queryKey: ['price-staleness', scenarioPath],
    queryFn: () => apiClient.get(`/market-data/staleness?scenario_path=${encodeURIComponent(scenarioPath)}`).then(r=>r.data),
    staleTime: 60_000,
  })

  if (!data?.has_stale) return null

  return (
    <div style={{ background:'#f0a50011', border:'1px solid #f0a50044', borderRadius:10,
                  padding:'10px 16px', marginTop:12 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div style={{ color:'#f0a500', fontSize:12, fontWeight:600 }}>
          ⚠ {data.stale_holdings.length} holding{data.stale_holdings.length!==1?'s':''} with stale prices
        </div>
        <button onClick={()=>window.dispatchEvent(new CustomEvent('refresh-prices'))}
                style={{ background:'#f0a500', color:'#fff', border:'none', borderRadius:6,
                          padding:'4px 12px', fontSize:11, cursor:'pointer', fontWeight:600 }}>
          Refresh prices
        </button>
      </div>
      <div style={{ marginTop:6, display:'flex', flexWrap:'wrap', gap:6 }}>
        {data.stale_holdings.map((h,i) => (
          <span key={i} style={{ background:'#f0a50018', color:'#f0a500', borderRadius:4,
                                  padding:'2px 8px', fontSize:10 }}>
            {h.holding_name} ({h.days_since_update}d)
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Sankey panel ──────────────────────────────────────────────────────────────

interface SankeyData {
  year: number; currency: string; nodes: SankeyNode[]; links: SankeyLink[]
  total_gross: number; warnings: string[]
}

function SankeyPanel({ scenarioPath }: { scenarioPath: string }) {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [visible, setVisible] = useState(true)

  const { data, isLoading } = useQuery<SankeyData>({
    queryKey: ['sankey', scenarioPath, year],
    queryFn: () =>
      apiClient.get(`/sankey-data?scenario_path=${encodeURIComponent(scenarioPath)}&year=${year}`)
               .then(r => r.data),
    staleTime: 120_000,
  })

  return (
    <Panel title="Cash Flow Breakdown" defaultOpen={true} accentColour="#0e9aad">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        {[currentYear, currentYear + 5, currentYear + 10].map(y => (
          <button key={y} onClick={() => setYear(y)} style={{
            padding: '3px 12px', borderRadius: 4, border: 'none', cursor: 'pointer',
            fontSize: 11, fontFamily: 'DM Mono, monospace',
            background: year === y ? '#0e9aad' : 'rgba(255,255,255,0.06)',
            color: year === y ? '#fff' : '#8fa3b8',
          }}>{y}</button>
        ))}
        {data && (
          <span style={{ color: '#8b949e', fontSize: 11, marginLeft: 'auto' }}>
            Total gross: <span style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace' }}>
              {fmt(data.total_gross)}
            </span>
          </span>
        )}
        <button onClick={() => setVisible(v => !v)} style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: '#8fa3b8', fontSize: 12,
        }}>{visible ? '▲ hide' : '▼ show'}</button>
      </div>
      {visible && (
        <>
          {isLoading && <div style={{ color: '#8fa3b8', fontSize: 13 }}>Loading cash flow…</div>}
          {data && data.nodes.length > 0 && (
            <SankeyChart nodes={data.nodes} links={data.links} height={320}
                         year={data.year} totalGross={data.total_gross} />
          )}
          {data && data.nodes.length === 0 && (
            <div style={{ color: '#8fa3b8', fontSize: 13, padding: 16, textAlign: 'center' }}>
              No active income sources for {year}.
            </div>
          )}
        </>
      )}
    </Panel>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export function Dashboard() {
  const { timeline, monteCarlo, isRunning } = useSimulationStore()
  const { activeScenarioPath } = useConfigStore()
  const scenarioName = activeScenarioPath.split('/').pop()?.replace('.yaml', '') ?? 'base'

  const latestSnap  = timeline?.years.at(-1)
  const fireYear    = timeline?.fire_year
  const currentYear = new Date().getFullYear()
  const yearsToFire = fireYear ? fireYear - currentYear : null
  const mcProb      = monteCarlo ? `${(monteCarlo.prob_fire * 100).toFixed(0)}%` : '—'

  // FIRE target from scenario (approximated from first snapshot's fire_coverage)
  const fireTarget = latestSnap && latestSnap.fire_coverage > 0
    ? latestSnap.total_net_worth / latestSnap.fire_coverage
    : null

  return (
    <div>
      <PageHeader title="Dashboard" subtitle={`Scenario: ${scenarioName}`} />

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {isRunning ? (
          <><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></>
        ) : (
          <>
            <KpiCard label="Current Net Worth"
                     value={latestSnap ? fmt(latestSnap.total_net_worth) : '—'}
                     sub={latestSnap ? `as of ${latestSnap.year}` : 'Run a simulation'}
                     accent="teal" />
            <KpiCard label="FIRE Year"
                     value={fireYear ? String(fireYear) : '—'}
                     sub={yearsToFire !== null ? `${yearsToFire} years away` : 'Not projected'}
                     accent="gold" />
            <KpiCard label="Years to FIRE"
                     value={yearsToFire !== null ? String(yearsToFire) : '—'}
                     sub={fireYear ? `Target: ${fireYear}` : 'Run a simulation'}
                     accent="green" />
            <KpiCard label="MC FIRE Probability"
                     value={mcProb}
                     sub={monteCarlo ? '1,000 simulations' : 'Run Monte Carlo'}
                     accent={monteCarlo ? (monteCarlo.prob_fire >= 0.9 ? 'green' : monteCarlo.prob_fire >= 0.7 ? 'gold' : 'red') : 'teal'} />
          </>
        )}
      </div>

      {/* Milestone cards (below KPIs, always visible when simulation run) */}
      <MilestoneCards
        nw={latestSnap?.total_net_worth ?? null}
        fireYear={fireYear ?? null}
        fireTarget={fireTarget}
        timeline={timeline}
      />

      {/* Timeline chart */}
      <div className="rounded-xl p-4 mt-4"
           style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}>
        <div className="text-xs font-semibold uppercase tracking-wide mb-4"
             style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}>
          Net Worth Timeline
        </div>
        {isRunning ? (
          <div className="rounded-lg flex items-center justify-center animate-pulse"
               style={{ height: 320, background: '#1d2f47' }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>Simulating…</span>
          </div>
        ) : (
          <TimelineChart data={timeline?.years ?? []} fireYear={timeline?.fire_year} />
        )}
      </div>

      {/* MC Plan Insights */}
      <MCInsightsPanel scenarioPath={activeScenarioPath} timeline={timeline} monteCarlo={monteCarlo} />

      {/* Price staleness alert */}
      <PriceStalePanel scenarioPath={activeScenarioPath} />

      {/* Planning coach alerts */}
      <PlanningCoachPanel
        scenarioPath={activeScenarioPath}
        nw={latestSnap?.total_net_worth ?? null}
        fireTarget={fireTarget}
        fireYear={fireYear ?? null}
      />

      {/* Scenario what-if sliders */}
      <ScenarioSliders scenarioPath={activeScenarioPath} />

      {/* Historical backtest: see Timeline → Backtest tab */}

      {/* Cash flow Sankey */}
      <SankeyPanel scenarioPath={activeScenarioPath} />

      {/* CTA when no data */}
      {!timeline && !isRunning && (
        <div className="mt-4 rounded-xl p-6 text-center"
             style={{ background: 'rgba(14,154,173,0.08)', border: '1px solid rgba(14,154,173,0.25)' }}>
          <p className="text-sm mb-1" style={{ color: '#e8edf2' }}>No simulation data yet</p>
          <p className="text-xs" style={{ color: '#8fa3b8' }}>
            Click <strong style={{ color: '#0e9aad' }}>Run Simulation</strong> in the top bar to
            generate a 50-year projection for the <em>{scenarioName}</em> scenario.
          </p>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
