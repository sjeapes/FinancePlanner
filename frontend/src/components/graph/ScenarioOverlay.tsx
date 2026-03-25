import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import type { YearSnapshot } from '../../types'
import { CrosshairTooltip } from './CrosshairTooltip'

interface ScenarioData {
  name: string
  data: YearSnapshot[]
}

interface Props {
  scenarios: ScenarioData[]
  height?: number
}

const COLORS = ['#0e9aad', '#d4a843', '#2dbd7e', '#a78bfa']

function fmtY(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v}`
}

export function ScenarioOverlay({ scenarios, height = 320 }: Props) {
  if (scenarios.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{ height, background: '#1d2f47', color: '#8fa3b8', fontSize: 13 }}
      >
        Select at least one scenario to compare
      </div>
    )
  }

  // Build unified year axis
  const allYears = [...new Set(scenarios.flatMap((s) => s.data.map((d) => d.year)))].sort(
    (a, b) => a - b
  )

  const chartData = allYears.map((year) => {
    const row: Record<string, number | undefined> = { year }
    scenarios.forEach((sc) => {
      const snap = sc.data.find((d) => d.year === year)
      row[sc.name] = snap?.total_net_worth
    })
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243859" vertical={false} />
        <XAxis
          dataKey="year"
          tick={{ fill: '#8fa3b8', fontSize: 11, fontFamily: 'DM Mono' }}
          axisLine={{ stroke: '#243859' }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={fmtY}
          tick={{ fill: '#8fa3b8', fontSize: 11, fontFamily: 'DM Mono' }}
          axisLine={false}
          tickLine={false}
          width={64}
        />
        <Tooltip content={<CrosshairTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: '#8fa3b8', paddingTop: 8 }}
        />
        {scenarios.map((sc, i) => (
          <Line
            key={sc.name}
            type="monotone"
            dataKey={sc.name}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
