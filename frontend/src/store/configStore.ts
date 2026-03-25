import { create } from 'zustand'

interface ConfigState {
  currency: string
  projectionStart: number
  projectionEnd: number
  inflationRate: number
  activeScenarioPath: string
}

interface ConfigActions {
  setActiveScenarioPath: (path: string) => void
  setConfig: (config: Partial<ConfigState>) => void
}

type ConfigStore = ConfigState & ConfigActions

export const useConfigStore = create<ConfigStore>((set) => ({
  currency: 'GBP',
  projectionStart: 2025,
  projectionEnd: 2075,
  inflationRate: 0.025,
  activeScenarioPath: 'data/scenarios/base.yaml',
  setActiveScenarioPath: (path) => set({ activeScenarioPath: path }),
  setConfig: (config) => set((s) => ({ ...s, ...config })),
}))
