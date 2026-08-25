/**
 * CheckpointsScreen.tsx — record and compare net worth checkpoints
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
         ReferenceLine, Legend } from 'recharts'
import { PageHeader } from '../components/layout/PageHeader'
import { useSimulationStore } from '../store/simulationStore'
import { apiClient } from '../api/client'
import { CheckCircle, Plus, Trash2 } from 'lucide-react'

const TEAL='#0e9aad', GOLD='#d4a843', GREEN='#2dbd7e', RED='#e05252'
const tipStyle = { background:'#0f1b2d', border:'1px solid #30363d',
                   borderRadius:8, color:'#e8edf2', fontSize:11 }

function fmt(v: number) {
  if (v >= 1_000_000) return `£${(v/1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v/1_000).toFixed(1)}k`
  return `£${Math.round(v).toLocaleString()}`
}

interface Checkpoint { id: string; date: string; net_worth: number; note?: string }

export function CheckpointsScreen() {
  const qc = useQueryClient()
  const { timeline } = useSimulationStore()
  const [showForm, setShowForm] = useState(false)
  const [date, setDate]         = useState(new Date().toISOString().slice(0,10))
  const [nw,   setNw]           = useState('')
  const [note, setNote]         = useState('')

  const { data: checkpoints=[], isLoading } = useQuery<Checkpoint[]>({
    queryKey: ['checkpoints'],
    queryFn: () => apiClient.get('/checkpoints').then(r =>
      Array.isArray(r.data) ? r.data.map((c:any) => ({
        id: c.id ?? c, date: c.date ?? '', net_worth: c.net_worth ?? 0, note: c.note ?? '',
      })) : []
    ),
    staleTime: 60_000,
  })

  const add = useMutation({
    mutationFn: () => apiClient.post('/checkpoints', {
      date, net_worth: parseFloat(nw), note,
    }).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries({queryKey:['checkpoints']}); setShowForm(false); setNw(''); setNote('') },
  })

  const del = useMutation({
    mutationFn: (id:string) => apiClient.delete(`/checkpoints/${id}`),
    onSuccess: () => qc.invalidateQueries({queryKey:['checkpoints']}),
  })

  // Build divergence chart: checkpoint actuals vs simulation projected
  const chartData = (() => {
    if (!timeline || !checkpoints.length) return []
    const simByYear = new Map(timeline.years.map(y=>[y.year, y.total_net_worth]))
    return checkpoints
      .filter(c => c.date && c.net_worth)
      .sort((a,b)=>a.date.localeCompare(b.date))
      .map(c => {
        const yr = parseInt(c.date.slice(0,4))
        const projected = simByYear.get(yr)
        const divergence = projected ? c.net_worth - projected : null
        return {
          date: c.date.slice(0,7), actual: c.net_worth,
          projected: projected ?? null,
          divergence: divergence ?? null,
        }
      })
  })()

  const inputS: React.CSSProperties = {
    background:'#0f1b2d', border:'1px solid #30363d', borderRadius:6,
    color:'#e8edf2', padding:'7px 10px', fontSize:12, fontFamily:'DM Mono, monospace',
  }

  return (
    <div>
      <PageHeader
        title="Checkpoints"
        subtitle="Actual net worth vs projected"
        actions={
          <button onClick={()=>setShowForm(f=>!f)}
                  style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 14px',
                            borderRadius:6, border:'1px solid rgba(255,255,255,0.1)',
                            background:'transparent', color:'#8fa3b8', fontSize:12, cursor:'pointer' }}>
            <Plus size={13} />
            Add Checkpoint
          </button>
        }
      />

      {/* Add form */}
      {showForm && (
        <div style={{ background:'#162236', borderRadius:12, padding:'18px 20px',
                      border:`1px solid ${TEAL}44`, marginBottom:20 }}>
          <h3 style={{ color:'#e8edf2', fontSize:13, fontWeight:600, margin:'0 0 14px' }}>
            New Checkpoint
          </h3>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 2fr', gap:12, alignItems:'end' }}>
            <div>
              <label style={{ color:'#8fa3b8', fontSize:11, display:'block', marginBottom:4 }}>Date</label>
              <input type="date" value={date} onChange={e=>setDate(e.target.value)} style={inputS} />
            </div>
            <div>
              <label style={{ color:'#8fa3b8', fontSize:11, display:'block', marginBottom:4 }}>Net worth (£)</label>
              <input type="number" placeholder="e.g. 750000" value={nw}
                     onChange={e=>setNw(e.target.value)} style={inputS} />
            </div>
            <div>
              <label style={{ color:'#8fa3b8', fontSize:11, display:'block', marginBottom:4 }}>Note (optional)</label>
              <input type="text" placeholder="e.g. Sold rental property" value={note}
                     onChange={e=>setNote(e.target.value)} style={{...inputS, width:'100%'}} />
            </div>
          </div>
          <div style={{ display:'flex', gap:10, marginTop:14 }}>
            <button onClick={()=>add.mutate()}
                    disabled={!nw || add.isPending}
                    style={{ background:TEAL, color:'#fff', border:'none', borderRadius:6,
                              padding:'8px 20px', fontSize:12, fontWeight:600, cursor:'pointer' }}>
              {add.isPending ? 'Saving…' : 'Save Checkpoint'}
            </button>
            <button onClick={()=>setShowForm(false)}
                    style={{ background:'transparent', color:'#8fa3b8', border:'1px solid #30363d',
                              borderRadius:6, padding:'8px 16px', fontSize:12, cursor:'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Divergence chart */}
      {chartData.length >= 2 && timeline && (
        <div style={{ background:'#162236', borderRadius:12, padding:'16px 20px',
                      border:'1px solid rgba(255,255,255,0.07)', marginBottom:20 }}>
          <h3 style={{ color:'#8fa3b8', fontSize:11, fontWeight:600,
                       textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 14px' }}>
            Actual vs Projected
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <XAxis dataKey="date" tick={{fill:'#8b949e',fontSize:9}} />
              <YAxis tickFormatter={v=>`£${(v/1000).toFixed(0)}k`} tick={{fill:'#8b949e',fontSize:9}} />
              <Tooltip formatter={(v:number,n:string)=>[fmt(v),n]} contentStyle={tipStyle} />
              <Legend wrapperStyle={{fontSize:11,color:'#8fa3b8'}} />
              <ReferenceLine y={0} stroke="#30363d" />
              <Line dataKey="actual"    stroke={GREEN} strokeWidth={2} dot={{fill:GREEN,r:4}} name="Actual" />
              <Line dataKey="projected" stroke={TEAL}  strokeWidth={1.5} dot={false}
                    strokeDasharray="5 3" name="Projected" connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Checkpoint list */}
      {isLoading ? (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {[1,2,3].map(i=>(
            <div key={i} style={{ height:60, borderRadius:10, background:'#162236',
                                   animation:'pulse 1.5s infinite' }} />
          ))}
        </div>
      ) : checkpoints.length > 0 ? (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {[...checkpoints].sort((a,b)=>b.date.localeCompare(a.date)).map(cp => {
            // Compare with projected for this year
            const yr = parseInt(cp.date.slice(0,4))
            const projected = timeline?.years.find(y=>y.year===yr)?.total_net_worth
            const delta = projected ? cp.net_worth - projected : null
            return (
              <div key={cp.id} style={{ background:'#162236', borderRadius:10,
                                         padding:'14px 16px', border:'1px solid rgba(255,255,255,0.07)',
                                         display:'flex', alignItems:'center', gap:12 }}>
                <CheckCircle size={16} style={{ color:GREEN, flexShrink:0 }} />
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'baseline', gap:10 }}>
                    <span style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontWeight:700, fontSize:14 }}>
                      {fmt(cp.net_worth)}
                    </span>
                    {delta !== null && (
                      <span style={{ color:delta>=0?GREEN:RED, fontSize:11, fontFamily:'DM Mono, monospace' }}>
                        {delta>=0?'▲ +':'▼ '}{fmt(Math.abs(delta))} vs projected
                      </span>
                    )}
                  </div>
                  <div style={{ color:'#8b949e', fontSize:11, marginTop:2 }}>
                    {cp.date}
                    {cp.note && <span style={{ marginLeft:10, color:'#8fa3b8' }}>{cp.note}</span>}
                  </div>
                </div>
                <button onClick={()=>del.mutate(cp.id)}
                        style={{ background:'transparent', border:'none', cursor:'pointer',
                                  color:'#8b949e', padding:4, opacity:0.6 }}>
                  <Trash2 size={14} />
                </button>
              </div>
            )
          })}
        </div>
      ) : (
        <div style={{ background:'#162236', borderRadius:12, padding:'40px 20px',
                      border:'1px solid rgba(255,255,255,0.07)', textAlign:'center' }}>
          <CheckCircle size={36} style={{ color:'#8fa3b8', opacity:0.3, margin:'0 auto 12px' }} />
          <h3 style={{ color:'#e8edf2', fontSize:13, fontWeight:600, marginBottom:6 }}>
            No checkpoints yet
          </h3>
          <p style={{ color:'#8fa3b8', fontSize:12, lineHeight:1.6, maxWidth:380, margin:'0 auto' }}>
            Checkpoints record your actual net worth at a point in time. Add one to compare
            against the projected simulation and track divergence over time.
          </p>
        </div>
      )}
    </div>
  )
}
