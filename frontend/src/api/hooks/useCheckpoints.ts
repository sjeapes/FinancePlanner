import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../client'

export function useCheckpoints() {
  return useQuery<string[]>({
    queryKey: ['checkpoints'],
    queryFn: () => apiClient.get<string[]>('/checkpoints').then((r) => r.data),
  })
}

export function useCreateCheckpoint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: object) => apiClient.post('/checkpoints', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints'] }),
  })
}
