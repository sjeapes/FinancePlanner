import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { SimulateRequest, MonteCarloRequest, TimelineResult, MonteCarloResult } from '../../types'

export function useSimulate() {
  return useMutation<TimelineResult, Error, SimulateRequest>({
    mutationFn: (body) => apiClient.post<TimelineResult>('/simulate', body).then((r) => r.data),
  })
}

export function useMonteCarlo() {
  return useMutation<MonteCarloResult, Error, MonteCarloRequest>({
    mutationFn: (body) =>
      apiClient.post<MonteCarloResult>('/simulate/monte-carlo', body).then((r) => r.data),
  })
}
