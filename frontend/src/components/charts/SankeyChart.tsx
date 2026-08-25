/**
 * SankeyChart.tsx
 * Pure-SVG two-column Sankey diagram for LifeLedger cash-flow visualisation.
 *
 * Layout
 * ------
 * Left column  — income source nodes (rectangles)
 * Right column — sink nodes: tax, NI, pension, ISA, expenses, savings
 * Between      — filled cubic bezier bands, width ∝ flow value
 *
 * No d3-sankey or external deps. All layout is computed from first principles.
 *
 * Props
 * -----
 * SankeyChartProps
 *   nodes   — SankeyNode[]  (column 0 = source, 1 = sink)
 *   links   — SankeyLink[]  (source → target with value and colour)
 *   width   — SVG width (default: container width via viewBox)
 *   height  — SVG height (default: 380)
 */

import { useState, useMemo } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SankeyNode {
  id: string
  label: string
  value: number
  colour: string
  column: number   // 0 = source, 1 = sink
  group: string
}

export interface SankeyLink {
  source: string
  target: string
  value: number
  colour: string
  label?: string
}

interface LayoutNode extends SankeyNode {
  y: number          // top edge in SVG coords
  height: number     // rectangle height in SVG coords
  consumedSrc: number  // consumed offset for outgoing links
  consumedDst: number  // consumed offset for incoming links
}

interface LayoutLink {
  source: LayoutNode
  target: LayoutNode
  value: number
  colour: string
  label: string
  srcY1: number    // top of band in source node
  srcY2: number    // bottom of band in source node
  dstY1: number    // top of band in target node
  dstY2: number    // bottom of band in target node
}

// ── Layout computation ────────────────────────────────────────────────────────

const NODE_W    = 18     // rectangle width
const GAP       = 6      // vertical gap between nodes of same column
const LABEL_PAD = 10     // gap between node and label
const MIN_H     = 2      // minimum node height so tiny flows remain visible

function computeLayout(
  nodes: SankeyNode[],
  links: SankeyLink[],
  svgH: number,
): { layoutNodes: Map<string, LayoutNode>; layoutLinks: LayoutLink[] } {
  const sources = nodes.filter(n => n.column === 0)
  const sinks   = nodes.filter(n => n.column === 1)

  const totalSrcValue = sources.reduce((s, n) => s + n.value, 0) || 1
  const totalDstValue = sinks.reduce((s,   n) => s + n.value, 0) || 1

  const usableH = svgH - Math.max(sources.length, sinks.length) * GAP

  function stackNodes(col: SankeyNode[], totalVal: number): Map<string, LayoutNode> {
    const map = new Map<string, LayoutNode>()
    let y = 0
    for (const n of col) {
      const h = Math.max(MIN_H, (n.value / totalVal) * usableH)
      map.set(n.id, {
        ...n,
        y,
        height: h,
        consumedSrc: y,
        consumedDst: y,
      })
      y += h + GAP
    }
    return map
  }

  const srcMap = stackNodes(sources, totalSrcValue)
  const dstMap = stackNodes(sinks,   totalDstValue)
  const allNodes = new Map([...srcMap, ...dstMap])

  const layoutLinks: LayoutLink[] = []
  for (const link of links) {
    const src = allNodes.get(link.source)
    const dst = allNodes.get(link.target)
    if (!src || !dst || link.value <= 0) continue

    const linkH_src = Math.max(MIN_H, (link.value / totalSrcValue) * usableH)
    const linkH_dst = Math.max(MIN_H, (link.value / totalDstValue) * usableH)

    const srcY1 = src.consumedSrc
    const srcY2 = srcY1 + linkH_src
    src.consumedSrc = srcY2

    const dstY1 = dst.consumedDst
    const dstY2 = dstY1 + linkH_dst
    dst.consumedDst = dstY2

    layoutLinks.push({
      source: src, target: dst,
      value: link.value, colour: link.colour,
      label: link.label ?? '',
      srcY1, srcY2, dstY1, dstY2,
    })
  }

  return { layoutNodes: allNodes, layoutLinks }
}

// ── Bezier path builder ───────────────────────────────────────────────────────

function makeBand(
  sx: number, sy1: number, sy2: number,
  tx: number, ty1: number, ty2: number,
): string {
  const mx = (sx + tx) / 2
  return [
    `M ${sx} ${sy1}`,
    `C ${mx} ${sy1}, ${mx} ${ty1}, ${tx} ${ty1}`,
    `L ${tx} ${ty2}`,
    `C ${mx} ${ty2}, ${mx} ${sy2}, ${sx} ${sy2}`,
    `Z`,
  ].join(' ')
}

// ── Money formatter ───────────────────────────────────────────────────────────

