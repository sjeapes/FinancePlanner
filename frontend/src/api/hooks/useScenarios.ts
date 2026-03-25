import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { Scenario, ScenarioTemplate, ScenarioComparisonRow } from '../../types'

// ── Existing hooks ────────────────────────────────────────────────────────────

export function useScenarios() {
  return useQuery<string[]>({
    queryKey: ['scenarios'],
    queryFn: () => apiClient.get<string[]>('/scenarios').then((r) => r.data),
  })
}

export function useScenario(name: string) {
  return useQuery<Scenario>({
    queryKey: ['scenario', name],
    queryFn: () => apiClient.get<Scenario>(`/scenarios/${name}`).then((r) => r.data),
    enabled: !!name,
  })
}

export function useCompareScenarios(names: string[]) {
  return useQuery({
    queryKey: ['scenarios', 'compare', names],
    queryFn: () =>
      apiClient
        .get('/scenarios/compare', { params: { scenarios: names.join(',') } })
        .then((r) => r.data),
    enabled: names.length > 1,
  })
}

export function useDeleteScenario() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (name) => apiClient.delete(`/scenarios/${name}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenarios'] }),
  })
}

// ── Phase 3 hooks ─────────────────────────────────────────────────────────────

/**
 * Fetches all scenario template YAML files from the templates gallery.
 * Returns a list of { id, name, path } objects.
 */
export function useScenarioTemplates() {
  return useQuery<ScenarioTemplate[]>({
    queryKey: ['scenarios', 'templates'],
    queryFn: () =>
      apiClient.get<ScenarioTemplate[]>('/scenarios/templates').then((r) => r.data),
    staleTime: 60_000, // templates rarely change — cache for 1 minute
  })
}

/**
 * Runs projections for multiple scenario YAML paths and returns comparison rows.
 * Each row contains: scenario_id, scenario_name, fire_year, net_worth_at_years.
 *
 * @param paths - Array of relative YAML paths (e.g. ['data/scenarios/base.yaml'])
 */
export function useScenarioComparison(paths: string[]) {
  return useQuery<ScenarioComparisonRow[]>({
    queryKey: ['scenarios', 'compare_v2', paths],
    queryFn: () =>
      apiClient
        .get<ScenarioComparisonRow[]>('/scenarios/compare_v2', {
          params: { paths: paths.join(',') },
        })
        .then((r) => r.data),
    enabled: paths.length >= 1,
    staleTime: 30_000,
  })
}
