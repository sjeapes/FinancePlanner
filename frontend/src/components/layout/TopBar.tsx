import { Play, Loader2, Smartphone, Monitor, ChevronDown } from 'lucide-react'
import { format } from 'date-fns'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useConfigStore } from '../../store/configStore'
import { useSimulationStore } from '../../store/simulationStore'
import { apiClient } from '../../api/client'

interface ScenarioListItem {
  name: string
  path: string
  display_name?: string
  is_base?: boolean
}

interface Props {
  isRunning: boolean
  lastRunAt: Date | null
  onRun: () => void
  isMobile?: boolean
  isManualOverride?: boolean
  onToggleMobileView?: () => void
}

export function TopBar({
  isRunning, lastRunAt, onRun,
  isMobile = false, isManualOverride = false, onToggleMobileView,
}: Props) {
  const { activeScenarioPath, setActiveScenarioPath, currency } = useConfigStore()
  const resetSimulation = useSimulationStore(s => s.reset)
  const scenarioName = activeScenarioPath.split('/').pop()?.replace('.yaml', '') ?? 'base'
  const [pickerOpen, setPickerOpen] = useState(false)

  const { data: scenarioList = [] } = useQuery<ScenarioListItem[]>({
    queryKey: ['scenarios-list'],
    queryFn: () => apiClient.get('/scenarios').then(r => r.data),
    staleTime: 30_000,
  })

  function switchScenario(path: string) {
    if (path === activeScenarioPath) { setPickerOpen(false); return }
    // The old timeline/Monte Carlo results belong to a DIFFERENT scenario
    // entirely — showing them under the new one would be actively
    // misleading (not just stale), so clear rather than just flag stale.
    resetSimulation()
    setActiveScenarioPath(path)
    setPickerOpen(false)
  }

  return (
    <header
      className="flex items-center shrink-0 px-4 gap-3"
      style={{
        height: 48,
        backgroundColor: '#162236',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        zIndex: 100,
      }}
    >
      {/* Scenario pill — click to switch which scenario is active everywhere */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setPickerOpen(v => !v)}
          className="flex items-center gap-2 rounded px-2.5 py-1"
          style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.07)',
            fontSize: 11, cursor: 'pointer',
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: '#0e9aad' }} />
          <span style={{ color: '#d4a843', fontWeight: 500 }}>{scenarioName}</span>
          <ChevronDown size={11} style={{ color: '#8fa3b8' }} />
        </button>
        {pickerOpen && (
          <>
            <div onClick={() => setPickerOpen(false)}
                 style={{ position: 'fixed', inset: 0, zIndex: 200 }} />
            <div style={{
              position: 'absolute', top: '100%', left: 0, marginTop: 4,
              background: '#162236', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8, minWidth: 200, zIndex: 201,
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)', overflow: 'hidden',
            }}>
              {scenarioList.length === 0 && (
                <div style={{ padding: '10px 14px', fontSize: 11, color: '#8fa3b8' }}>Loading…</div>
              )}
              {scenarioList.map(s => (
                <button
                  key={s.path}
                  onClick={() => switchScenario(s.path)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    width: '100%', textAlign: 'left', padding: '8px 14px', fontSize: 12,
                    background: s.path === activeScenarioPath ? 'rgba(14,154,173,0.12)' : 'transparent',
                    color: s.path === activeScenarioPath ? '#0e9aad' : '#e8edf2',
                    border: 'none', cursor: 'pointer',
                  }}
                >
                  <span>{s.display_name || s.name}</span>
                  {s.is_base && (
                    <span style={{ fontSize: 9, color: '#8fa3b8', marginLeft: 8 }}>base</span>
                  )}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="w-px h-5" style={{ background: 'rgba(255,255,255,0.07)' }} />

      {/* Currency badge */}
      <span
        className="font-mono text-xs px-2 py-0.5 rounded"
        style={{
          background: 'rgba(14,154,173,0.12)',
          color: '#0e9aad',
          border: '1px solid rgba(14,154,173,0.25)',
          fontSize: 10,
        }}
      >
        {currency}
      </span>

      {/* Spacer */}
      <div className="ml-auto flex items-center gap-2">
        {/* Last run — hide on mobile to save space */}
        {lastRunAt && !isMobile && (
          <span style={{ fontSize: 11, color: '#8fa3b8' }}>
            Last run:{' '}
            <span className="font-mono" style={{ color: '#e8edf2' }}>
              {format(lastRunAt, 'HH:mm:ss')}
            </span>
          </span>
        )}

        {/* Mobile / Desktop toggle button */}
        {onToggleMobileView && (
          <button
            onClick={onToggleMobileView}
            title={isMobile ? 'Switch to desktop view' : 'Switch to mobile view'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 30, height: 30, borderRadius: 6,
              border: `1px solid ${isManualOverride ? '#0e9aad44' : 'rgba(255,255,255,0.07)'}`,
              background: isManualOverride ? 'rgba(14,154,173,0.12)' : 'rgba(255,255,255,0.04)',
              cursor: 'pointer', color: isManualOverride ? '#0e9aad' : '#8fa3b8',
            }}
          >
            {isMobile
              ? <Monitor size={14} />
              : <Smartphone size={14} />}
          </button>
        )}

        {/* Run simulation button */}
        <button
          onClick={onRun}
          disabled={isRunning}
          className="flex items-center gap-1.5 rounded px-3 py-1.5"
          style={{
            background: isRunning ? 'rgba(14,154,173,0.15)' : '#0e9aad',
            border: 'none', cursor: isRunning ? 'not-allowed' : 'pointer',
            color: '#fff', fontSize: 12, fontWeight: 600,
            opacity: isRunning ? 0.7 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {isRunning
            ? <Loader2 size={13} className="animate-spin" />
            : <Play size={13} />}
          {!isMobile && (isRunning ? 'Running…' : 'Run')}
        </button>
      </div>
    </header>
  )
}
