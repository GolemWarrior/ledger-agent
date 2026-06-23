import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export interface SyncStatus {
  status: 'idle' | 'processing' | 'complete' | 'error'
  processed: number
  total: number
  last_synced_at: string | null
  error: string | null
}

async function fetchSyncStatus(): Promise<{ data: SyncStatus }> {
  const res = await fetch('/api/v1/sync/status')
  if (!res.ok) throw new Error('Failed to fetch sync status')
  return res.json()
}

async function triggerSync(): Promise<void> {
  const res = await fetch('/api/v1/sync', { method: 'POST' })
  if (!res.ok && res.status !== 409) throw new Error('Failed to trigger sync')
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ['sync-status'],
    queryFn: fetchSyncStatus,
    refetchInterval: (query) =>
      query.state.data?.data?.status === 'processing' ? 2000 : false,
  })
}

export function useTriggerSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sync-status'] }),
  })
}