function fmt(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toFixed(0)}`
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  nodes: SankeyNode[]
  links: SankeyLink[]
  height?: number
  year?: number
  totalGross?: number
}

export function SankeyChart({ nodes, links, height = 380, year, totalGross }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null)

  const SVG_W   = 800
  const SVG_H   = height
  const SRC_X   = 0
  const DST_X   = SVG_W - NODE_W
  const LABEL_W = 140  // max label width on each side

  const { layoutNodes, layoutLinks } = useMemo(
    () => computeLayout(nodes, links, SVG_H - 20),
    [nodes, links, SVG_H],
  )

  function handleLinkEnter(ll: LayoutLink, e: React.MouseEvent) {
    const svgRect = (e.currentTarget as SVGElement)
      .closest('svg')?.getBoundingClientRect()
    if (!svgRect) return
    setHovered(`${ll.source.id}→${ll.target.id}`)
    setTooltip({
      x: e.clientX - svgRect.left,
      y: e.clientY - svgRect.top - 36,
      text: `${ll.source.label} → ${ll.target.label}: ${fmt(ll.value)}`,
    })
  }

  function handleNodeEnter(n: LayoutNode, e: React.MouseEvent) {
    const svgRect = (e.currentTarget as SVGElement)
      .closest('svg')?.getBoundingClientRect()
    if (!svgRect) return
    setHovered(n.id)
    setTooltip({
      x: e.clientX - svgRect.left,
      y: e.clientY - svgRect.top - 36,
      text: `${n.label}: ${fmt(n.value)}`,
    })
  }

  function handleLeave() {
    setHovered(null)
    setTooltip(null)
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Year + total badge */}
      {year && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <span style={{ color: '#8b949e', fontSize: 11 }}>
            Cash flow{year ? ` · ${year}` : ''}
          </span>
          {totalGross && (
            <span style={{ color: '#8b949e', fontSize: 11 }}>
              Total gross income:{' '}
              <span style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace' }}>
                {fmt(totalGross)}
              </span>
            </span>
          )}
        </div>
      )}

      <svg
        viewBox={`-${LABEL_W} 0 ${SVG_W + LABEL_W * 2} ${SVG_H}`}
        style={{ width: '100%', height: SVG_H, overflow: 'visible' }}
        onMouseLeave={handleLeave}
      >
        {/* ── Link bands ──────────────────────────────────────────────────── */}
        {layoutLinks.map((ll, i) => {
          const key  = `${ll.source.id}→${ll.target.id}-${i}`
          const isHov = hovered === key || hovered === ll.source.id || hovered === ll.target.id
          return (
            <path
              key={key}
              d={makeBand(
                SRC_X + NODE_W, ll.srcY1, ll.srcY2,
                DST_X,          ll.dstY1, ll.dstY2,
              )}
              fill={ll.colour}
              opacity={hovered ? (isHov ? 0.55 : 0.12) : 0.32}
              style={{ transition: 'opacity 0.15s', cursor: 'pointer' }}
              onMouseEnter={e => handleLinkEnter(ll, e)}
            />
          )
        })}

        {/* ── Source nodes ─────────────────────────────────────────────────── */}
        {Array.from(layoutNodes.values())
          .filter(n => n.column === 0)
          .map(n => (
            <g key={n.id} onMouseEnter={e => handleNodeEnter(n, e)}>
              <rect
                x={SRC_X} y={n.y} width={NODE_W} height={n.height}
                fill={n.colour}
                opacity={hovered && hovered !== n.id ? 0.45 : 1}
                rx={3}
                style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
              />
              {/* Left label */}
              <text
                x={SRC_X - LABEL_PAD}
                y={n.y + n.height / 2}
                textAnchor="end"
                dominantBaseline="middle"
                style={{ fill: '#e8edf2', fontSize: 11, fontFamily: 'DM Sans, sans-serif' }}
              >
                {n.label}
              </text>
              <text
                x={SRC_X - LABEL_PAD}
                y={n.y + n.height / 2 + 13}
                textAnchor="end"
                dominantBaseline="middle"
                style={{ fill: n.colour, fontSize: 10, fontFamily: 'DM Mono, monospace' }}
              >
                {fmt(n.value)}
              </text>
            </g>
          ))}

        {/* ── Sink nodes ───────────────────────────────────────────────────── */}
        {Array.from(layoutNodes.values())
          .filter(n => n.column === 1)
          .map(n => (
            <g key={n.id} onMouseEnter={e => handleNodeEnter(n, e)}>
              <rect
                x={DST_X} y={n.y} width={NODE_W} height={n.height}
                fill={n.colour}
                opacity={hovered && hovered !== n.id ? 0.45 : 1}
                rx={3}
                style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
              />
              {/* Right label */}
              <text
                x={DST_X + NODE_W + LABEL_PAD}
                y={n.y + n.height / 2}
                dominantBaseline="middle"
                style={{ fill: '#e8edf2', fontSize: 11, fontFamily: 'DM Sans, sans-serif' }}
              >
                {n.label}
              </text>
              <text
                x={DST_X + NODE_W + LABEL_PAD}
                y={n.y + n.height / 2 + 13}
                dominantBaseline="middle"
                style={{ fill: n.colour, fontSize: 10, fontFamily: 'DM Mono, monospace' }}
              >
                {fmt(n.value)}
              </text>
            </g>
          ))}

        {/* ── Tooltip ──────────────────────────────────────────────────────── */}
        {tooltip && (
          <g>
            <rect
              x={tooltip.x - 4} y={tooltip.y - 16}
              width={tooltip.text.length * 6.5 + 8} height={22}
              rx={4} fill="#0f1b2d" stroke="#30363d" strokeWidth={1}
            />
            <text
              x={tooltip.x} y={tooltip.y}
              style={{ fill: '#e8edf2', fontSize: 11, fontFamily: 'DM Mono, monospace' }}
            >
              {tooltip.text}
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}
