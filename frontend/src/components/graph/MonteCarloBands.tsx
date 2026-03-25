import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import type { MonteCarloResult, TimelineResult } from '../../types'
import { CrosshairTooltip } from './CrosshairTooltip'

interface Props {
  data: MonteCarloResult
  deterministic?: TimelineResult | null
  height?: number
}

function fmtY(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v}`
}

export function MonteCarloBands({ data, deterministic, height = 320 }: Props) {
  const chartData = data.years.map((year, i) => {
    const detSnap = deterministic?.years.find((s) => s.year === year)
    return {
      year,
      p10: data.p10[i],
      p25: data.p25[i],
      p50: data.p50[i],
      p75: data.p75[i],
      p90: data.p90[i],
      deterministic: detSnap?.total_net_worth,
    }
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 16, bottom: 0 }}>
        <defs>
          <linearGradient id="mcGrad10" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0e9aad" stopOpacity={0.08} />
            <stop offset="100%" stopColor="#0e9aad" stopOpacity={0.01} />
          </linearGradient>
          <linearGradient id="mcGrad25" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0e9aad" stopOpacity={0.14} />
            <stop offset="100%" stopColor="#0e9aad" stopOpacity={0.03} />
          </linearGradient>
        </defs>
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

        {/* P10–P90 outer band */}
        <Area
          type="monotone"
          dataKey="p90"
          stroke="none"
          fill="url(#mcGrad10)"
          name="P90"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="p10"
          stroke="none"
          fill="#0f1b2d"
          name="P10"
          dot={false}
        />

        {/* P25–P75 inner band */}
        <Area
          type="monotone"
          dataKey="p75"
          stroke="none"
          fill="url(#mcGrad25)"
          name="P75"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="p25"
          stroke="none"
          fill="#0f1b2d"
          name="P25"
          dot={false}
        />

        {/* P50 median */}
        <Line
          type="monotone"
          dataKey="p50"
          stroke="#0e9aad"
          strokeWidth={2}
          dot={false}
          name="P50 (Median)"
        />

        {/* Deterministic overlay */}
        {deterministic && (
          <Line
            type="monotone"
            dataKey="deterministic"
            stroke="#d4a843"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            dot={false}
            name="Deterministic"
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
