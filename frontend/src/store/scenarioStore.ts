import { create } from 'zustand'
import type { Scenario } from '../types'

interface ScenarioStore {
  scenarios: string[]
  activeScenario: Scenario | null
  comparisonScenarios: string[]
  setScenarios: (s: string[]) => void
  setActiveScenario: (s: Scenario | null) => void
  toggleComparison: (name: string) => void
}

export const useScenarioStore = create<ScenarioStore>((set) => ({
  scenarios: [],
  activeScenario: null,
  comparisonScenarios: [],
  setScenarios: (scenarios) => set({ scenarios }),
  setActiveScenario: (activeScenario) => set({ activeScenario }),
  toggleComparison: (name) =>
    set((s) => ({
      comparisonScenarios: s.comparisonScenarios.includes(name)
        ? s.comparisonScenarios.filter((n) => n !== name)
        : s.comparisonScenarios.length < 4
          ? [...s.comparisonScenarios, name]
          : s.comparisonScenarios,
    })),
}))
