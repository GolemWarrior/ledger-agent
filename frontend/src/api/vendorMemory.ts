import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export interface VendorMemoryEntry {
  id: number
  vendor: string
  category_id: number
  category_name: string
  hit_count: number
  last_used_at: string
}

async function apiRequest(input: RequestInfo, init?: RequestInit): Promise<unknown> {
  const r = await fetch(input, init)
  const json = await r.json().catch(() => null)
  if (!r.ok) throw new Error((json as { detail?: string })?.detail ?? `Request failed: ${r.status}`)
  return json
}

export function useVendorMemory() {
  return useQuery({
    queryKey: ['vendor-memory'],
    queryFn: async () => {
      const json = await apiRequest('/api/v1/vendor-memory') as { data: VendorMemoryEntry[] }
      return json.data
    },
  })
}

export function useReassignVendorMemory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, category_id }: { id: number; category_id: number }) =>
      apiRequest(`/api/v1/vendor-memory/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_id }),
      }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['vendor-memory'] }) },
  })
}

export function useDeleteVendorMemory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/api/v1/vendor-memory/${id}`, { method: 'DELETE' }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['vendor-memory'] }) },
  })
}
