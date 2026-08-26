/**
 * OpportunityAnalyser.tsx — Phase 10
 * "What if I'd invested that cash?" — DCA comparison across ETFs
 */

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, BarChart, Bar, Cell,
} from 'recharts'
import { PageHeader } from '../components/layout/PageHeader'
import { apiClient } from '../api/client'

const TEAL='#0e9aad', GOLD='#d4a843', GREEN='#2dbd7e', RED='#e05252',
      PURP='#a78bfa', ORNG='#f97316', BLUE='#58a6ff'

const COLORS = [TEAL, GOLD, GREEN, PURP, ORNG, BLUE]

const tipStyle = { background:'#0f1b2d', border:'1px solid #30363d',
                   borderRadius:8, color:'#e8edf2', fontSize:11 }

function fmt(v: number) {
  if (v >= 1_000_000) return `£${(v/1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v/1_000).toFixed(1)}k`
  return `£${Math.round(v).toLocaleString()}`
}

interface Fund { ticker: string; name: string; category: string }
interface MonthlySnap { date_str: string; portfolio_value: number; cumulative_invested: number; gain_pct: number }
interface FundResult {
  ticker: string; name: string; category: string
  total_invested: number; final_value: number; total_gain: number
  total_gain_pct: number; annualised_return: number
  monthly: MonthlySnap[]; error: string
}
interface CompareResult {
  start_date: string; end_date: string; total_invested: number
  funds: FundResult[]; best_fund_ticker: string
  cash_value: number; missed_gain: number; warnings: string[]
}

