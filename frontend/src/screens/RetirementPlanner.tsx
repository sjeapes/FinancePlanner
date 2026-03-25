import { PageHeader } from '../components/layout/PageHeader'
import { useSimulationStore } from '../store/simulationStore'
import { useScenarioStore } from '../store/scenarioStore'

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toLocaleString()}`
}

export function RetirementPlanner() {
  const { timeline } = useSimulationStore()
  const { activeScenario } = useScenarioStore()

  const fireTarget = activeScenario?.fire_target ?? null
  const fireYear = timeline?.fire_year

  const impliedTarget =
    fireTarget ? fireTarget.annual_expenses / fireTarget.swr : null

  return (
    <div>
      <PageHeader
        title="Retirement Planner"
        subtitle="FIRE & drawdown analysis"
      />

      {/* FIRE Target Card */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div
          className="rounded-xl p-5"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            FIRE Target
          </div>
          {fireTarget ? (
            <div className="space-y-3">
              {[
                { label: 'Target Net Worth',   value: fmt(fireTarget.target_net_worth), color: '#d4a843' },
                { label: 'Safe Withdrawal Rate', value: `${(fireTarget.swr * 100).toFixed(1)}%`,     color: '#0e9aad' },
                { label: 'Annual Expenses',    value: fmt(fireTarget.annual_expenses),  color: '#e8edf2' },
                { label: 'Implied Target',     value: impliedTarget ? fmt(impliedTarget) : '—', color: '#2dbd7e' },
                { label: 'FIRE Year',          value: fireYear ? String(fireYear) : 'TBD', color: '#d4a843' },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: '#8fa3b8' }}>
                    {label}
                  </span>
                  <span className="font-mono text-sm font-medium" style={{ color }}>
                    {value}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm" style={{ color: '#8fa3b8' }}>
              No FIRE target configured. Load a scenario with a fire_target.
            </p>
          )}
        </div>

        {/* Progress card */}
        <div
          className="rounded-xl p-5"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            FIRE Progress
          </div>
          {timeline && fireTarget ? (
            (() => {
              const latestSnap = timeline.years.find(
                (s) => s.year === new Date().getFullYear()
              )
              const currentNW = latestSnap?.total_net_worth ?? 0
              const progress = Math.min(100, (currentNW / fireTarget.target_net_worth) * 100)
              return (
                <div>
                  <div className="flex justify-between items-baseline mb-2">
                    <span className="text-sm" style={{ color: '#8fa3b8' }}>
                      Current / Target
                    </span>
                    <span className="font-mono text-sm" style={{ color: '#e8edf2' }}>
                      {fmt(currentNW)} / {fmt(fireTarget.target_net_worth)}
                    </span>
                  </div>
                  {/* Progress bar */}
                  <div
                    className="rounded-full overflow-hidden mb-2"
                    style={{ height: 8, background: '#243859' }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${progress}%`,
                        background: progress >= 100 ? '#2dbd7e' : '#0e9aad',
                      }}
                    />
                  </div>
                  <div className="font-mono text-2xl font-medium" style={{ color: '#d4a843' }}>
                    {progress.toFixed(1)}%
                  </div>
                  <div className="text-xs mt-1" style={{ color: '#8fa3b8' }}>
                    of FIRE target reached
                  </div>
                </div>
              )
            })()
          ) : (
            <p className="text-sm" style={{ color: '#8fa3b8' }}>
              Run a simulation to see progress
            </p>
          )}
        </div>
      </div>

      {/* Income Coverage Placeholder */}
      <div
        className="rounded-xl p-5 mb-4"
        style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
      >
        <div
          className="text-xs font-semibold uppercase tracking-wide mb-3"
          style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
        >
          Income Coverage Table
        </div>
        <p className="text-sm" style={{ color: '#8fa3b8' }}>
          Detailed income coverage analysis — Phase 4 feature. Will show pension drawdown,
          state pension, and rental income vs. expenses year by year.
        </p>
      </div>

      {/* Phase 4 note */}
      <div
        className="rounded-xl p-4 text-sm"
        style={{
          background: 'rgba(212,168,67,0.06)',
          border: '1px solid rgba(212,168,67,0.2)',
          color: '#d4a843',
        }}
      >
        Drawdown optimiser, annuity comparison, and state pension integration arrive in Phase 4.
      </div>
    </div>
  )
}
