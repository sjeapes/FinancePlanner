import { create } from 'zustand'
import type { TimelineResult, MonteCarloResult } from '../types'

interface SimulationStore {
  timeline: TimelineResult | null
  monteCarlo: MonteCarloResult | null
  isRunning: boolean
  lastRunAt: Date | null
  setTimeline: (t: TimelineResult) => void
  setMonteCarlo: (mc: MonteCarloResult) => void
  setRunning: (v: boolean) => void
  reset: () => void
}

export const useSimulationStore = create<SimulationStore>((set) => ({
  timeline: null,
  monteCarlo: null,
  isRunning: false,
  lastRunAt: null,
  setTimeline: (timeline) => set({ timeline, lastRunAt: new Date() }),
  setMonteCarlo: (monteCarlo) => set({ monteCarlo }),
  setRunning: (isRunning) => set({ isRunning }),
  reset: () => set({ timeline: null, monteCarlo: null, isRunning: false, lastRunAt: null }),
}))
