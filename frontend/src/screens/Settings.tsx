/**
 * Settings.tsx — application settings, Google Drive, IFA export
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../components/layout/PageHeader'
import { useConfigStore } from '../store/configStore'
import { useSimulationStore } from '../store/simulationStore'
import { useConfigStore as cfg2 } from '../store/configStore'
import { apiClient } from '../api/client'

const TEAL='#0e9aad', GOLD='#d4a843', GREEN='#2dbd7e', RED='#e05252', PURP='#a78bfa'

const inputS: React.CSSProperties = {
  background:'#0f1b2d', border:'1px solid #30363d', borderRadius:6,
  color:'#e8edf2', padding:'7px 10px', fontSize:12, width:'100%',
  fontFamily:'DM Mono, monospace', outline:'none',
}
const labelS: React.CSSProperties = {
  color:'#8fa3b8', fontSize:11, display:'block', marginBottom:4, fontWeight:500,
}
function Card({ title, children, accent=TEAL }: {
  title: string; children: React.ReactNode; accent?: string
}) {
  return (
    <div style={{ background:'#162236', borderRadius:12, padding:'18px 20px',
                  border:'1px solid rgba(255,255,255,0.07)', marginBottom:16,
                  borderLeft:`3px solid ${accent}` }}>
      <h3 style={{ color:'#e8edf2', fontSize:13, fontWeight:600, margin:'0 0 16px' }}>{title}</h3>
      {children}
    </div>
  )
}

// ── Google Drive section ──────────────────────────────────────────────────────

interface DriveStatus { connected: boolean; message: string; last_sync_at: string }
interface AuthStart  { device_code: string; user_code: string; verification_url: string; interval: number }
interface AuthPoll   { status: string; message: string }

function GoogleDriveCard() {
  const qc = useQueryClient()
  const [clientId,     setClientId]     = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [authStart,    setAuthStart]    = useState<AuthStart|null>(null)
  const [polling,      setPolling]      = useState(false)
  const [pollMsg,      setPollMsg]      = useState('')

  const { data: status, refetch: refetchStatus } = useQuery<DriveStatus>({
    queryKey: ['drive-status'],
    queryFn: () => apiClient.get('/sync/status').then(r => r.data),
    staleTime: 30_000,
  })

  const startAuth = useMutation({
    mutationFn: () => apiClient.post('/sync/drive/auth/start',
      { client_id: clientId, client_secret: clientSecret }).then(r => r.data as AuthStart),
    onSuccess: (d) => { setAuthStart(d); setPollMsg('') },
  })

  const disconnect = useMutation({
    mutationFn: () => apiClient.delete('/sync/drive/auth'),
    onSuccess: () => { refetchStatus(); setAuthStart(null) },
  })

  const syncNow = useMutation({
    mutationFn: () => apiClient.post('/sync/push').then(r => r.data),
  })

  // Poll for token
  useEffect(() => {
    if (!authStart || !polling) return
    const iv = setInterval(async () => {
      try {
        const r = await apiClient.post('/sync/drive/auth/poll', {
          client_id: clientId, client_secret: clientSecret,
          device_code: authStart.device_code,
        })
        const d = r.data as AuthPoll
        setPollMsg(d.message)
        if (d.status === 'approved') {
          setPolling(false); setAuthStart(null)
          refetchStatus()
        } else if (d.status !== 'pending') {
          setPolling(false)
        }
      } catch { setPolling(false) }
    }, (authStart.interval + 1) * 1000)
    return () => clearInterval(iv)
  }, [authStart, polling, clientId, clientSecret])

  if (status?.connected) {
    return (
      <Card title="Google Drive" accent={GREEN}>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:14 }}>
          <span style={{ background:`${GREEN}22`, color:GREEN, border:`1px solid ${GREEN}44`,
                          borderRadius:20, padding:'4px 14px', fontSize:12, fontWeight:600 }}>
            ✓ Connected
          </span>
          <span style={{ color:'#8b949e', fontSize:11 }}>{status.message}</span>
        </div>
        {status.last_sync_at && (
          <div style={{ color:'#8b949e', fontSize:11, marginBottom:14 }}>
            Last synced: {status.last_sync_at.slice(0,16).replace('T',' ')} UTC
          </div>
        )}
        <div style={{ display:'flex', gap:10 }}>
          <button onClick={() => syncNow.mutate()}
                  disabled={syncNow.isPending}
                  style={{ background:TEAL, color:'#fff', border:'none', borderRadius:6,
                            padding:'7px 18px', fontSize:12, fontWeight:600, cursor:'pointer' }}>
            {syncNow.isPending ? 'Syncing…' : 'Sync Scenarios Now'}
          </button>
          <button onClick={() => disconnect.mutate()}
                  style={{ background:'transparent', color:RED, border:`1px solid ${RED}44`,
                            borderRadius:6, padding:'7px 14px', fontSize:12, cursor:'pointer' }}>
            Disconnect
          </button>
        </div>
        {syncNow.data && (
          <div style={{ color:GREEN, fontSize:11, marginTop:8 }}>
            ✓ Synced {syncNow.data.synced?.length ?? 0} file(s)
            {syncNow.data.errors?.length > 0 && (
              <span style={{ color:RED, marginLeft:10 }}>{syncNow.data.errors.length} error(s)</span>
            )}
          </div>
        )}
      </Card>
    )
  }

  return (
    <Card title="Google Drive" accent={TEAL}>
      <p style={{ color:'#8fa3b8', fontSize:12, lineHeight:1.6, marginBottom:16 }}>
        Automatically back up scenario YAML files to your Google Drive.
        Uses the Device Authorization flow — no redirect URL needed.
      </p>
      <div style={{ background:'#0f1b2d', borderRadius:8, padding:'12px 14px',
                    marginBottom:16, fontSize:11, color:'#8b949e', lineHeight:1.7 }}>
        <strong style={{ color:'#8fa3b8' }}>Setup (one-time):</strong>
        {' '}Go to{' '}
        <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer"
           style={{ color:TEAL }}>console.cloud.google.com</a>
        {' '}→ New project → Enable Drive API → Create credentials
        → OAuth 2.0 → Application type: <strong style={{ color:'#e8edf2' }}>
          TV and Limited Input devices
        </strong> → copy Client ID and Client Secret.
      </div>

      {!authStart ? (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
            <div>
              <label style={labelS}>Client ID</label>
              <input style={inputS} value={clientId} onChange={e=>setClientId(e.target.value)}
                     placeholder="1234567890-abc...apps.googleusercontent.com" />
            </div>
            <div>
              <label style={labelS}>Client Secret</label>
              <input style={{ ...inputS, fontFamily:'monospace' }} type="password"
                     value={clientSecret} onChange={e=>setClientSecret(e.target.value)}
                     placeholder="GOCSPX-…" />
            </div>
          </div>
          <button onClick={() => startAuth.mutate()}
                  disabled={!clientId || !clientSecret || startAuth.isPending}
                  style={{ background:TEAL, color:'#fff', border:'none', borderRadius:6,
                            padding:'8px 20px', fontSize:12, fontWeight:600, cursor:'pointer',
                            opacity: !clientId || !clientSecret ? 0.5 : 1 }}>
            {startAuth.isPending ? 'Contacting Google…' : 'Connect Google Drive'}
          </button>
        </>
      ) : (
        <div style={{ background:'#0f1b2d', borderRadius:10, padding:'16px 18px' }}>
          <div style={{ color:'#e8edf2', fontSize:13, fontWeight:600, marginBottom:10 }}>
            Step 2 — Authorise on your phone or PC
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:14 }}>
            <div>
              <div style={{ color:'#8b949e', fontSize:10, textTransform:'uppercase', marginBottom:4 }}>
                Visit this URL
              </div>
              <a href={authStart.verification_url} target="_blank" rel="noreferrer"
                 style={{ color:TEAL, fontSize:13, fontWeight:600 }}>
                {authStart.verification_url}
              </a>
            </div>
            <div>
              <div style={{ color:'#8b949e', fontSize:10, textTransform:'uppercase', marginBottom:4 }}>
                Enter this code
              </div>
              <div style={{ color:'#e8edf2', fontFamily:'DM Mono, monospace', fontSize:20,
                             fontWeight:700, letterSpacing:'0.15em',
                             background:'#162236', padding:'6px 14px', borderRadius:6 }}>
                {authStart.user_code}
              </div>
            </div>
          </div>
          <div style={{ display:'flex', gap:10 }}>
            <button onClick={() => setPolling(true)} disabled={polling}
                    style={{ background:GREEN, color:'#fff', border:'none', borderRadius:6,
                              padding:'8px 20px', fontSize:12, fontWeight:600, cursor:'pointer',
                              opacity:polling?0.7:1 }}>
              {polling ? 'Waiting for approval…' : 'I\'ve authorised — verify'}
            </button>
            <button onClick={() => { setAuthStart(null); setPolling(false) }}
                    style={{ background:'transparent', color:'#8fa3b8',
                              border:'1px solid #30363d', borderRadius:6,
                              padding:'8px 14px', fontSize:12, cursor:'pointer' }}>
              Cancel
            </button>
          </div>
          {pollMsg && (
            <div style={{ color:polling ? GOLD : GREEN, fontSize:11, marginTop:8 }}>
              {pollMsg}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── IFA Export Pack ───────────────────────────────────────────────────────────

function IFAExportCard() {
  const { activeScenarioPath } = cfg2()
  const [preparedFor,  setPreparedFor]  = useState('')
  const [watermark,    setWatermark]    = useState('CONFIDENTIAL')
  const [jobId,        setJobId]        = useState<string|null>(null)
  const [downloadUrl,  setDownloadUrl]  = useState<string|null>(null)

  const generate = useMutation({
    mutationFn: () => apiClient.post('/reports/generate', {
      title: 'LifeLedger Financial Plan',
      subtitle: 'Prepared by LifeLedger',
      prepared_for: preparedFor || 'Client',
      prepared_by: 'LifeLedger',
      scenario_path: activeScenarioPath,
      preset: 'ifa_pack',
      watermark: watermark || null,
      include_monte_carlo: true,
      mc_simulations: 500,
      paper_size: 'A4',
    }).then(r => r.data),
    onSuccess: (d) => { setJobId(d.job_id); setDownloadUrl(null) },
  })

  // Poll job status
  const { data: jobStatus } = useQuery({
    queryKey: ['report-job', jobId],
    queryFn: () => apiClient.get(`/reports/status/${jobId}`).then(r => r.data),
    enabled: !!jobId && !downloadUrl,
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'complete' || status === 'failed' ? false : 2_000
    },
    staleTime: 0,
  })

  useEffect(() => {
    if (jobStatus?.status === 'complete' && jobId && !downloadUrl) {
      setDownloadUrl(`/api/reports/download/${jobId}`)
    }
  }, [jobStatus, jobId, downloadUrl])

  const isRunning = jobStatus?.status === 'running' || jobStatus?.status === 'queued'

  return (
    <Card title="IFA Export Pack" accent={GOLD}>
      <p style={{ color:'#8fa3b8', fontSize:12, lineHeight:1.6, marginBottom:16 }}>
        Generate a professional PDF report for your Independent Financial Adviser.
        Includes cover page, executive summary, net worth timeline, income coverage,
        estate analysis, Monte Carlo results, and regulatory disclaimer.
      </p>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
        <div>
          <label style={labelS}>Prepared for (client name)</label>
          <input style={inputS} value={preparedFor} onChange={e=>setPreparedFor(e.target.value)}
                 placeholder="e.g. Mr & Mrs Smith" />
        </div>
        <div>
          <label style={labelS}>Watermark</label>
          <select style={{ ...inputS, cursor:'pointer' }} value={watermark}
                  onChange={e=>setWatermark(e.target.value)}>
            <option value="">None</option>
            <option value="CONFIDENTIAL">CONFIDENTIAL</option>
            <option value="DRAFT">DRAFT</option>
          </select>
        </div>
      </div>
      <div style={{ display:'flex', gap:10, alignItems:'center', flexWrap:'wrap' }}>
        <button onClick={() => generate.mutate()} disabled={generate.isPending || isRunning}
                style={{ background:GOLD, color:'#0f1b2d', border:'none', borderRadius:6,
                          padding:'8px 22px', fontSize:12, fontWeight:700, cursor:'pointer',
                          opacity: generate.isPending || isRunning ? 0.6 : 1 }}>
          {isRunning ? 'Generating…' : generate.isPending ? 'Starting…' : 'Generate IFA Report'}
        </button>

        {isRunning && (
          <span style={{ color:GOLD, fontSize:12 }}>
            ⏳ {jobStatus?.progress_pct ? `${jobStatus.progress_pct}%` : 'Building report…'}
          </span>
        )}

        {downloadUrl && (
          <a href={downloadUrl} download style={{
            background:GREEN, color:'#fff', borderRadius:6,
            padding:'8px 22px', fontSize:12, fontWeight:600,
            textDecoration:'none', display:'inline-block',
          }}>
            ⬇ Download PDF
          </a>
        )}
      </div>

      {jobStatus?.status === 'failed' && (
        <div style={{ color:RED, fontSize:12, marginTop:8 }}>
          ⚠ Report generation failed: {jobStatus.error_message}
        </div>
      )}

      <div style={{ marginTop:14, padding:'10px 14px', background:'#0f1b2d', borderRadius:8,
                    fontSize:11, color:'#8b949e', lineHeight:1.6 }}>
        <strong style={{ color:'#8fa3b8' }}>IFA Pack includes:</strong> Cover page ·
        Assumptions · Net worth timeline · Income coverage analysis ·
        Drawdown strategy · Monte Carlo fan chart · Estate &amp; IHT summary ·
        Regulatory disclaimer
      </div>
    </Card>
  )
}

// ── Main Settings screen ──────────────────────────────────────────────────────

export function Settings() {
  const { currency, projectionStart, projectionEnd, inflationRate, setConfig } = useConfigStore()
  const [avKey, setAvKey] = useState('')

  return (
    <div>
      <PageHeader title="Settings" subtitle="Configuration · integrations · exports" />

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
        {/* Left column: projection settings */}
        <div>
          <Card title="Projection Settings">
            <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <div>
                <label style={labelS}>Currency</label>
                <select style={{ ...inputS, cursor:'pointer' }} value={currency}
                        onChange={e=>setConfig({ currency: e.target.value })}>
                  <option value="GBP">GBP (£)</option>
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                </select>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
                <div>
                  <label style={labelS}>Start year</label>
                  <input type="number" style={inputS} value={projectionStart}
                         onChange={e=>setConfig({ projectionStart: +e.target.value })} />
                </div>
                <div>
                  <label style={labelS}>End year</label>
                  <input type="number" style={inputS} value={projectionEnd}
                         onChange={e=>setConfig({ projectionEnd: +e.target.value })} />
                </div>
              </div>
              <div>
                <label style={labelS}>Inflation rate (e.g. 0.025 = 2.5%)</label>
                <input type="number" step="0.001" style={inputS} value={inflationRate}
                       onChange={e=>setConfig({ inflationRate: +e.target.value })} />
              </div>
            </div>
          </Card>

          <Card title="Market Data API Keys" accent={PURP}>
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              <div>
                <label style={labelS}>Alpha Vantage API key (optional)</label>
                <input style={inputS} type="password" value={avKey}
                       onChange={e=>setAvKey(e.target.value)} placeholder="Enter key…" />
              </div>
              <button onClick={async () => {
                  await apiClient.post('/market-data/api-key',
                    { provider: 'alpha_vantage', key: avKey })
                }}
                style={{ background:PURP, color:'#fff', border:'none', borderRadius:6,
                          padding:'7px 18px', fontSize:12, cursor:'pointer', fontWeight:600 }}>
                Save Key
              </button>
              <div style={{ color:'#8b949e', fontSize:11, lineHeight:1.6 }}>
                LifeLedger uses yfinance for most price data (no key required).
                An Alpha Vantage key adds intraday quotes and fundamental data.
                Keys are stored encrypted in the local SQLite database.
              </div>
            </div>
          </Card>
        </div>

        {/* Right column: Drive + IFA export */}
        <div>
          <GoogleDriveCard />
          <IFAExportCard />
        </div>
      </div>
    </div>
  )
}
