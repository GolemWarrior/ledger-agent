import { useState } from 'react'
import { useCategories } from '../api/categories'
import { useDeleteVendorMemory, useReassignVendorMemory, useVendorMemory } from '../api/vendorMemory'

export default function VendorMemory() {
  const { data: entries, isLoading, isError } = useVendorMemory()
  const { data: categories } = useCategories()
  const reassignCategory = useReassignVendorMemory()
  const deleteVendorMemory = useDeleteVendorMemory()

  const [reassigningId, setReassigningId] = useState<number | null>(null)
  const [reassignCategoryId, setReassignCategoryId] = useState<number>(0)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  function handleReassignStart(id: number, currentCategoryId: number) {
    setReassigningId(id)
    setReassignCategoryId(currentCategoryId)
    setDeletingId(null)
  }

  function handleReassignSave() {
    if (!reassigningId) return
    const capturedId = reassigningId
    reassignCategory.mutate(
      { id: capturedId, category_id: reassignCategoryId },
      { onSuccess: () => setReassigningId(prev => prev === capturedId ? null : prev) }
    )
  }

  function handleDeleteStart(id: number) {
    setDeletingId(id)
    setReassigningId(null)
  }

  function handleDeleteConfirm(id: number) {
    deleteVendorMemory.mutate(id, { onSuccess: () => setDeletingId(null) })
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Vendor Memory</h1>

      {isLoading && <p className="text-gray-500">Loading vendor memory…</p>}
      {isError && <p className="text-red-600">Failed to load vendor memory.</p>}

      {entries && (
        <>
          {reassignCategory.isError && (
            <p className="text-red-600 text-xs mb-3">Failed to reassign category.</p>
          )}
          {deleteVendorMemory.isError && (
            <p className="text-red-600 text-xs mb-3">Failed to delete vendor memory entry.</p>
          )}
          {entries.length === 0 ? (
            <p className="text-gray-500">No vendor memory entries found.</p>
          ) : (
            <table className="w-full text-sm text-left">
              <thead>
                <tr>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Vendor</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Category</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Hit Count</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Last Used</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Actions</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(entry => (
                  <tr key={entry.id}>
                    <td className="py-2 pr-4 text-gray-900">{entry.vendor}</td>
                    <td className="py-2 pr-4 text-gray-900">
                      {reassigningId === entry.id ? (
                        <select
                          className="border border-gray-300 rounded px-2 py-1 text-sm"
                          value={reassignCategoryId}
                          onChange={e => setReassignCategoryId(Number(e.target.value))}
                        >
                          {categories?.map(cat => (
                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                          ))}
                        </select>
                      ) : (
                        entry.category_name
                      )}
                    </td>
                    <td className="py-2 pr-4 text-gray-900">{entry.hit_count}</td>
                    <td className="py-2 pr-4 text-gray-500">
                      {new Date(entry.last_used_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 pr-4">
                      {reassigningId === entry.id ? (
                        <span className="space-x-2">
                          <button
                            className="text-blue-600 hover:underline text-xs"
                            onClick={handleReassignSave}
                            disabled={reassignCategory.isPending}
                          >
                            Save
                          </button>
                          <button
                            className="text-gray-500 hover:underline text-xs"
                            onClick={() => setReassigningId(null)}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : deletingId === entry.id ? (
                        <span className="space-x-2 text-xs">
                          <span className="text-gray-700">Remove this vendor mapping?</span>
                          <button
                            className="bg-red-600 text-white px-3 py-1 rounded text-xs ml-2"
                            onClick={() => handleDeleteConfirm(entry.id)}
                            disabled={deleteVendorMemory.isPending}
                          >
                            Confirm
                          </button>
                          <button
                            className="text-gray-500 hover:underline text-xs"
                            onClick={() => setDeletingId(null)}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <span className="space-x-3">
                          <button
                            className="text-blue-600 hover:underline"
                            onClick={() => handleReassignStart(entry.id, entry.category_id)}
                          >
                            Reassign
                          </button>
                          <button
                            className="text-red-600 hover:underline"
                            onClick={() => handleDeleteStart(entry.id)}
                          >
                            Delete
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
