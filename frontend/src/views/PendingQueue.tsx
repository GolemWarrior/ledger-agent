import { useState } from 'react'
import { usePendingTransactions, useResolveTransaction, type PendingTransaction } from '../api/transactions'

function PendingCard({ txn }: { txn: PendingTransaction }) {
  const resolve = useResolveTransaction()
  const [answer, setAnswer] = useState('')

  return (
    <li className="border border-gray-200 rounded p-4">
      <div className="flex justify-between items-start mb-2">
        <div>
          <p className="font-medium text-gray-900">{txn.description}</p>
          {txn.merchant_name && (
            <p className="text-sm text-gray-500">{txn.merchant_name}</p>
          )}
        </div>
        <span className="text-sm font-mono text-gray-700">${txn.amount}</span>
      </div>
      <p className="text-xs text-gray-400 mb-3">
        {txn.date} · {txn.account_name}
      </p>
      <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
        <p className="text-sm font-medium text-yellow-800">Agent question:</p>
        <p className="text-sm text-yellow-900 mt-1">
          {txn.escalation_question ?? 'What category does this transaction belong to?'}
        </p>
      </div>
      <textarea
        className="w-full border border-gray-300 rounded p-2 text-sm resize-none"
        rows={2}
        placeholder="Type your answer..."
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
      />
      <button
        className="mt-2 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        disabled={!answer.trim() || resolve.isPending}
        onClick={() =>
          resolve.mutate(
            { id: txn.id, answer: answer.trim() },
            { onSuccess: () => setAnswer('') }
          )
        }
      >
        {resolve.isPending ? 'Submitting...' : 'Submit'}
      </button>
      {resolve.isError && (
        <p className="mt-1 text-xs text-red-600">Failed to submit. Try again.</p>
      )}
    </li>
  )
}

export default function PendingQueue() {
  const { data, isLoading, error } = usePendingTransactions()

  if (isLoading) return <div className="p-4 text-gray-500">Loading...</div>
  if (error) return <div className="p-4 text-red-600">Failed to load pending transactions.</div>

  const pending = data?.data ?? []

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-4">Pending Queue</h1>
      {pending.length === 0 ? (
        <p className="text-gray-500">No escalated transactions — the agent resolved everything automatically.</p>
      ) : (
        <ul className="space-y-4">
          {pending.map((txn: PendingTransaction) => (
            <PendingCard key={txn.id} txn={txn} />
          ))}
        </ul>
      )}
    </div>
  )
}
