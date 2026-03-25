import { PageHeader } from '../components/layout/PageHeader'
import { PortfolioMix } from '../components/portfolio/PortfolioMix'
import { HoldingsTable } from '../components/portfolio/HoldingsTable'
import { useSimulationStore } from '../store/simulationStore'
import { useScenarioStore } from '../store/scenarioStore'
import type { AccountBreakdown, AccountSnapshotOut } from '../types'

const EMPTY_BREAKDOWN: AccountBreakdown = {
  savings_total: 0,
  investments_total: 0,
  pensions_total: 0,
  property_net: 0,
  cash_total: 0,
}

const INVESTMENT_TYPES = new Set(['ISA', 'cash_ISA', 'LISA'])
const PENSION_TYPES = new Set(['SIPP', 'workplace_DC', 'DB'])

function computeBreakdown(accounts: Record<string, AccountSnapshotOut>): AccountBreakdown {
  const bd = { ...EMPTY_BREAKDOWN }
  for (const acc of Object.values(accounts)) {
    const v = acc.value
    const t = acc.account_type
    if (INVESTMENT_TYPES.has(t)) bd.investments_total += v
    else if (PENSION_TYPES.has(t)) bd.pensions_total += v
    else if (t === 'property' || t === 'mortgage') bd.property_net += v
    else if (t === 'GIA') bd.savings_total += v
    else bd.cash_total += v
  }
  return bd
}

export function PortfolioMixScreen() {
  const { timeline } = useSimulationStore()
  const { activeScenario } = useScenarioStore()

  // Use most recent snapshot for allocation
  const latestSnap = timeline?.years.at(-1)
  const breakdown: AccountBreakdown = latestSnap ? computeBreakdown(latestSnap.accounts) : EMPTY_BREAKDOWN

  return (
    <div>
      <PageHeader title="Portfolio Mix" subtitle="Asset allocation & holdings" />

      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Pie chart */}
        <div
          className="rounded-xl p-4"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-3"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            Asset Allocation
          </div>
          <PortfolioMix accounts={breakdown} />
        </div>

        {/* Summary */}
        <div
          className="rounded-xl p-4"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            Breakdown
          </div>
          {[
            { label: 'ISA / Investments', value: breakdown.investments_total, color: '#0e9aad' },
            { label: 'Pension',           value: breakdown.pensions_total,    color: '#d4a843' },
            { label: 'Property (net)',    value: breakdown.property_net,     color: '#2dbd7e' },
            { label: 'GIA / Savings',    value: breakdown.savings_total,    color: '#a78bfa' },
            { label: 'Cash',             value: breakdown.cash_total,       color: '#8fa3b8' },
          ].map(({ label, value, color }) => {
            const total = (Object.values(breakdown) as number[]).reduce((a, b) => a + Math.max(0, b), 0)
            const pct = total > 0 ? ((Math.max(0, value) / total) * 100).toFixed(1) : '0.0'
            return (
              <div key={label} className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: color }}
                  />
                  <span className="text-sm" style={{ color: '#8fa3b8' }}>
                    {label}
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-mono text-sm" style={{ color: '#e8edf2' }}>
                    {value >= 1_000_000
                      ? `£${(value / 1_000_000).toFixed(2)}M`
                      : `£${(value / 1_000).toFixed(0)}k`}
                  </span>
                  <span
                    className="font-mono text-xs ml-2"
                    style={{ color }}
                  >
                    {pct}%
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Holdings tables */}
      {activeScenario ? (
        activeScenario.investment_accounts.map((account) => (
          <div
            key={account.id}
            className="rounded-xl overflow-hidden mb-4"
            style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
          >
            <HoldingsTable holdings={account.holdings} accountName={account.name} />
          </div>
        ))
      ) : (
        <div
          className="rounded-xl p-6 text-center text-sm"
          style={{
            background: '#162236',
            border: '1px solid rgba(255,255,255,0.07)',
            color: '#8fa3b8',
          }}
        >
          Load a scenario to view individual holdings
        </div>
      )}
    </div>
  )
}
