import { useTransactions } from '../api/transactions'

const STATUS_STYLES: Record<string, string> = {
  pending:   'bg-yellow-100 text-yellow-800',
  posted:    'bg-gray-100 text-gray-700',
  resolved:  'bg-green-100 text-green-800',
  escalated: 'bg-red-100 text-red-800',
  transfer:  'bg-blue-100 text-blue-800',
}

export default function Transactions() {
  const { data, isLoading, isError } = useTransactions()

  if (isLoading) return <div className="text-gray-500">Loading transactions…</div>
  if (isError)   return <div className="text-red-500">Failed to load transactions. Please refresh.</div>

  const txns = data?.data ?? []

  if (txns.length === 0) {
    return (
      <div>
        <h1 className="text-xl font-semibold text-gray-900 mb-4">Transactions</h1>
        <p className="text-gray-500">No transactions yet. Sync your accounts to get started.</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-4">
        Transactions <span className="text-sm font-normal text-gray-500">({data?.total})</span>
      </h1>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500 text-xs uppercase tracking-wide">
              <th className="pb-2 pr-4">Date</th>
              <th className="pb-2 pr-4">Description</th>
              <th className="pb-2 pr-4">Merchant</th>
              <th className="pb-2 pr-4 text-right">Amount</th>
              <th className="pb-2 pr-4">Account</th>
              <th className="pb-2 pr-4">Category</th>
              <th className="pb-2 pr-4 text-right">Confidence</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t) => (
              <tr key={t.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 pr-4 text-gray-500 whitespace-nowrap">{t.date}</td>
                <td className="py-2 pr-4 text-gray-900 max-w-xs truncate">{t.description}</td>
                <td className="py-2 pr-4 text-gray-600">{t.merchant_name ?? '—'}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  <span className={parseFloat(t.amount) < 0 ? 'text-green-700' : 'text-gray-900'}>
                    {parseFloat(t.amount) < 0 ? '+' : ''}
                    {Math.abs(parseFloat(t.amount)).toFixed(2)}
                  </span>
                </td>
                <td className="py-2 pr-4 text-gray-600">{t.account_name}</td>
                <td className="py-2 pr-4 text-gray-600">{t.category_name ?? '—'}</td>
                <td className="py-2 pr-4 text-right text-gray-600">
                  {t.confidence_score != null ? `${Math.round(t.confidence_score * 100)}%` : '—'}
                </td>
                <td className="py-2">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[t.status] ?? 'bg-gray-100 text-gray-700'}`}>
                    {t.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
