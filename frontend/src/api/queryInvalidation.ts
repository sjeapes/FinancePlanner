/**
 * queryInvalidation.ts
 *
 * Almost every screen in the app (Dashboard, FIRE, Portfolio Mix, Retirement
 * Planner, Estate Planner, Tax Optimiser, Scenarios comparison, and more)
 * runs its own React Query fetch keyed on `[queryName, scenarioPath]` against
 * data derived from the same underlying scenario YAML. Editing an account,
 * person, life event, or expense via Data Management previously only
 * invalidated the `accounts` cache itself — every one of those derived views
 * kept showing whatever it had cached until its own staleTime lapsed, so the
 * app didn't visibly "refresh dynamically" after an edit.
 *
 * `invalidateScenarioDerivedQueries` is the single place that knows the full
 * set of query-name prefixes that derive from scenario data — call it from
 * any mutation's onSuccess instead of hand-picking which caches to bust.
 */

import type { QueryClient } from '@tanstack/react-query'
import { useSimulationStore } from '../store/simulationStore'

/**
 * First element of every React Query key, across the app, whose data is
 * computed from scenario YAML (accounts, people, life events, expenses,
 * income, mortgages, properties, or the FIRE target) rather than being
 * independent of it. Keep this in sync when adding a new scenario-derived
 * query elsewhere — the pattern is almost always `[name, scenarioPath]`.
 */
const SCENARIO_DERIVED_QUERY_NAMES = new Set<string>([
  'accounts',
  'scenarios',
  'scenario',
  'fire-status',
  'networth-current',
  'emergency-fund',
  'review-snapshots',
  'income-coverage',
  'drawdown-order',
  'annuity',
  'state-pension',
  'coach',
  'mc-insights',
  'price-staleness',
  'sankey',
  'estate',
  'survivor',
  'rebalancing',
  'band-fill',
  'ufpls',
  'cgt-harvest',
  'tax-optimiser-summary',
  'backtest',
  'slider-sim',
])

/**
 * @brief Invalidate every cached query derived from scenario data, and mark
 *        the current simulation timeline as stale so screens can prompt a
 *        re-run instead of silently showing projections computed from data
 *        that's since changed.
 *
 * @param queryClient  The React Query client (from useQueryClient()).
 * @return             Promise resolving once invalidated queries have
 *                      refetched — await it if you need that guarantee,
 *                      or leave it unawaited for fire-and-forget use.
 */
export async function invalidateScenarioDerivedQueries(queryClient: QueryClient): Promise<void> {
  useSimulationStore.getState().markDataChanged()
  // The full projection timeline (used for charts, FIRE-year search, income
  // coverage per year, etc.) is comparatively expensive to recompute
  // (especially the 1,000-run Monte Carlo pass), so it's never
  // auto-re-triggered here — only flagged as stale (via markDataChanged
  // above) for the UI to surface.
  await queryClient.invalidateQueries({
    predicate: (query) => SCENARIO_DERIVED_QUERY_NAMES.has(String(query.queryKey[0])),
  })
}
