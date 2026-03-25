import { Play, Loader2 } from 'lucide-react'
import { format } from 'date-fns'
import { useConfigStore } from '../../store/configStore'

interface Props {
  isRunning: boolean
  lastRunAt: Date | null
  onRun: () => void
}

export function TopBar({ isRunning, lastRunAt, onRun }: Props) {
  const { activeScenarioPath, currency } = useConfigStore()

  const scenarioName = activeScenarioPath.split('/').pop()?.replace('.yaml', '') ?? 'base'

  return (
    <header
      className="flex items-center shrink-0 px-5 gap-4"
      style={{
        height: 48,
        backgroundColor: '#162236',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        zIndex: 100,
      }}
    >
      {/* Scenario pill */}
      <div
        className="flex items-center gap-2 rounded px-2.5 py-1 text-xs cursor-pointer transition-all duration-150"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.07)',
          color: '#7a93a8',
          fontSize: 11,
        }}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: '#0e9aad' }} />
        <span style={{ color: '#d4a843', fontWeight: 500 }}>{scenarioName}</span>
      </div>

      {/* Divider */}
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
      <div className="ml-auto flex items-center gap-3">
        {/* Last run */}
        {lastRunAt && (
          <span style={{ fontSize: 11, color: '#8fa3b8' }}>
            Last run:{' '}
            <span className="font-mono" style={{ color: '#e8edf2' }}>
              {format(lastRunAt, 'HH:mm:ss')}
            </span>
          </span>
        )}

        {/* Run simulation button */}
        <button
          onClick={onRun}
          disabled={isRunning}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold text-white transition-all duration-150 disabled:opacity-60 cursor-pointer disabled:cursor-not-allowed"
          style={{
            background: isRunning ? '#0b7a8a' : '#0e9aad',
            border: '1px solid transparent',
            fontSize: 11,
          }}
        >
          {isRunning ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Play size={12} />
          )}
          {isRunning ? 'Running…' : 'Run Simulation'}
        </button>
      </div>
    </header>
  )
}
