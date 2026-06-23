import { useState } from 'react'
import { useAddCategory, useCategories, useDeleteCategory, useRenameCategory } from '../api/categories'

export default function Categories() {
  const { data: categories, isLoading, isError } = useCategories()
  const addCategory = useAddCategory()
  const renameCategory = useRenameCategory()
  const deleteCategory = useDeleteCategory()

  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [newName, setNewName] = useState('')
  const [newHint, setNewHint] = useState('')

  function handleRenameStart(id: number, currentName: string) {
    setRenamingId(id)
    setRenameValue(currentName)
    setDeletingId(null)
  }

  function handleRenameSave() {
    if (!renamingId || !renameValue.trim()) return
    const capturedId = renamingId
    renameCategory.mutate(
      { id: capturedId, name: renameValue.trim() },
      { onSuccess: () => setRenamingId(prev => prev === capturedId ? null : prev) }
    )
  }

  function handleDeleteStart(id: number) {
    setDeletingId(id)
    setRenamingId(null)
  }

  function handleDeleteConfirm(id: number) {
    deleteCategory.mutate(id, { onSuccess: () => setDeletingId(null) })
  }

  function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    addCategory.mutate(
      { name: newName.trim(), hint: newHint.trim() || undefined },
      {
        onSuccess: () => {
          setNewName('')
          setNewHint('')
        },
      }
    )
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Categories</h1>

      {isLoading && <p className="text-gray-500">Loading categories…</p>}
      {isError && <p className="text-red-600">Failed to load categories.</p>}

      {categories && (
        <>
          {renameCategory.isError && (
            <p className="text-red-600 text-xs mb-3">Failed to rename category. The name may already exist.</p>
          )}
          {deleteCategory.isError && (
            <p className="text-red-600 text-xs mb-3">Failed to delete category.</p>
          )}
          {categories.length === 0 ? (
            <p className="text-gray-500">No categories found.</p>
          ) : (
            <table className="w-full text-sm text-left mb-8">
              <thead>
                <tr>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Name</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Hint</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Transactions</th>
                  <th className="py-2 pr-4 text-gray-500 font-medium border-b">Actions</th>
                </tr>
              </thead>
              <tbody>
                {categories.map(cat => (
                  <tr key={cat.id}>
                    <td className="py-2 pr-4 text-gray-900">
                      {renamingId === cat.id ? (
                        <input
                          className="border border-gray-300 rounded px-2 py-1 text-sm"
                          value={renameValue}
                          onChange={e => setRenameValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleRenameSave()
                            if (e.key === 'Escape') setRenamingId(null)
                          }}
                          autoFocus
                        />
                      ) : (
                        cat.name
                      )}
                    </td>
                    <td className="py-2 pr-4 text-gray-500">{cat.hint ?? '—'}</td>
                    <td className="py-2 pr-4 text-gray-900">{cat.transaction_count}</td>
                    <td className="py-2 pr-4">
                      {renamingId === cat.id ? (
                        <span className="space-x-2">
                          <button
                            className="text-blue-600 hover:underline text-xs"
                            onClick={handleRenameSave}
                            disabled={renameCategory.isPending}
                          >
                            Save
                          </button>
                          <button
                            className="text-gray-500 hover:underline text-xs"
                            onClick={() => setRenamingId(null)}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : deletingId === cat.id ? (
                        <span className="space-x-2 text-xs">
                          <span className="text-gray-700">
                            {cat.transaction_count} transaction{cat.transaction_count !== 1 ? 's' : ''} will revert to Uncategorized. Confirm?
                          </span>
                          <button
                            className="bg-red-600 text-white px-3 py-1 rounded text-xs ml-2"
                            onClick={() => handleDeleteConfirm(cat.id)}
                            disabled={deleteCategory.isPending}
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
                            onClick={() => handleRenameStart(cat.id, cat.name)}
                          >
                            Rename
                          </button>
                          {cat.name !== 'Uncategorized' && (
                            <button
                              className="text-red-600 hover:underline"
                              onClick={() => handleDeleteStart(cat.id)}
                            >
                              Delete
                            </button>
                          )}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="border-t pt-6">
            <h2 className="text-sm font-medium text-gray-700 mb-3">Add Category</h2>
            <form onSubmit={handleAddSubmit} className="flex gap-3 items-end flex-wrap">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500">Name *</label>
                <input
                  className="border border-gray-300 rounded px-2 py-1 text-sm"
                  placeholder="e.g. Side Project"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500">Hint (optional)</label>
                <input
                  className="border border-gray-300 rounded px-2 py-1 text-sm w-72"
                  placeholder="e.g. software tools, domains, hardware for freelance"
                  value={newHint}
                  onChange={e => setNewHint(e.target.value)}
                />
              </div>
              <button
                type="submit"
                className="bg-blue-600 text-white px-3 py-1 rounded text-sm"
                disabled={addCategory.isPending || !newName.trim()}
              >
                {addCategory.isPending ? 'Adding…' : 'Add Category'}
              </button>
            </form>
            {addCategory.isError && (
              <p className="text-red-600 text-xs mt-2">Failed to add category.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
