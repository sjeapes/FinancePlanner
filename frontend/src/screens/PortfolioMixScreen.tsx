/**
 * PortfolioMixScreen.tsx — asset allocation, target mix and rebalancing
 */
import { useState, useMemo } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { PageHeader } from '../components/layout/PageHeader'
import { useSimulationStore } from '../store/simulationStore'
import { useScenarioStore } from '../store/scenarioStore'
import type { AccountBreakdown, AccountSnapshotOut } from '../types'

const TEAL='#0e9aad', GOLD='#d4a843', GREEN='#2dbd7e', PURP='#a78bfa', SLATE='#8fa3b8'
const COLORS = [TEAL, GOLD, GREEN, PURP, SLATE]
const tipStyle = { background:'#0f1b2d', border:'1px solid #30363d',
                   borderRadius:8, color:'#e8edf2', fontSize:11 }

function fmt(v: number) {
  if (v >= 1_000_000) return `£${(v/1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v/1_000).toFixed(0)}k`
  return `£${Math.round(v).toLocaleString()}`
}

const EMPTY_BD: AccountBreakdown = {
  savings_total:0, investments_total:0, pensions_total:0,
  property_net:0, cash_total:0,
}
const INV = new Set(['ISA','cash_ISA','LISA'])
const PEN = new Set(['SIPP','workplace_DC','DB'])

function computeBreakdown(accs: Record<string,AccountSnapshotOut>): AccountBreakdown {
  const bd = {...EMPTY_BD}
  for (const a of Object.values(accs)) {
    const v=a.value, t=a.account_type
    if (INV.has(t))                  bd.investments_total += v
    else if (PEN.has(t))             bd.pensions_total    += v
    else if (t==='property'||t==='mortgage') bd.property_net += v
    else if (t==='GIA')              bd.savings_total     += v
    else                             bd.cash_total        += v
  }
  return bd
}

const BUCKETS = [
  { key:'investments_total' as keyof AccountBreakdown, label:'ISA / Investments', color:TEAL },
  { key:'pensions_total'    as keyof AccountBreakdown, label:'Pension',            color:GOLD },
  { key:'property_net'      as keyof AccountBreakdown, label:'Property (net)',     color:GREEN },
  { key:'savings_total'     as keyof AccountBreakdown, label:'GIA / Savings',      color:PURP },
  { key:'cash_total'        as keyof AccountBreakdown, label:'Cash',               color:SLATE },
]

