import type { TooltipProps } from 'recharts'

interface Props extends TooltipProps<number, string> {}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `£${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `£${(value / 1_000).toFixed(0)}k`
  return `£${value.toLocaleString()}`
}

export function CrosshairTooltip({ active, payload, label }: Props) {
  if (!active || !payload || payload.length === 0) return null

  return (
    <div
      className="rounded-lg px-3 py-3"
      style={{
        minWidth: 160,
        background: '#243859',
        border: '1px solid rgba(14,154,173,0.4)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        pointerEvents: 'none',
      }}
    >
      <div className="font-mono mb-2" style={{ fontSize: 10, color: '#7a93a8' }}>
        {label}
      </div>
      {payload.map((entry, i) => (
        <div key={i} className="flex justify-between items-baseline gap-4 mb-1">
          <span className="flex items-center gap-1.5" style={{ fontSize: 10, color: '#8fa3b8' }}>
            <span
              className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
              style={{ background: typeof entry.color === 'string' ? entry.color : '#0e9aad' }}
            />
            {entry.name}
          </span>
          <span className="font-mono font-medium" style={{ fontSize: 12, color: '#e8edf2' }}>
            {typeof entry.value === 'number' ? formatCurrency(entry.value) : String(entry.value ?? '')}
          </span>
        </div>
      ))}
    </div>
  )
}
