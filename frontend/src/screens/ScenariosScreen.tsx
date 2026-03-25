import { useState, useCallback } from 'react'
import { GitBranch, Plus, X, Check, TrendingUp } from 'lucide-react'
import { PageHeader } from '../components/layout/PageHeader'
import { ScenarioOverlay } from '../components/graph/ScenarioOverlay'
import { useScenarioTemplates, useScenarioComparison } from '../api/hooks/useScenarios'
import { apiClient } from '../api/client'
import type { ScenarioComparisonRow, YearSnapshot } from '../types'

// ── Constants ─────────────────────────────────────────────────────────────────

const SCENARIO_COLORS = ['#0e9aad', '#d4a843', '#2dbd7e', '#a78bfa']
const BASE_PATH = 'data/scenarios/base.yaml'
const COMPARISON_YEARS = ['2030', '2040', '2050', '2060']
const MAX_COMPARISON = 4

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtGBP(v: number | undefined): string {
  if (v === undefined || v === null) return '—'
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}k`
  return `£${v.toFixed(0)}`
}

function templateIdToPath(id: string): string {
  return `data/scenarios/templates/${id}.yaml`
}

// ── Template Card ─────────────────────────────────────────────────────────────

interface TemplateCardProps {
  id: string
  name: string
  path: string
  isSelected: boolean
  color: string
  onAdd: (path: string) => void
  onRemove: (path: string) => void
  disabled: boolean
}

function TemplateCard({
  name,
  path,
  isSelected,
  color,
  onAdd,
  onRemove,
  disabled,
}: TemplateCardProps) {
  return (
    <div
      style={{
        background: '#162236',
        border: isSelected ? `1px solid ${color}` : '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12,
        padding: '14px 16px',
        position: 'relative',
        overflow: 'hidden',
        transition: 'border-color 150ms',
      }}
    >
      {/* Top accent stripe */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: isSelected ? color : 'rgba(255,255,255,0.06)',
          borderRadius: '12px 12px 0 0',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginTop: 4 }}>
        <div style={{ flex: 1, marginRight: 8 }}>
          <div style={{ color: '#e8edf2', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
            {name}
          </div>
          <div style={{ color: '#8fa3b8', fontSize: 11, fontFamily: 'DM Mono, monospace' }}>
            {path.split('/').pop()}
          </div>
        </div>

        <button
          onClick={() => isSelected ? onRemove(path) : onAdd(path)}
          disabled={!isSelected && disabled}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '5px 10px',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 600,
            cursor: (!isSelected && disabled) ? 'not-allowed' : 'pointer',
            border: isSelected ? `1px solid ${color}` : '1px solid rgba(255,255,255,0.12)',
            background: isSelected ? `${color}22` : 'rgba(255,255,255,0.04)',
            color: isSelected ? color : '#8fa3b8',
            opacity: (!isSelected && disabled) ? 0.4 : 1,
            transition: 'all 150ms',
            whiteSpace: 'nowrap',
          }}
        >
          {isSelected ? (
            <><Check size={11} /> Added</>
          ) : (
            <><Plus size={11} /> Add</>
          )}
        </button>
      </div>
    </div>
  )
}

// ── Active Scenario Badge ─────────────────────────────────────────────────────

interface ActiveScenarioBadgeProps {
  path: string
  color: string
  isBase: boolean
  onRemove: (path: string) => void
}

function ActiveScenarioBadge({ path, color, isBase, onRemove }: ActiveScenarioBadgeProps) {
  const label = isBase ? 'Base Scenario' : path.split('/').pop()?.replace('.yaml', '') ?? path

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px 4px 8px',
        borderRadius: 20,
        background: `${color}18`,
        border: `1px solid ${color}55`,
        fontSize: 11,
        fontWeight: 600,
        color,
        whiteSpace: 'nowrap',
      }}
    >
      <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label}
      {isBase && (
        <span
          style={{
            fontSize: 9,
            padding: '1px 5px',
            borderRadius: 4,
            background: `${color}25`,
            color,
            fontFamily: 'DM Mono, monospace',
            letterSpacing: '0.5px',
          }}
        >
          BASE
        </span>
      )}
      {!isBase && (
        <button
          onClick={() => onRemove(path)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            color,
            opacity: 0.7,
          }}
        >
          <X size={10} />
        </button>
      )}
    </div>
  )
}

// ── Comparison Table ──────────────────────────────────────────────────────────

interface ComparisonTableProps {
  rows: ScenarioComparisonRow[]
  colors: string[]
}

function ComparisonTable({ rows, colors }: ComparisonTableProps) {
  if (rows.length === 0) return null

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            <th
              style={{
                textAlign: 'left',
                padding: '8px 12px',
                color: '#8fa3b8',
                fontWeight: 600,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                whiteSpace: 'nowrap',
              }}
            >
              Scenario
            </th>
            {COMPARISON_YEARS.map((yr) => (
              <th
                key={yr}
                style={{
                  textAlign: 'right',
                  padding: '8px 12px',
                  color: '#8fa3b8',
                  fontWeight: 600,
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  fontFamily: 'DM Mono, monospace',
                }}
              >
                {yr}
              </th>
            ))}
            <th
              style={{
                textAlign: 'right',
                padding: '8px 12px',
                color: '#8fa3b8',
                fontWeight: 600,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              FIRE Year
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const color = colors[i % colors.length]
            return (
              <tr
                key={row.scenario_id}
                style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
              >
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: color,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color: '#e8edf2', fontWeight: 500 }}>
                      {row.scenario_name}
                    </span>
                  </div>
                </td>
                {COMPARISON_YEARS.map((yr) => {
                  const val = row.net_worth_at_years[yr]
                  return (
                    <td
                      key={yr}
                      style={{
                        textAlign: 'right',
                        padding: '10px 12px',
                        fontFamily: 'DM Mono, monospace',
                        color: val !== undefined ? '#e8edf2' : '#8fa3b8',
                      }}
                    >
                      {fmtGBP(val)}
                    </td>
                  )
                })}
                <td
                  style={{
                    textAlign: 'right',
                    padding: '10px 12px',
                    fontFamily: 'DM Mono, monospace',
                    color: row.fire_year ? '#2dbd7e' : '#8fa3b8',
                    fontWeight: row.fire_year ? 700 : 400,
                  }}
                >
                  {row.fire_year ?? '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export function ScenariosScreen() {
  // Selected paths for comparison — always start with base
  const [selectedPaths, setSelectedPaths] = useState<string[]>([BASE_PATH])
  // Full simulation data per path (for ScenarioOverlay chart)
  const [simulationData, setSimulationData] = useState<Record<string, YearSnapshot[]>>({})
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set())

  const { data: templates = [], isLoading: templatesLoading } = useScenarioTemplates()
  const { data: comparisonRows = [], isLoading: comparisonLoading } = useScenarioComparison(selectedPaths)

  // ── Simulation fetcher (for chart overlay) ─────────────────────────────────
  const fetchSimulation = useCallback(async (path: string) => {
    if (simulationData[path] || loadingPaths.has(path)) return
    setLoadingPaths((prev) => new Set(prev).add(path))
    try {
      const res = await apiClient.post<{ years: YearSnapshot[] }>('/simulate', {
        scenario_path: path,
        include_breakdown: false,
      })
      setSimulationData((prev) => ({ ...prev, [path]: res.data.years }))
    } catch (err) {
      console.error('ScenariosScreen: simulation fetch failed for', path, err)
    } finally {
      setLoadingPaths((prev) => {
        const next = new Set(prev)
        next.delete(path)
        return next
      })
    }
  }, [simulationData, loadingPaths])

  // ── Path management ────────────────────────────────────────────────────────
  const addPath = useCallback((path: string) => {
    setSelectedPaths((prev) => {
      if (prev.includes(path) || prev.length >= MAX_COMPARISON) return prev
      fetchSimulation(path)
      return [...prev, path]
    })
  }, [fetchSimulation])

  const removePath = useCallback((path: string) => {
    if (path === BASE_PATH) return // cannot remove base
    setSelectedPaths((prev) => prev.filter((p) => p !== path))
  }, [])

  // Fetch base simulation on mount if not present
  if (!simulationData[BASE_PATH] && !loadingPaths.has(BASE_PATH)) {
    fetchSimulation(BASE_PATH)
  }

  // Build overlay data for ScenarioOverlay
  const overlayScenarios = selectedPaths
    .filter((p) => simulationData[p])
    .map((p) => ({
      name:
        comparisonRows.find((r) => r.scenario_id)
          ? (comparisonRows[selectedPaths.indexOf(p)]?.scenario_name ?? p.split('/').pop()?.replace('.yaml', '') ?? p)
          : p.split('/').pop()?.replace('.yaml', '') ?? p,
      data: simulationData[p] ?? [],
    }))

  const canAddMore = selectedPaths.length < MAX_COMPARISON

  return (
    <div>
      <PageHeader
        title="Scenarios"
        subtitle="Compare financial futures side-by-side"
      />

      {/* ── Active scenarios ──────────────────────────────────────────────── */}
      <div
        style={{
          background: '#162236',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 12,
          padding: '14px 16px',
          marginBottom: 20,
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.8px',
            color: '#8fa3b8',
            textTransform: 'uppercase',
            marginBottom: 10,
          }}
        >
          Active Comparison ({selectedPaths.length}/{MAX_COMPARISON})
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {selectedPaths.map((path, i) => (
            <ActiveScenarioBadge
              key={path}
              path={path}
              color={SCENARIO_COLORS[i % SCENARIO_COLORS.length]}
              isBase={path === BASE_PATH}
              onRemove={removePath}
            />
          ))}
          {!canAddMore && (
            <span style={{ fontSize: 11, color: '#8fa3b8', alignSelf: 'center' }}>
              Maximum {MAX_COMPARISON} scenarios
            </span>
          )}
        </div>
      </div>

      {/* ── Template gallery ──────────────────────────────────────────────── */}
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.8px',
          color: '#8fa3b8',
          textTransform: 'uppercase',
          marginBottom: 12,
        }}
      >
        Template Gallery
      </div>

      {templatesLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 24 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              style={{
                background: '#162236',
                border: '1px solid rgba(255,255,255,0.07)',
                borderRadius: 12,
                height: 72,
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          ))}
        </div>
      ) : templates.length === 0 ? (
        <div
          style={{
            background: '#162236',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 12,
            padding: 32,
            textAlign: 'center',
            color: '#8fa3b8',
            fontSize: 13,
            marginBottom: 24,
          }}
        >
          <GitBranch size={28} style={{ opacity: 0.3, marginBottom: 8 }} />
          <div>No templates found in{' '}
            <code style={{ fontFamily: 'DM Mono, monospace', color: '#0e9aad', fontSize: 12 }}>
              data/scenarios/templates/
            </code>
          </div>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
            marginBottom: 24,
          }}
        >
          {templates.map((tmpl) => {
            const path = templateIdToPath(tmpl.id)
            const isSelected = selectedPaths.includes(path)
            const colorIdx = isSelected
              ? selectedPaths.indexOf(path)
              : (selectedPaths.length) % SCENARIO_COLORS.length
            return (
              <TemplateCard
                key={tmpl.id}
                id={tmpl.id}
                name={tmpl.name}
                path={tmpl.path}
                isSelected={isSelected}
                color={SCENARIO_COLORS[colorIdx % SCENARIO_COLORS.length]}
                onAdd={addPath}
                onRemove={removePath}
                disabled={!canAddMore}
              />
            )
          })}
        </div>
      )}

      {/* ── Comparison chart ──────────────────────────────────────────────── */}
      {selectedPaths.length >= 1 && (
        <div
          style={{
            background: '#162236',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 12,
            padding: '16px',
            marginBottom: 20,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 16,
            }}
          >
            <TrendingUp size={14} style={{ color: '#0e9aad' }} />
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.8px',
                color: '#8fa3b8',
                textTransform: 'uppercase',
              }}
            >
              Net Worth Timeline
            </span>
            {loadingPaths.size > 0 && (
              <span style={{ fontSize: 10, color: '#8fa3b8', marginLeft: 4 }}>
                (loading…)
              </span>
            )}
          </div>

          {overlayScenarios.length === 0 ? (
            <div
              style={{
                height: 280,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: '#1d2f47',
                borderRadius: 8,
                color: '#8fa3b8',
                fontSize: 12,
              }}
            >
              {loadingPaths.size > 0 ? 'Running projections…' : 'Select scenarios to view chart'}
            </div>
          ) : (
            <ScenarioOverlay scenarios={overlayScenarios} height={280} />
          )}
        </div>
      )}

      {/* ── Comparison table ──────────────────────────────────────────────── */}
      {selectedPaths.length >= 1 && (
        <div
          style={{
            background: '#162236',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 12,
            padding: '16px',
            marginBottom: 20,
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.8px',
              color: '#8fa3b8',
              textTransform: 'uppercase',
              marginBottom: 14,
            }}
          >
            Key Metrics Comparison
          </div>

          {comparisonLoading ? (
            <div style={{ color: '#8fa3b8', fontSize: 12, padding: '8px 0' }}>
              Computing projections…
            </div>
          ) : comparisonRows.length === 0 ? (
            <div style={{ color: '#8fa3b8', fontSize: 12, padding: '8px 0' }}>
              No comparison data yet — select at least one scenario.
            </div>
          ) : (
            <ComparisonTable rows={comparisonRows} colors={SCENARIO_COLORS} />
          )}
        </div>
      )}

      {/* ── Empty state (no templates AND no base sim) ────────────────────── */}
      {templates.length === 0 && !templatesLoading && selectedPaths.length === 1 && (
        <div
          style={{
            background: '#162236',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 12,
            padding: 40,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
          }}
        >
          <GitBranch size={36} style={{ opacity: 0.3, color: '#8fa3b8', marginBottom: 12 }} />
          <p style={{ color: '#8fa3b8', fontSize: 13 }}>
            Add scenario templates to{' '}
            <code style={{ fontFamily: 'DM Mono, monospace', color: '#0e9aad' }}>
              data/scenarios/templates/
            </code>{' '}
            to compare financial futures.
          </p>
        </div>
      )}
    </div>
  )
}
