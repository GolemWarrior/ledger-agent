import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export interface Category {
  id: number
  name: string
  hint: string | null
  transaction_count: number
}

async function fetchCategories(): Promise<Category[]> {
  const res = await fetch('/api/v1/categories')
  if (!res.ok) throw new Error('Failed to fetch categories')
  const json = await res.json()
  return json.data
}

export function useCategories() {
  return useQuery({ queryKey: ['categories'], queryFn: fetchCategories })
}

async function apiRequest(input: RequestInfo, init?: RequestInit): Promise<unknown> {
  const r = await fetch(input, init)
  const json = await r.json().catch(() => null)
  if (!r.ok) throw new Error((json as { detail?: string })?.detail ?? `Request failed: ${r.status}`)
  return json
}

export function useAddCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; hint?: string }) =>
      apiRequest('/api/v1/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['categories'] }) },
  })
}

export function useRenameCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      apiRequest(`/api/v1/categories/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}

export function useDeleteCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/api/v1/categories/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['vendor-memory'] })
    },
  })
}
