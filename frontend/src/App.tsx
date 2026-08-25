import { useState } from 'react'
import type { ComponentType } from 'react'
import { Sidebar } from './components/layout/Sidebar'
import { TopBar } from './components/layout/TopBar'
import { MobileNav } from './components/layout/MobileNav'
import { Dashboard } from './screens/Dashboard'
import { TimelineGraph } from './screens/TimelineGraph'
import { PortfolioMixScreen } from './screens/PortfolioMixScreen'
import { RetirementPlanner } from './screens/RetirementPlanner'
import { EstatePlanner } from './screens/EstatePlanner'
import { GenerationalPlanning } from './screens/GenerationalPlanning'
import { TaxOptimiser } from './screens/TaxOptimiser'
import { OpportunityAnalyser } from './screens/OpportunityAnalyser'
import { ScenariosScreen } from './screens/ScenariosScreen'
import { CheckpointsScreen } from './screens/CheckpointsScreen'
import { Settings } from './screens/Settings'
import { DataManagement } from './screens/DataManagement'
import { useSimulate, useMonteCarlo } from './api/hooks/useSimulation'
import { useSimulationStore } from './store/simulationStore'
import { useConfigStore } from './store/configStore'
import { useMobileView } from './hooks/useMobileView'

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

const SCREEN_COMPONENTS: Record<Screen, ComponentType> = {
  dashboard:   Dashboard,
  timeline:    TimelineGraph,
  portfolio:   PortfolioMixScreen,
  data:        DataManagement,
  retirement:  RetirementPlanner,
  estate:      EstatePlanner,
  generational: GenerationalPlanning,
  tax:           TaxOptimiser,
  opportunity:   OpportunityAnalyser,
  scenarios:   ScenariosScreen,
  checkpoints: CheckpointsScreen,
  settings:    Settings,
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('dashboard')
  const { setTimeline, setMonteCarlo, setRunning, isRunning, lastRunAt } = useSimulationStore()
  const { activeScenarioPath } = useConfigStore()
  const simulate   = useSimulate()
  const monteCarlo = useMonteCarlo()
  const { isMobile, isManualOverride, toggleMobileView } = useMobileView()

  async function handleRunSimulation() {
    setRunning(true)
    try {
      const [tl, mc] = await Promise.all([
        simulate.mutateAsync({ scenario_path: activeScenarioPath }),
        monteCarlo.mutateAsync({ scenario_path: activeScenarioPath, n_simulations: 1000 }),
      ])
      setTimeline(tl)
      setMonteCarlo(mc)
    } catch (e) {
      console.error('Simulation failed', e)
    } finally {
      setRunning(false)
    }
  }

  const ScreenComponent = SCREEN_COMPONENTS[screen]

  // ── Mobile layout ─────────────────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh',
                    background: '#0f1b2d', overflow: 'hidden' }}>
        <TopBar
          isRunning={isRunning}
          lastRunAt={lastRunAt}
          onRun={handleRunSimulation}
          isMobile={true}
          isManualOverride={isManualOverride}
          onToggleMobileView={toggleMobileView}
        />
        <main style={{
          flex: 1, overflowY: 'auto',
          padding: '16px 16px 0',
          paddingBottom: 'calc(60px + env(safe-area-inset-bottom) + 16px)',
          background: '#0f1b2d',
        }}>
          <ScreenComponent />
        </main>
        <MobileNav
          currentScreen={screen}
          onNavigate={s => setScreen(s as Screen)}
        />
      </div>
    )
  }

  // ── Desktop layout ────────────────────────────────────────────────────────
  return (
    <div className="flex overflow-hidden" style={{ height: '100vh', background: '#0f1b2d' }}>
      <Sidebar currentScreen={screen} onNavigate={s => setScreen(s as Screen)} />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar
          isRunning={isRunning}
          lastRunAt={lastRunAt}
          onRun={handleRunSimulation}
          isMobile={false}
          isManualOverride={isManualOverride}
          onToggleMobileView={toggleMobileView}
        />
        <main className="flex-1 overflow-y-auto p-6" style={{ background: '#0f1b2d' }}>
          <ScreenComponent />
        </main>
      </div>
    </div>
  )
}
