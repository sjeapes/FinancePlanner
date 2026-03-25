/**
 * useAccounts.ts
 * Hooks for fetching and mutating all account types via the /api/accounts endpoints.
 *
 * Hooks:
 *   useAllAccounts()       — GET /api/accounts → AccountListResponse
 *   useUpdateAccount(type) — PUT /api/accounts/{type}/{id}
 *   useAddAccount(type)    — POST /api/accounts/{type}
 *   useDeleteAccount(type) — DELETE /api/accounts/{type}/{id}
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../client'

// ── Response shape ─────────────────────────────────────────────────────────

export interface AccountListResponse {
  savings: any[]
  investment: any[]
  pension: any[]
  property: any[]
  income: any[]
  people: any[]
  mortgages: any[]
  expenses: any[]
  life_events: any[]
}

const EMPTY_RESPONSE: AccountListResponse = {
  savings: [],
  investment: [],
  pension: [],
  property: [],
  income: [],
  people: [],
  mortgages: [],
  expenses: [],
  life_events: [],
}

// ── Query key ─────────────────────────────────────────────────────────────

export const ACCOUNTS_QUERY_KEY = ['accounts'] as const

// ── Hooks ─────────────────────────────────────────────────────────────────

/**
 * Fetches all accounts from GET /api/accounts.
 * Defaults absent fields to empty arrays for forward-compatibility.
 */
export function useAllAccounts() {
  return useQuery<AccountListResponse>({
    queryKey: ACCOUNTS_QUERY_KEY,
    queryFn: async () => {
      const res = await apiClient.get<AccountListResponse>('/accounts')
      const d = res.data
      return {
        savings: d.savings ?? [],
        investment: d.investment ?? [],
        pension: d.pension ?? [],
        property: d.property ?? [],
        income: d.income ?? [],
        people: d.people ?? [],
        mortgages: d.mortgages ?? [],
        expenses: d.expenses ?? [],
        life_events: d.life_events ?? [],
      }
    },
    placeholderData: EMPTY_RESPONSE,
  })
}

/**
 * Returns a mutation for updating an account via PUT /api/accounts/{type}/{id}.
 * @param type Account type string.
 */
export function useUpdateAccount(type: string) {
  const queryClient = useQueryClient()
  return useMutation<any, Error, { id: string; data: any }>({
    mutationFn: async ({ id, data }) => {
      const res = await apiClient.put(`/accounts/${type}/${id}`, data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY })
    },
  })
}

/**
 * Returns a mutation for adding an account via POST /api/accounts/{type}.
 * @param type Account type string.
 */
export function useAddAccount(type: string) {
  const queryClient = useQueryClient()
  return useMutation<any, Error, any>({
    mutationFn: async (data: any) => {
      const res = await apiClient.post(`/accounts/${type}`, data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY })
    },
  })
}

/**
 * Returns a mutation for deleting an account via DELETE /api/accounts/{type}/{id}.
 * @param type Account type string.
 */
export function useDeleteAccount(type: string) {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/accounts/${type}/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY })
    },
  })
}
