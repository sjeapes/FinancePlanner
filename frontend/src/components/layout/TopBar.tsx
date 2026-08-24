import { Play, Loader2, Smartphone, Monitor } from 'lucide-react'
import { format } from 'date-fns'
import { useConfigStore } from '../../store/configStore'

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
  const { activeScenarioPath, currency } = useConfigStore()
  const scenarioName = activeScenarioPath.split('/').pop()?.replace('.yaml', '') ?? 'base'

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
      {/* Scenario pill */}
      <div
        className="flex items-center gap-2 rounded px-2.5 py-1"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.07)',
          fontSize: 11,
        }}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: '#0e9aad' }} />
        <span style={{ color: '#d4a843', fontWeight: 500 }}>{scenarioName}</span>
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
