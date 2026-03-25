import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts'
import type { YearSnapshot } from '../../types'
import { CrosshairTooltip } from './CrosshairTooltip'

interface Props {
  data: YearSnapshot[]
  fireYear?: number | null
  height?: number
}

function fmtY(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v}`
}

interface ChartRow {
  year: number
  pre_fire?: number
  post_fire?: number
}

export function TimelineChart({ data, fireYear, height = 320 }: Props) {
  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{ height, background: '#1d2f47', color: '#8fa3b8', fontSize: 13 }}
      >
        No simulation data — click Run Simulation
      </div>
    )
  }

  const hasPostFire = fireYear != null && data.some((d) => d.year >= fireYear)

  const chartData: ChartRow[] = data.map((snap) => ({
    year: snap.year,
    pre_fire:
      fireYear == null || snap.year <= fireYear ? snap.total_net_worth : undefined,
    post_fire:
      fireYear != null && snap.year >= fireYear ? snap.total_net_worth : undefined,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 16, bottom: 0 }}>
        <defs>
          <linearGradient id="tealGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0e9aad" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#0e9aad" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="goldGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#d4a843" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#d4a843" stopOpacity={0.02} />
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

        {/* Pre-FIRE area (solid teal line) */}
        <Area
          type="monotone"
          dataKey="pre_fire"
          name="Net Worth"
          stroke="#0e9aad"
          strokeWidth={2}
          fill="url(#tealGradient)"
          connectNulls={false}
          dot={false}
          activeDot={{ r: 4, fill: '#0e9aad', strokeWidth: 0 }}
        />

        {/* Post-FIRE area (dashed gold line) */}
        {hasPostFire && (
          <Area
            type="monotone"
            dataKey="post_fire"
            name="Net Worth (post-FIRE)"
            stroke="#d4a843"
            strokeWidth={2}
            strokeDasharray="6 3"
            fill="url(#goldGradient)"
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4, fill: '#d4a843', strokeWidth: 0 }}
          />
        )}

        {/* FIRE reference line */}
        {fireYear != null && (
          <ReferenceLine
            x={fireYear}
            stroke="#d4a843"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            label={{
              value: 'FIRE',
              position: 'top',
              fill: '#d4a843',
              fontSize: 10,
              fontFamily: 'DM Mono',
            }}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}
