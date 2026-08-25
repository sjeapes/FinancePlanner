import { useState } from 'react'
type Screen =
  | 'dashboard' | 'timeline' | 'portfolio' | 'data'
  | 'retirement' | 'estate' | 'generational' | 'tax' | 'opportunity' | 'scenarios' | 'checkpoints' | 'settings'

interface NavItem { id: Screen; label: string; icon: string }

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard',    label: 'Home',       icon: '⌂' },
  { id: 'timeline',     label: 'Timeline',   icon: '📈' },
  { id: 'portfolio',    label: 'Portfolio',  icon: '🥧' },
  { id: 'retirement',   label: 'Retirement', icon: '🏖' },
  { id: 'estate',       label: 'Estate',     icon: '🏛' },
  { id: 'scenarios',    label: 'Scenarios',  icon: '🔀' },
]

const OVERFLOW_ITEMS: NavItem[] = [
  { id: 'data',         label: 'Data',       icon: '📋' },
  { id: 'generational', label: 'Generational', icon: '🌍' },
  { id: 'tax',          label: 'Tax Opt',    icon: '📊' },
  { id: 'opportunity',  label: 'Analyser',   icon: '📈' },
  { id: 'checkpoints',  label: 'Checks',     icon: '✓' },
  { id: 'settings',     label: 'Settings',   icon: '⚙' },
]

interface MobileNavProps {
  currentScreen: Screen
  onNavigate: (screen: Screen) => void
}

/**
 * Bottom navigation bar for mobile view.
 * Shows 5 primary screens in the nav bar + a "More" overflow sheet.
 */
export function MobileNav({ currentScreen, onNavigate }: MobileNavProps) {
  const isOverflow = OVERFLOW_ITEMS.some(i => i.id === currentScreen)

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100,
      background: '#0f1b2d',
      borderTop: '1px solid #1d2f47',
      display: 'flex',
      alignItems: 'stretch',
      height: 60,
      paddingBottom: 'env(safe-area-inset-bottom)',
    }}>
      {NAV_ITEMS.slice(0, 5).map(item => (
        <NavTab
          key={item.id}
          item={item}
          active={currentScreen === item.id}
          onClick={() => onNavigate(item.id)}
        />
      ))}
      <MoreTab
        active={isOverflow}
        currentScreen={currentScreen}
        items={OVERFLOW_ITEMS}
        onNavigate={onNavigate}
      />
    </nav>
  )
}

function NavTab({ item, active, onClick }: {
  item: NavItem; active: boolean; onClick: () => void
}) {
  return (
    <button onClick={onClick} style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: 2, border: 'none', cursor: 'pointer',
      background: 'transparent',
      color: active ? '#0e9aad' : '#8fa3b8',
      borderTop: active ? '2px solid #0e9aad' : '2px solid transparent',
      fontSize: 18, padding: '4px 0',
    }}>
      <span style={{ fontSize: 18 }}>{item.icon}</span>
      <span style={{ fontSize: 9, letterSpacing: '0.03em' }}>{item.label}</span>
    </button>
  )
}

function MoreTab({ active, currentScreen, items, onNavigate }: {
  active: boolean; currentScreen: Screen
  items: NavItem[]; onNavigate: (s: Screen) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button onClick={() => setOpen(o => !o)} style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        gap: 2, border: 'none', cursor: 'pointer',
        background: 'transparent',
        color: active ? '#0e9aad' : '#8fa3b8',
        borderTop: active ? '2px solid #0e9aad' : '2px solid transparent',
        padding: '4px 0',
      }}>
        <span style={{ fontSize: 18 }}>⋯</span>
        <span style={{ fontSize: 9, letterSpacing: '0.03em' }}>More</span>
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div onClick={() => setOpen(false)} style={{
            position: 'fixed', inset: 0, zIndex: 98, background: '#00000066',
          }} />
          {/* Sheet */}
          <div style={{
            position: 'fixed', bottom: 64, right: 0, zIndex: 99,
            background: '#162236', borderRadius: '12px 12px 0 0',
            border: '1px solid #1d2f47', padding: '12px 0', minWidth: 180,
          }}>
            {items.map(item => (
              <button key={item.id} onClick={() => { onNavigate(item.id); setOpen(false) }} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                width: '100%', padding: '12px 20px',
                border: 'none', cursor: 'pointer',
                background: currentScreen === item.id ? '#0e9aad22' : 'transparent',
                color: currentScreen === item.id ? '#0e9aad' : '#e8edf2',
                fontSize: 14,
              }}>
                <span style={{ fontSize: 18 }}>{item.icon}</span>
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </>
  )
}

