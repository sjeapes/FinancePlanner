import type { ComponentType } from 'react'
import {
  LayoutDashboard,
  TrendingUp,
  BarChart,
  PieChart,
  Database,
  Calendar,
  Scale,
  Globe,
  GitBranch,
  CheckCircle,
  Settings,
} from 'lucide-react'

type Screen =
  | 'dashboard'
  | 'timeline'
  | 'portfolio'
  | 'data'
  | 'retirement'
  | 'estate'
  | 'generational'
  | 'tax'
  | 'opportunity'
  | 'scenarios'
  | 'checkpoints'
  | 'settings'

interface NavItem {
  key: Screen
  label: string
  icon: ComponentType<{ size?: number; className?: string }>
  group: string
}

const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard',    label: 'Dashboard',          icon: LayoutDashboard, group: 'Overview' },
  { key: 'timeline',     label: 'Timeline',            icon: TrendingUp,      group: 'Overview' },
  { key: 'portfolio',    label: 'Portfolio Mix',       icon: PieChart,        group: 'Overview' },
  { key: 'data',         label: 'Data',                icon: Database,        group: 'Data' },
  { key: 'retirement',   label: 'Retirement Planner',  icon: Calendar,        group: 'Planning' },
  { key: 'estate',       label: 'Estate Planner',      icon: Scale,           group: 'Planning' },
  { key: 'generational', label: 'Generational',         icon: Globe,           group: 'Planning' },
  { key: 'tax',           label: 'Tax Optimiser',       icon: TrendingUp,      group: 'Planning' },
  { key: 'opportunity',   label: 'Fund Analyser',        icon: BarChart,       group: 'Planning' },
  { key: 'scenarios',    label: 'Scenarios',           icon: GitBranch,       group: 'Planning' },
  { key: 'checkpoints',  label: 'Checkpoints',         icon: CheckCircle,     group: 'Planning' },
  { key: 'settings',     label: 'Settings',            icon: Settings,        group: 'System' },
]

interface Props {
  currentScreen: Screen
  onNavigate: (screen: Screen) => void
}

export function Sidebar({ currentScreen, onNavigate }: Props) {
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))]

  return (
    <aside
      className="flex flex-col shrink-0 border-r overflow-y-auto"
      style={{
        width: 220,
        backgroundColor: '#162236',
        borderColor: 'rgba(255,255,255,0.07)',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center px-5 shrink-0"
        style={{ height: 48, borderBottom: '1px solid rgba(255,255,255,0.07)' }}
      >
        <span
          className="font-display font-bold text-lg tracking-tight"
          style={{ color: '#e8edf2' }}
        >
          Life<span style={{ color: '#0e9aad' }}>Ledger</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3">
        {groups.map((group) => (
          <div key={group}>
            <div
              className="px-5 pt-3 pb-1 text-xs font-semibold uppercase tracking-widest opacity-50"
              style={{ color: '#7a93a8', fontSize: 9, letterSpacing: '1.2px' }}
            >
              {group}
            </div>
            {NAV_ITEMS.filter((i) => i.group === group).map((item) => {
              const Icon = item.icon
              const isActive = currentScreen === item.key
              return (
                <button
                  key={item.key}
                  onClick={() => onNavigate(item.key)}
                  className="w-full flex items-center gap-2.5 px-5 py-2 text-sm text-left transition-all duration-150 cursor-pointer"
                  style={{
                    borderLeft: isActive ? '2px solid #0e9aad' : '2px solid transparent',
                    backgroundColor: isActive ? 'rgba(14,154,173,0.12)' : 'transparent',
                    color: isActive ? '#0e9aad' : '#8fa3b8',
                    fontWeight: isActive ? 500 : 400,
                    fontSize: 12,
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.04)'
                      e.currentTarget.style.color = '#e8edf2'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'transparent'
                      e.currentTarget.style.color = '#8fa3b8'
                    }
                  }}
                >
                  <Icon size={15} className="shrink-0 opacity-80" />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </div>
        ))}
      </nav>

      {/* Footer net worth stub */}
      <div
        className="px-5 py-4 shrink-0"
        style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}
      >
        <div
          className="uppercase tracking-wide mb-1"
          style={{ fontSize: 10, color: '#7a93a8', letterSpacing: '0.5px' }}
        >
          Net Worth
        </div>
        <div className="font-mono text-xl font-medium" style={{ color: '#e8edf2' }}>
          —
        </div>
        <div style={{ fontSize: 10, color: '#7a93a8', marginTop: 2 }}>Run a simulation</div>
      </div>
    </aside>
  )
}
