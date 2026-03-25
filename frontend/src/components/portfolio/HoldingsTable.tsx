import type { InvestmentHolding } from '../../types'

interface Props {
  holdings: InvestmentHolding[]
  accountName?: string
}

function fmt(v: number | null): string {
  if (v === null || v === undefined) return '—'
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(1)}k`
  return `£${v.toLocaleString()}`
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

function getValue(h: InvestmentHolding): number | null {
  if (h.total_value !== null) return h.total_value
  if (h.units !== null && h.price_per_unit !== null) return h.units * h.price_per_unit
  return null
}

export function HoldingsTable({ holdings, accountName }: Props) {
  if (holdings.length === 0) {
    return (
      <div
        className="px-4 py-6 text-center rounded-lg"
        style={{ background: '#1d2f47', color: '#8fa3b8', fontSize: 12 }}
      >
        No holdings
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      {accountName && (
        <div
          className="px-3 py-2 text-xs font-semibold uppercase tracking-wide"
          style={{ color: '#8fa3b8', borderBottom: '1px solid #243859' }}
        >
          {accountName}
        </div>
      )}
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {['Name', 'Ticker', 'Value', 'Growth Rate'].map((col) => (
              <th
                key={col}
                className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wide"
                style={{ color: '#8fa3b8', borderBottom: '1px solid #243859', letterSpacing: '0.8px' }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h, i) => (
            <tr
              key={h.id}
              style={{ backgroundColor: i % 2 === 0 ? '#162236' : '#1d2f47' }}
              className="transition-colors"
            >
              <td className="px-3 py-2.5 text-sm" style={{ color: '#e8edf2' }}>
                {h.name}
              </td>
              <td className="px-3 py-2.5">
                {h.ticker ? (
                  <span
                    className="font-mono text-xs px-2 py-0.5 rounded"
                    style={{
                      color: '#0e9aad',
                      background: 'rgba(14,154,173,0.12)',
                      border: '1px solid rgba(14,154,173,0.2)',
                    }}
                  >
                    {h.ticker}
                  </span>
                ) : (
                  <span style={{ color: '#8fa3b8', fontSize: 11 }}>—</span>
                )}
              </td>
              <td className="px-3 py-2.5 font-mono text-sm" style={{ color: '#e8edf2' }}>
                {fmt(getValue(h))}
              </td>
              <td className="px-3 py-2.5 font-mono text-sm" style={{ color: '#2dbd7e' }}>
                {fmtPct(h.assumed_growth_rate)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
