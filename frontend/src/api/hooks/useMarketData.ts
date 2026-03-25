import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { SymbolResult } from '../../types'

export function useSymbolSearch(query: string) {
  return useQuery<SymbolResult[]>({
    queryKey: ['market', 'search', query],
    queryFn: () =>
      apiClient.get<SymbolResult[]>('/market-data/search', { params: { q: query } }).then((r) => r.data),
    enabled: query.length > 1,
  })
}

export function usePrice(symbol: string) {
  return useQuery<number | null>({
    queryKey: ['market', 'price', symbol],
    queryFn: () =>
      apiClient
        .get<{ price: number | null }>(`/market-data/price/${symbol}`)
        .then((r) => r.data?.price ?? null),
    enabled: !!symbol,
  })
}
