import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { AccountBreakdown } from '../../types'

interface Props {
  accounts: AccountBreakdown
  height?: number
}

const SEGMENTS = [
  { key: 'investments_total' as const, label: 'ISA / Investments', color: '#0e9aad' },
  { key: 'pensions_total'    as const, label: 'Pension',           color: '#d4a843' },
  { key: 'property_net'     as const, label: 'Property (net)',    color: '#2dbd7e' },
  { key: 'savings_total'    as const, label: 'GIA / Savings',    color: '#a78bfa' },
  { key: 'cash_total'       as const, label: 'Cash',              color: '#8fa3b8' },
]

function fmtValue(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toLocaleString()}`
}

interface PieRow {
  name: string
  value: number
  color: string
}

export function PortfolioMix({ accounts, height = 300 }: Props) {
  const data: PieRow[] = SEGMENTS.map((seg) => ({
    name: seg.label,
    value: Math.max(0, accounts[seg.key] ?? 0),
    color: seg.color,
  })).filter((d) => d.value > 0)

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{ height, background: '#1d2f47', color: '#8fa3b8', fontSize: 13 }}
      >
        No allocation data
      </div>
    )
  }

  const total = data.reduce((s, d) => s + d.value, 0)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="45%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color} opacity={0.9} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value) => {
            const v = typeof value === 'number' ? value : 0
            return [fmtValue(v), '']
          }}
          contentStyle={{
            background: '#243859',
            border: '1px solid rgba(14,154,173,0.4)',
            borderRadius: 8,
            fontSize: 11,
            color: '#e8edf2',
            fontFamily: 'DM Mono',
          }}
        />
        <Legend
          formatter={(value: string) => {
            const item = data.find((d) => d.name === value)
            const pct = item ? ((item.value / total) * 100).toFixed(1) : '0'
            const color = item?.color ?? '#8fa3b8'
            return (
              <span style={{ fontSize: 11, color: '#8fa3b8' }}>
                <span style={{ color }}>{value}</span>
                {' '}
                <span style={{ color: '#e8edf2', fontFamily: 'DM Mono' }}>{pct}%</span>
              </span>
            )
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
