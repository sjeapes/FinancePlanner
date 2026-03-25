import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../client'
import type { TaxCalculateRequest, TaxResult } from '../../types'

export function useCalculateTax() {
  return useMutation<TaxResult, Error, TaxCalculateRequest>({
    mutationFn: (body) =>
      apiClient.post<TaxResult>('/tax/calculate', body).then((r) => r.data),
  })
}
