/**
 * FireTab.tsx — Guided FIRE (Financial Independence, Retire Early) tab.
 *
 * Shows current progress toward the user's FIRE number, the year FIRE is
 * projected to be reached (both computed by the existing projection engine
 * — nothing here re-derives that maths), and a small guided form for
 * setting/editing the FIRE target itself, pre-filled with a data-driven
 * suggestion pulled from the scenario's own post-retirement expenses.
 */

import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../components/layout/PageHeader'
import { useConfigStore } from '../store/configStore'
import { apiClient } from '../api/client'

const TEAL = '#0e9aad', GOLD = '#d4a843', GREEN = '#2dbd7e', RED = '#e05252'

function fmt(v: number) {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${Math.round(v).toLocaleString()}`
}

function Card({ title, children, accent = TEAL }: { title?: string; children: React.ReactNode; accent?: string }) {
  return (
    <div style={{ background: '#162236', borderRadius: 12, padding: 18,
                  borderLeft: `3px solid ${accent}`, marginBottom: 14 }}>
      {title && <h3 style={{ color: '#e8edf2', fontSize: 11, fontWeight: 600,
                              textTransform: 'uppercase', letterSpacing: '0.06em',
                              margin: '0 0 14px' }}>{title}</h3>}
      {children}
    </div>
  )
}

function KPI({ label, value, sub, accent = TEAL }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div style={{ background: '#0f1b2d', borderRadius: 10, padding: '12px 16px',
                  borderTop: `2px solid ${accent}` }}>
      <div style={{ color: '#8fa3b8', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ color: '#e8edf2', fontSize: 19, fontWeight: 700, fontFamily: 'DM Mono, monospace', marginTop: 4 }}>{value}</div>
      {sub && <div style={{ color: '#8b949e', fontSize: 10, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                  height: 180, color: '#8fa3b8', gap: 10, fontSize: 13 }}>
      <div style={{ width: 16, height: 16, border: `2px solid ${TEAL}`,
                    borderTopColor: 'transparent', borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite' }} />
      Loading…
    </div>
  )
}

interface FireStatus {
  has_fire_target: boolean
  fire_type: string
  annual_expenses_target: number
  swr: number
  explicit_target_net_worth: number
  fire_number: number
  current_net_worth: number
  primary_residence_excluded: number
  progress_pct: number
  fire_year: number | null
  years_to_fire: number | null
  current_fire_coverage: number
  retirement_year: number | null
  suggested_annual_expenses: number | null
  warnings: string[]
}

// Each type is a different lifestyle target, not just a label — switching
// type rescales the suggested expenses so the previewed number actually
// changes. Coast FIRE is handled separately: it doesn't scale expenses at
// all, it discounts the standard FIRE number back from retirement age.
const FIRE_TYPE_INFO: Record<string, { label: string; blurb: string; expenseMultiplier: number }> = {
  lean_fire: { label: 'Lean FIRE', blurb: 'A frugal number — covers essentials with little slack.', expenseMultiplier: 0.7 },
  fire:      { label: 'FIRE',      blurb: 'A comfortable, standard target using your usual spending.', expenseMultiplier: 1.0 },
  fat_fire:  { label: 'Fat FIRE',  blurb: 'A generous number with plenty of room for extras and buffer.', expenseMultiplier: 1.4 },
  coast_fire:{ label: 'Coast FIRE',blurb: "How much you need invested now so growth alone (no more saving) gets you to a standard FIRE number by retirement.", expenseMultiplier: 1.0 },
}

export function FireTab() {
  const { activeScenarioPath } = useConfigStore()
  const qc = useQueryClient()

  const { data, isLoading, isError, error } = useQuery<FireStatus>({
    queryKey: ['fire-status', activeScenarioPath],
    queryFn: () => apiClient.get('/fire/status', { params: { scenario_path: activeScenarioPath } }).then(r => r.data),
    staleTime: 30_000,
  })

  const [editing, setEditing] = useState(false)
  const [expenses, setExpenses] = useState('')
  const [swrPct, setSwrPct] = useState('4')
  const [fireType, setFireType] = useState('fire')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (data && !editing) {
      setExpenses(String(data.annual_expenses_target || Math.round(data.suggested_annual_expenses ?? 0)))
      setSwrPct(String((data.swr || 0.04) * 100))
      setFireType(data.fire_type || 'fire')
    }
  }, [data, editing])

  async function handleSave() {
    setSaving(true); setSaveError(null)
    try {
      await apiClient.put('/fire/target', {
        scenario_path: activeScenarioPath,
        annual_expenses_target: Number(expenses),
        swr: Number(swrPct) / 100,
        fire_type: fireType,
      })
      await qc.invalidateQueries({ queryKey: ['fire-status', activeScenarioPath] })
      setEditing(false)
    } catch (e: any) {
      setSaveError(e?.response?.data?.detail ?? e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader title="FIRE" subtitle="Financial Independence, Retire Early — your number and your date" />

      {isLoading && <Loading />}
      {isError && <Card accent={RED}>⚠ Couldn't load FIRE status: {(error as any)?.message ?? 'unknown error'}</Card>}

      {data && !editing && (
        <>
          {!data.has_fire_target && (
            <Card accent={GOLD} title="No FIRE target set yet">
              <p style={{ color: '#e8edf2', fontSize: 13, marginBottom: 12 }}>
                Set your target annual expenses and a safe withdrawal rate below and we'll work out
                your FIRE number and — using your existing scenario data — the year you're projected
                to hit it.
              </p>
              <button onClick={() => setEditing(true)} style={btnPrimary}>Set my FIRE number</button>
            </Card>
          )}

          {data.has_fire_target && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 14 }}>
                <KPI label="FIRE Number" value={fmt(data.fire_number)}
                     sub={`${FIRE_TYPE_INFO[data.fire_type]?.label ?? data.fire_type} · ${(data.swr * 100).toFixed(1)}% SWR`} />
                <KPI label="Investable Net Worth" value={fmt(data.current_net_worth)} accent={GREEN}
                     sub={data.primary_residence_excluded > 0 ? 'excludes your home' : undefined} />
                <KPI label="Progress" value={`${data.progress_pct.toFixed(0)}%`} accent={data.progress_pct >= 100 ? GREEN : TEAL}
                     sub={data.progress_pct >= 100 ? 'Target reached today' : undefined} />
                <KPI label="Projected FIRE Year" value={data.fire_year ? String(data.fire_year) : '—'}
                     sub={data.years_to_fire != null ? `${data.years_to_fire} year${data.years_to_fire === 1 ? '' : 's'} away` : 'Not reached in projection'}
                     accent={data.fire_year ? GREEN : GOLD} />
              </div>

              <Card title="Progress to FIRE number">
                <div style={{ height: 10, borderRadius: 6, background: '#0f1b2d', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${Math.min(100, data.progress_pct)}%`,
                    background: data.progress_pct >= 100 ? GREEN : TEAL,
                    borderRadius: 6, transition: 'width 0.4s',
                  }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 11, color: '#8fa3b8' }}>
                  <span>{fmt(data.current_net_worth)} today</span>
                  <span>{fmt(data.fire_number)} target</span>
                </div>
              </Card>

              {data.retirement_year && (
                <Card title="Planned retirement">
                  <div style={{ fontSize: 13, color: '#e8edf2' }}>
                    Planned retirement year: <strong style={{ fontFamily: 'DM Mono, monospace' }}>{data.retirement_year}</strong>
                    {data.suggested_annual_expenses != null && (
                      <> — projected annual expenses around then: <strong style={{ fontFamily: 'DM Mono, monospace' }}>{fmt(data.suggested_annual_expenses)}</strong> (that year's money, not today's)</>
                    )}
                  </div>
                </Card>
              )}

              <button onClick={() => setEditing(true)} style={btnSecondary}>Edit FIRE target</button>
            </>
          )}

          {data.warnings.length > 0 && (
            <Card accent={GOLD} title="Notes">
              {data.warnings.map((w, i) => <div key={i} style={{ color: GOLD, fontSize: 12, marginBottom: 4 }}>⚠ {w}</div>)}
            </Card>
          )}
        </>
      )}

      {data && editing && (
        <Card title="Set your FIRE target">
          <p style={{ color: '#8fa3b8', fontSize: 12, marginBottom: 14 }}>
            Your FIRE number is <strong>annual expenses ÷ safe withdrawal rate</strong>. We've suggested a
            starting figure below based on your own scenario's projected spending around your planned
            retirement — adjust it to whatever lifestyle you actually want.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <div>
              <label style={fieldLabel}>Target annual expenses in retirement</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: '#8fa3b8' }}>£</span>
                <input type="number" value={expenses} onChange={e => setExpenses(e.target.value)} style={inputStyle} />
              </div>
              {data.suggested_annual_expenses != null && (
                <button
                  type="button"
                  onClick={() => setExpenses(String(Math.round(data.suggested_annual_expenses!)))}
                  style={{ ...linkBtn, marginTop: 6 }}
                >
                  Use suggested: {fmt(data.suggested_annual_expenses)}
                </button>
              )}
            </div>
            <div>
              <label style={fieldLabel}>Safe withdrawal rate (%)</label>
              <input type="number" step="0.1" value={swrPct} onChange={e => setSwrPct(e.target.value)} style={inputStyle} />
              <div style={{ color: '#8fa3b8', fontSize: 11, marginTop: 6 }}>The classic "4% rule" is a common starting point.</div>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={fieldLabel}>FIRE type</label>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {Object.entries(FIRE_TYPE_INFO).map(([key, info]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setFireType(key)
                    // Rescale the expenses field to this type's baseline so
                    // switching types actually changes the previewed number
                    // — without this, every type shares whatever figure was
                    // typed in and the preview never moves.
                    const baseline = data.suggested_annual_expenses ?? Number(expenses) ?? 0
                    if (baseline > 0) {
                      setExpenses(String(Math.round(baseline * info.expenseMultiplier)))
                    }
                  }}
                  style={{
                    ...chipStyle,
                    background: fireType === key ? `${TEAL}22` : 'transparent',
                    borderColor: fireType === key ? TEAL : 'rgba(255,255,255,0.12)',
                    color: fireType === key ? TEAL : '#8fa3b8',
                  }}
                >
                  {info.label}
                </button>
              ))}
            </div>
            <div style={{ color: '#8fa3b8', fontSize: 11, marginTop: 8 }}>
              {FIRE_TYPE_INFO[fireType]?.blurb}
            </div>
          </div>

          {Number(expenses) > 0 && Number(swrPct) > 0 && (
            <div style={{ color: '#e8edf2', fontSize: 13, marginBottom: 16 }}>
              → This implies a standard FIRE number of <strong style={{ fontFamily: 'DM Mono, monospace', color: TEAL }}>
                {fmt(Number(expenses) / (Number(swrPct) / 100))}
              </strong>
              {fireType === 'coast_fire' && (
                <> — but Coast FIRE's actual number is that figure discounted back from your
                  {data.retirement_year ? ` retirement year (${data.retirement_year})` : ' retirement year'} at
                  an assumed growth rate, so it'll usually be noticeably lower. Save to see the real Coast number.</>
              )}
            </div>
          )}

          {saveError && <div style={{ color: RED, fontSize: 12, marginBottom: 10 }}>⚠ {saveError}</div>}

          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={handleSave} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.6 : 1 }}>
              {saving ? 'Saving…' : 'Save FIRE target'}
            </button>
            <button onClick={() => setEditing(false)} disabled={saving} style={btnSecondary}>Cancel</button>
          </div>
        </Card>
      )}
    </div>
  )
}

const btnPrimary: React.CSSProperties = {
  background: TEAL, color: '#fff', border: 'none', borderRadius: 6,
  padding: '8px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
}
const btnSecondary: React.CSSProperties = {
  background: 'transparent', color: '#8fa3b8', border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 6, padding: '8px 18px', fontSize: 13, cursor: 'pointer',
}
const linkBtn: React.CSSProperties = {
  background: 'transparent', color: TEAL, border: 'none', fontSize: 11,
  cursor: 'pointer', padding: 0, textDecoration: 'underline',
}
const fieldLabel: React.CSSProperties = {
  display: 'block', fontSize: 11, color: '#8fa3b8', marginBottom: 6,
  fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.5px',
}
const inputStyle: React.CSSProperties = {
  background: '#0f1b2d', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 6,
  color: '#e8edf2', padding: '7px 10px', fontSize: 14, width: '100%', boxSizing: 'border-box',
  fontFamily: 'DM Mono, monospace',
}
const chipStyle: React.CSSProperties = {
  border: '1px solid', borderRadius: 20, padding: '6px 14px', fontSize: 12,
  cursor: 'pointer', fontWeight: 500,
}
