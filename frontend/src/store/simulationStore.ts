import { create } from 'zustand'
import type { TimelineResult, MonteCarloResult } from '../types'

interface SimulationStore {
  timeline: TimelineResult | null
  monteCarlo: MonteCarloResult | null
  isRunning: boolean
  lastRunAt: Date | null
  // Set whenever underlying scenario data (accounts, life events, people,
  // etc.) changes via a mutation — lets screens show a "data changed,
  // re-run to refresh projections" indicator instead of silently
  // displaying a timeline computed from stale inputs.
  dataChangedAt: Date | null
  setTimeline: (t: TimelineResult) => void
  setMonteCarlo: (mc: MonteCarloResult) => void
  setRunning: (v: boolean) => void
  markDataChanged: () => void
  reset: () => void
}

export const useSimulationStore = create<SimulationStore>((set) => ({
  timeline: null,
  monteCarlo: null,
  isRunning: false,
  lastRunAt: null,
  dataChangedAt: null,
  setTimeline: (timeline) => set({ timeline, lastRunAt: new Date() }),
  setMonteCarlo: (monteCarlo) => set({ monteCarlo }),
  setRunning: (isRunning) => set({ isRunning }),
  markDataChanged: () => set({ dataChangedAt: new Date() }),
  reset: () => set({ timeline: null, monteCarlo: null, isRunning: false, lastRunAt: null, dataChangedAt: null }),
}))
