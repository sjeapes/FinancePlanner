import { useSimulationStore } from '../store/simulationStore'
import { useConfigStore } from '../store/configStore'
import { PageHeader } from '../components/layout/PageHeader'
import { TimelineChart } from '../components/graph/TimelineChart'

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toLocaleString()}`
}

interface KpiCardProps {
  label: string
  value: string
  sub?: string
  accent?: 'teal' | 'gold' | 'green' | 'red'
}

const ACCENT_COLORS = {
  teal:  { top: '#0e9aad', value: '#0e9aad' },
  gold:  { top: '#d4a843', value: '#d4a843' },
  green: { top: '#2dbd7e', value: '#2dbd7e' },
  red:   { top: '#e05252', value: '#e05252' },
}

function KpiCard({ label, value, sub, accent = 'teal' }: KpiCardProps) {
  const colors = ACCENT_COLORS[accent]
  return (
    <div
      className="rounded-xl p-4 relative overflow-hidden"
      style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0"
        style={{ height: 2, background: colors.top }}
      />
      <div
        className="text-xs font-semibold uppercase tracking-wide mb-2"
        style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
      >
        {label}
      </div>
      <div className="font-mono text-2xl font-medium" style={{ color: colors.value }}>
        {value}
      </div>
      {sub && (
        <div className="mt-1.5 text-xs" style={{ color: '#8fa3b8' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function SkeletonCard() {
  return (
    <div
      className="rounded-xl p-4 animate-pulse"
      style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
    >
      <div className="h-2 w-24 rounded mb-3" style={{ background: '#243859' }} />
      <div className="h-8 w-32 rounded" style={{ background: '#243859' }} />
    </div>
  )
}

export function Dashboard() {
  const { timeline, monteCarlo, isRunning } = useSimulationStore()
  const { activeScenarioPath } = useConfigStore()

  const scenarioName = activeScenarioPath.split('/').pop()?.replace('.yaml', '') ?? 'base'

  // Latest snapshot
  const latestSnap = timeline?.years.at(-1)
  const fireYear = timeline?.fire_year
  const currentYear = new Date().getFullYear()
  const yearsToFire = fireYear ? fireYear - currentYear : null
  const mcProb = monteCarlo ? `${(monteCarlo.prob_fire * 100).toFixed(0)}%` : '—'

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={`Scenario: ${scenarioName}`}
      />

      {/* KPI Grid */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {isRunning ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <KpiCard
              label="Current Net Worth"
              value={latestSnap ? fmt(latestSnap.total_net_worth) : '—'}
              sub={latestSnap ? `as of ${latestSnap.year}` : 'Run a simulation'}
              accent="teal"
            />
            <KpiCard
              label="FIRE Year"
              value={fireYear ? String(fireYear) : '—'}
              sub={yearsToFire !== null ? `${yearsToFire} years away` : 'Not yet projected'}
              accent="gold"
            />
            <KpiCard
              label="Years to FIRE"
              value={yearsToFire !== null ? String(yearsToFire) : '—'}
              sub={fireYear ? `Target: ${fireYear}` : 'Run a simulation'}
              accent="green"
            />
            <KpiCard
              label="MC FIRE Probability"
              value={mcProb}
              sub={monteCarlo ? '1,000 simulations' : 'Run Monte Carlo'}
              accent={
                monteCarlo
                  ? monteCarlo.prob_fire >= 0.9
                    ? 'green'
                    : monteCarlo.prob_fire >= 0.7
                      ? 'gold'
                      : 'red'
                  : 'teal'
              }
            />
          </>
        )}
      </div>

      {/* Timeline Chart */}
      <div
        className="rounded-xl p-4"
        style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
      >
        <div
          className="text-xs font-semibold uppercase tracking-wide mb-4"
          style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
        >
          Net Worth Timeline
        </div>
        {isRunning ? (
          <div
            className="rounded-lg flex items-center justify-center animate-pulse"
            style={{ height: 320, background: '#1d2f47' }}
          >
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>Simulating…</span>
          </div>
        ) : (
          <TimelineChart
            data={timeline?.years ?? []}
            fireYear={timeline?.fire_year}
          />
        )}
      </div>

      {/* CTA when no data */}
      {!timeline && !isRunning && (
        <div
          className="mt-4 rounded-xl p-6 text-center"
          style={{
            background: 'rgba(14,154,173,0.08)',
            border: '1px solid rgba(14,154,173,0.25)',
          }}
        >
          <p className="text-sm mb-1" style={{ color: '#e8edf2' }}>
            No simulation data yet
          </p>
          <p className="text-xs" style={{ color: '#8fa3b8' }}>
            Click <strong style={{ color: '#0e9aad' }}>Run Simulation</strong> in the top bar to
            generate a 50-year projection for the <em>{scenarioName}</em> scenario.
          </p>
        </div>
      )}
    </div>
  )
}