export function PortfolioMixScreen() {
  const { timeline }      = useSimulationStore()
  const { activeScenario} = useScenarioStore()

  const latestSnap  = timeline?.years.at(-1)
  const actual: AccountBreakdown = latestSnap ? computeBreakdown(latestSnap.accounts) : EMPTY_BD
  const total = Math.max(1, (Object.values(actual) as number[]).reduce((a,b)=>a+Math.max(0,b),0))

  // Default target = current allocation
  const defaultTarget = useMemo(() => ({
    investments_total: Math.round((Math.max(0, actual.investments_total)/total)*100),
    pensions_total:    Math.round((Math.max(0, actual.pensions_total)/total)*100),
    property_net:      Math.round((Math.max(0, actual.property_net)/total)*100),
    savings_total:     Math.round((Math.max(0, actual.savings_total)/total)*100),
    cash_total:        Math.round((Math.max(0, actual.cash_total)/total)*100),
  }), [total, actual])

  const [target, setTarget] = useState<Record<string,number>>(defaultTarget)

  const pieData = BUCKETS.map(b => ({
    name: b.label,
    value: Math.max(0, actual[b.key] as number),
    color: b.color,
  })).filter(d=>d.value>0)

  const targetTotal = Object.values(target).reduce((a,b)=>a+b,0)

  const rebalanceActions = BUCKETS.map(b => {
    const actualPct = (Math.max(0, actual[b.key] as number)/total)*100
    const targetPct = target[b.key] ?? 0
    const diff      = targetPct - actualPct
    const diffAmt   = (diff/100)*total
    return { ...b, actualPct, targetPct, diff, diffAmt }
  }).filter(a=>Math.abs(a.diff)>0.5)

  const sliderStyle: React.CSSProperties = { width:'100%', accentColor:TEAL, cursor:'pointer' }
  const labelStyle:  React.CSSProperties = { color:'#8fa3b8', fontSize:11 }

  return (
    <div>
      <PageHeader title="Portfolio Mix" subtitle="Asset allocation & rebalancing" />

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:20 }}>
        {/* Actual allocation pie */}
        <div style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                      border:'1px solid rgba(255,255,255,0.07)' }}>
          <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                       textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
            Current Allocation
          </h3>
          {total > 1 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" outerRadius={80} dataKey="value"
                     label={({name,percent})=>`${(percent*100).toFixed(0)}%`}
                     labelLine={false}>
                  {pieData.map((_,i)=><Cell key={i} fill={pieData[i].color} />)}
                </Pie>
                <Tooltip formatter={(v:number)=>[fmt(v)]} contentStyle={tipStyle} />
                <Legend formatter={n=>n} wrapperStyle={{fontSize:11,color:'#8fa3b8'}} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color:'#8fa3b8', fontSize:13, textAlign:'center', padding:40 }}>
              Run a simulation to see allocation
            </div>
          )}
        </div>

        {/* Breakdown table */}
        <div style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                      border:'1px solid rgba(255,255,255,0.07)' }}>
          <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                       textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
            Breakdown
          </h3>
          {BUCKETS.map(b=>{
            const val = Math.max(0, actual[b.key] as number)
            const pct = ((val/total)*100).toFixed(1)
            return (
              <div key={b.key} style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                                         marginBottom:10 }}>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ width:10, height:10, borderRadius:'50%', background:b.color, flexShrink:0 }} />
                  <span style={{ color:'#8fa3b8', fontSize:12 }}>{b.label}</span>
                </div>
                <div style={{ textAlign:'right' }}>
                  <span style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:12 }}>{fmt(val)}</span>
                  <span style={{ color:b.color, fontFamily:'DM Mono, monospace', fontSize:10, marginLeft:8 }}>{pct}%</span>
                </div>
              </div>
            )
          })}
          <div style={{ borderTop:'1px solid #1d2f47', paddingTop:10, marginTop:6,
                         display:'flex', justifyContent:'space-between' }}>
            <span style={{ color:'#8fa3b8', fontSize:12 }}>Total</span>
            <span style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:14, fontWeight:700 }}>
              {fmt(total)}
            </span>
          </div>
        </div>
      </div>

      {/* Target allocation sliders */}
      <div style={{ background:'#162236', borderRadius:12, padding:'18px 20px',
                    border:'1px solid rgba(255,255,255,0.07)', marginBottom:16 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
          <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                       textTransform:'uppercase', letterSpacing:'0.06em', margin:0 }}>
            Target Allocation
          </h3>
          <span style={{ color: targetTotal===100 ? GREEN : '#e05252',
                          fontSize:12, fontFamily:'DM Mono, monospace', fontWeight:700 }}>
            {targetTotal}% {targetTotal!==100 && `(must equal 100%)`}
          </span>
        </div>
        {BUCKETS.map(b=>{
          const tPct = target[b.key] ?? 0
          const aPct = (Math.max(0, actual[b.key] as number)/total)*100
          const drift = tPct - aPct
          return (
            <div key={b.key} style={{ marginBottom:12 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                <span style={{ ...labelStyle, display:'flex', alignItems:'center', gap:6 }}>
                  <span style={{ width:8, height:8, borderRadius:'50%', background:b.color }} />
                  {b.label}
                </span>
                <span style={{ fontFamily:'DM Mono, monospace', fontSize:11 }}>
                  <span style={{ color:b.color }}>{tPct}%</span>
                  {Math.abs(drift)>0.5 && (
                    <span style={{ color:drift>0?GREEN:RED, marginLeft:8 }}>
                      {drift>0?'+':''}{drift.toFixed(0)}%
                    </span>
                  )}
                </span>
              </div>
              <input type="range" min={0} max={80} step={1} value={tPct}
                     onChange={e=>setTarget(t=>({...t,[b.key]:Number(e.target.value)}))}
                     style={{...sliderStyle, accentColor:b.color}} />
            </div>
          )
        })}
      </div>

      {/* Rebalancing actions */}
      {rebalanceActions.length > 0 && targetTotal===100 && (
        <div style={{ background:'#162236', borderRadius:12, padding:'18px 20px',
                      border:'1px solid rgba(255,255,255,0.07)', marginBottom:16 }}>
          <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                       textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
            Rebalancing Actions
          </h3>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
              <thead>
                <tr style={{ color:'#8b949e' }}>
                  {['Asset','Current','Target','Drift','Action (£)'].map(h=>(
                    <th key={h} style={{ padding:'6px 10px', fontWeight:500,
                                         borderBottom:'1px solid #1d2f47', textAlign:'right' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rebalanceActions.map(a=>(
                  <tr key={a.key} style={{ borderBottom:'1px solid #0f1b2d' }}>
                    <td style={{ padding:'8px 10px', display:'flex', alignItems:'center', gap:6 }}>
                      <span style={{ width:8, height:8, borderRadius:'50%', background:a.color }} />
                      <span style={{ color:'#e8edf2' }}>{a.label}</span>
                    </td>
                    <td style={{ padding:'8px 10px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#8fa3b8' }}>
                      {a.actualPct.toFixed(1)}%
                    </td>
                    <td style={{ padding:'8px 10px', textAlign:'right', fontFamily:'DM Mono, monospace', color:a.color }}>
                      {a.targetPct}%
                    </td>
                    <td style={{ padding:'8px 10px', textAlign:'right', fontFamily:'DM Mono, monospace',
                                  color:a.diff>0?GREEN:RED }}>
                      {a.diff>0?'+':''}{a.diff.toFixed(1)}%
                    </td>
                    <td style={{ padding:'8px 10px', textAlign:'right', fontFamily:'DM Mono, monospace',
                                  fontWeight:600, color:a.diffAmt>0?GREEN:RED }}>
                      {a.diffAmt>0?'Buy ':'Sell '}{fmt(Math.abs(a.diffAmt))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ color:'#8b949e', fontSize:11, marginTop:10, lineHeight:1.5 }}>
            These are indicative rebalancing amounts based on your current vs target allocation.
            Actual trades should account for ISA allowances, tax implications, and transaction costs.
            Use the Tax Optimiser for optimal drawdown order.
          </p>
        </div>
      )}

      {/* Holdings tables */}
      {activeScenario && activeScenario.investment_accounts.map(acc=>(
        acc.holdings?.length > 0 && (
          <div key={acc.id} style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                                      border:'1px solid rgba(255,255,255,0.07)', marginBottom:12 }}>
            <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                         textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 12px' }}>
              {acc.name} — Holdings
            </h3>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
              <thead>
                <tr style={{ color:'#8b949e' }}>
                  {['Holding','Units','Price','Value'].map(h=>(
                    <th key={h} style={{ padding:'5px 8px', fontWeight:500,
                                         borderBottom:'1px solid #1d2f47', textAlign:'right' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {acc.holdings.map((h:any)=>(
                  <tr key={h.id} style={{ borderBottom:'1px solid #0f1b2d' }}>
                    <td style={{ padding:'6px 8px', color:'#e8edf2' }}>{h.name}</td>
                    <td style={{ padding:'6px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#8fa3b8' }}>
                      {h.units?.toFixed(4) ?? '—'}
                    </td>
                    <td style={{ padding:'6px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:'#8fa3b8' }}>
                      {h.price_per_unit ? fmt(h.price_per_unit) : '—'}
                    </td>
                    <td style={{ padding:'6px 8px', textAlign:'right', fontFamily:'DM Mono, monospace', color:TEAL }}>
                      {h.units && h.price_per_unit ? fmt(h.units*h.price_per_unit) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ))}
    </div>
  )
}