export function OpportunityAnalyser() {
  const [startDate, setStartDate] = useState('2018-01-01')
  const [endDate,   setEndDate]   = useState('2024-12-31')
  const [lumpSum,   setLumpSum]   = useState(0)
  const [monthly,   setMonthly]   = useState(500)
  const [selected,  setSelected]  = useState<string[]>(['VWRP.L','VUSA.L','IWDA.L'])

  // Load fund catalogue
  const { data: catalogue } = useQuery<Fund[]>({
    queryKey: ['fund-catalogue'],
    queryFn: () => apiClient.get('/analyser/funds').then(r=>r.data),
    staleTime: Infinity,
  })

  // DCA comparison mutation
  const compare = useMutation({
    mutationFn: () => apiClient.post('/analyser/compare', {
      tickers: selected, start_date: startDate, end_date: endDate,
      initial_lump_sum: lumpSum, monthly_contribution: monthly,
    }).then(r => r.data as CompareResult),
  })

  const result = compare.data
  const successFunds = result?.funds.filter(f => !f.error) ?? []

  // Build chart data aligned by date
  const chartData = (() => {
    if (!successFunds.length) return []
    const allDates = [...new Set(successFunds.flatMap(f => f.monthly.map(m => m.date_str)))].sort()
    return allDates.filter((_,i) => i % 2 === 0).map(d => {
      const row: Record<string, any> = { date: d.slice(0,7) }
      for (const f of successFunds) {
        const snap = f.monthly.find(m => m.date_str === d)
        row[f.ticker] = snap ? Math.round(snap.portfolio_value) : null
      }
      if (successFunds[0]) {
        const snap = successFunds[0].monthly.find(m => m.date_str === d)
        row['Invested'] = snap ? Math.round(snap.cumulative_invested) : null
      }
      return row
    })
  })()

  const labelS: React.CSSProperties = { color:'#8fa3b8', fontSize:11, marginBottom:4, display:'block' }
  const inputS: React.CSSProperties = {
    background:'#0f1b2d', border:'1px solid #30363d', borderRadius:6,
    color:'#e8edf2', padding:'7px 10px', fontSize:12, width:'100%', fontFamily:'DM Mono, monospace',
  }
  const numInputS: React.CSSProperties = { ...inputS, width:120 }

  return (
    <div>
      <PageHeader title="Opportunity Analyser"
                  subtitle="What would your cash have returned if invested?" />

      {/* Controls */}
      <div style={{ background:'#162236', borderRadius:12, padding:'18px 20px',
                    border:'1px solid rgba(255,255,255,0.07)', marginBottom:20 }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr auto auto', gap:16,
                      alignItems:'end', marginBottom:16 }}>
          <div>
            <label style={labelS}>Start date</label>
            <input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)} style={inputS} />
          </div>
          <div>
            <label style={labelS}>End date</label>
            <input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)} style={inputS} />
          </div>
          <div>
            <label style={labelS}>Lump sum (£)</label>
            <input type="number" value={lumpSum} onChange={e=>setLumpSum(Number(e.target.value))}
                   min={0} step={100} style={numInputS} />
          </div>
          <div>
            <label style={labelS}>Monthly (£)</label>
            <input type="number" value={monthly} onChange={e=>setMonthly(Number(e.target.value))}
                   min={0} step={50} style={numInputS} />
          </div>
        </div>

        {/* Fund picker */}
        <div style={{ marginBottom:14 }}>
          <label style={labelS}>Select up to 6 funds to compare</label>
          <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
            {(catalogue ?? []).map(f => {
              const active = selected.includes(f.ticker)
              const col = COLORS[selected.indexOf(f.ticker)] ?? '#8b949e'
              return (
                <button key={f.ticker} onClick={() => {
                  if (active) setSelected(s => s.filter(t => t !== f.ticker))
                  else if (selected.length < 6) setSelected(s => [...s, f.ticker])
                }} style={{
                  padding:'5px 12px', borderRadius:6, border:`1px solid ${active ? col+'88' : '#30363d'}`,
                  background: active ? `${col}18` : 'transparent',
                  color: active ? col : '#8fa3b8', fontSize:11, cursor:'pointer',
                  fontWeight: active ? 600 : 400,
                }}>
                  {active && <span style={{ marginRight:5 }}>●</span>}
                  {f.ticker.replace('.L','')} — {f.name.split(' ').slice(0,3).join(' ')}
                </button>
              )
            })}
          </div>
        </div>

        <button
          onClick={() => compare.mutate()}
          disabled={compare.isPending || selected.length === 0}
          style={{
            background: TEAL, color:'#fff', border:'none', borderRadius:8,
            padding:'10px 28px', fontSize:14, fontWeight:600,
            cursor: compare.isPending ? 'not-allowed' : 'pointer',
            opacity: compare.isPending ? 0.7 : 1,
          }}
        >
          {compare.isPending ? 'Fetching prices…' : 'Compare Funds'}
        </button>

        {compare.isPending && (
          <span style={{ color:'#8fa3b8', fontSize:12, marginLeft:14 }}>
            Downloading historical prices from Yahoo Finance…
          </span>
        )}
      </div>

      {result && (
        <>
          {/* Missed gain hero */}
          {result.missed_gain > 0 && (
            <div style={{ background:`${RED}0d`, border:`1px solid ${RED}44`, borderRadius:12,
                          padding:'16px 20px', marginBottom:20,
                          display:'flex', alignItems:'center', gap:24 }}>
              <div>
                <div style={{ color:'#8fa3b8', fontSize:11, textTransform:'uppercase',
                              letterSpacing:'0.06em' }}>Missed opportunity</div>
                <div style={{ color:RED, fontSize:32, fontWeight:700,
                              fontFamily:'DM Mono, monospace' }}>{fmt(result.missed_gain)}</div>
                <div style={{ color:'#8fa3b8', fontSize:12, marginTop:4 }}>
                  difference between keeping cash and investing in {result.best_fund_ticker.replace('.L','')}
                </div>
              </div>
              <div style={{ borderLeft:'1px solid #30363d', paddingLeft:24 }}>
                <div style={{ color:'#8b949e', fontSize:11 }}>Cash value today</div>
                <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:18, fontWeight:700 }}>
                  {fmt(result.cash_value)}
                </div>
                <div style={{ color:'#8b949e', fontSize:10, marginTop:4 }}>no investment, no return</div>
              </div>
            </div>
          )}

          {/* Fund result cards */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:20 }}>
            {successFunds.map((f, i) => {
              const col = COLORS[i] ?? TEAL
              const isBest = f.ticker === result.best_fund_ticker
              return (
                <div key={f.ticker} style={{ background:`${col}0d`,
                                              border:`1px solid ${col}${isBest?'88':'33'}`,
                                              borderRadius:12, padding:'14px 16px' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
                    <div style={{ color:col, fontWeight:700, fontSize:12 }}>
                      {f.ticker.replace('.L','')}
                    </div>
                    {isBest && (
                      <span style={{ background:`${GREEN}22`, color:GREEN, border:`1px solid ${GREEN}44`,
                                      borderRadius:3, padding:'1px 7px', fontSize:9, fontWeight:700 }}>BEST</span>
                    )}
                  </div>
                  <div style={{ color:'#8b949e', fontSize:10, marginBottom:8 }}>{f.name}</div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, fontSize:11 }}>
                    <div>
                      <div style={{ color:'#8b949e' }}>Final value</div>
                      <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:15 }}>
                        {fmt(f.final_value)}
                      </div>
                    </div>
                    <div>
                      <div style={{ color:'#8b949e' }}>Total gain</div>
                      <div style={{ color:f.total_gain>=0?GREEN:RED,
                                     fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:15 }}>
                        {f.total_gain>=0?'+':''}{fmt(f.total_gain)}
                      </div>
                    </div>
                    <div>
                      <div style={{ color:'#8b949e' }}>Return</div>
                      <div style={{ color:col, fontFamily:'DM Mono, monospace' }}>
                        {f.total_gain_pct>=0?'+':''}{f.total_gain_pct.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div style={{ color:'#8b949e' }}>CAGR</div>
                      <div style={{ color:col, fontFamily:'DM Mono, monospace' }}>
                        {f.annualised_return.toFixed(1)}%/yr
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Portfolio trajectory chart */}
          <div style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                        border:'1px solid rgba(255,255,255,0.07)', marginBottom:16 }}>
            <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                         textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
              Portfolio value over time
            </h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <XAxis dataKey="date" tick={{fill:'#8b949e',fontSize:9}} />
                <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
                <Tooltip formatter={(v:number,n:string)=>[fmt(v),n]} contentStyle={tipStyle} />
                <Legend wrapperStyle={{fontSize:10,color:'#8fa3b8'}} />
                <Line dataKey="Invested" stroke="#30363d" strokeWidth={1} dot={false}
                      strokeDasharray="4 2" name="Cash invested" />
                {successFunds.map((f,i)=>(
                  <Line key={f.ticker} dataKey={f.ticker} stroke={COLORS[i]??TEAL}
                        strokeWidth={2} dot={false} name={f.ticker.replace('.L','')} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* CAGR comparison bar chart */}
          <div style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                        border:'1px solid rgba(255,255,255,0.07)', marginBottom:16 }}>
            <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                         textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
              Annualised return (CAGR) comparison
            </h3>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={successFunds.map((f,i)=>({
                name: f.ticker.replace('.L',''),
                CAGR: f.annualised_return, idx: i,
              }))}>
                <XAxis dataKey="name" tick={{fill:'#8fa3b8',fontSize:10}} />
                <YAxis tickFormatter={v=>`${v}%`} tick={{fill:'#8b949e',fontSize:9}} />
                <Tooltip formatter={(v:number)=>[`${v.toFixed(1)}%`,'CAGR']} contentStyle={tipStyle} />
                <Bar dataKey="CAGR" radius={[4,4,0,0]}>
                  {successFunds.map((_,i)=>(
                    <Cell key={i} fill={COLORS[i]??TEAL} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {result.funds.filter(f=>f.error).map(f=>(
            <div key={f.ticker} style={{ color:ORNG, background:`${ORNG}11`, borderRadius:8,
                                          padding:'8px 14px', marginBottom:8, fontSize:12 }}>
              ⚠ {f.ticker}: {f.error}
            </div>
          ))}

          {result.warnings.map((w,i)=>(
            <div key={i} style={{ color:'#8b949e', fontSize:11, marginBottom:4 }}>ⓘ {w}</div>
          ))}

          <div style={{ background:'#0f1b2d', borderRadius:10, padding:'12px 16px',
                        marginTop:8, fontSize:11, color:'#8b949e', lineHeight:1.6 }}>
            <strong style={{color:'#8fa3b8'}}>Methodology:</strong> Dollar-cost averaging — buying at the monthly closing price.
            Returns are in GBP. London-listed ETF prices in pence are automatically converted to pounds.
            Past performance is not a guide to future returns. Data via Yahoo Finance.
            Dividends not included for accumulating share classes (already reflected in price).
          </div>
        </>
      )}

      {compare.isError && (
        <div style={{ color:RED, background:`${RED}11`, borderRadius:8,
                      padding:'12px 16px', fontSize:13 }}>
          ⚠ Comparison failed. Check your internet connection — historical prices are fetched live from Yahoo Finance.
        </div>
      )}
    </div>
  )
}
