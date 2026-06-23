import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSyncStatus, useTriggerSync } from '../api/sync'

export default function SyncStatus() {
  const queryClient = useQueryClient()
  const status = useSyncStatus()
  const trigger = useTriggerSync()
  const prevStatus = useRef<string | undefined>(undefined)

  useEffect(() => {
    const current = status.data?.data?.status
    if (prevStatus.current === 'processing' && current === 'complete') {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
    }
    prevStatus.current = current
  }, [status.data?.data?.status, queryClient])

  const syncData = status.data?.data
  const isProcessing = syncData?.status === 'processing' || trigger.isPending
  const hasError = syncData?.status === 'error'

  function formatLastSynced(iso: string | null | undefined): string {
    if (!iso) return 'Never synced'
    return new Date(iso).toLocaleString()
  }

  return (
    <div className="flex items-center gap-3">
      {hasError && (
        <span className="text-xs text-red-600 max-w-xs truncate" title={syncData?.error ?? ''}>
          Sync error: {syncData?.error ?? 'Unknown error'}
        </span>
      )}
      {!hasError && (
        <span className="text-xs text-gray-500">
          {isProcessing
            ? `Syncing… ${syncData?.processed ?? 0}/${syncData?.total ?? 0}`
            : `Last synced: ${formatLastSynced(syncData?.last_synced_at)}`}
        </span>
      )}
      <button
        onClick={() => trigger.mutate()}
        disabled={isProcessing}
        className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isProcessing ? 'Syncing…' : 'Sync'}
      </button>
    </div>
  )
}
