import { useParams, useNavigate } from 'react-router-dom'
import { useTransaction } from '../api/transactions'
import ReasoningTrace from '../components/ReasoningTrace'

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, isLoading, isError } = useTransaction(Number(id))

  if (!id) return <div className="text-red-500">Invalid transaction.</div>
  if (isLoading) return <div className="text-gray-500">Loading...</div>
  if (isError || !data) return <div className="text-red-500">Transaction not found.</div>

  const t = data.data
  const amount = parseFloat(t.amount)

  return (
    <div className="max-w-2xl">
      <button onClick={() => navigate('/')} className="text-blue-600 text-sm mb-4 hover:underline">
        ← Transactions
      </button>
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h1 className="text-lg font-semibold text-gray-900 mb-4">{t.description}</h1>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-gray-500">Merchant</dt>
            <dd className="text-gray-900">{t.merchant_name ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Amount</dt>
            <dd className={`font-mono font-medium ${amount < 0 ? 'text-green-700' : 'text-gray-900'}`}>
              {amount < 0 ? '+' : ''}{Math.abs(amount).toFixed(2)}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Date</dt>
            <dd className="text-gray-900">{t.date}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Account</dt>
            <dd className="text-gray-900">{t.account_name}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Category</dt>
            <dd className="text-gray-900">{t.category_name ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Confidence</dt>
            <dd className="text-gray-900">
              {t.confidence_score != null ? `${Math.round(t.confidence_score * 100)}%` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Status</dt>
            <dd className="text-gray-900">{t.status}</dd>
          </div>
        </dl>
      </div>

      {t.status === 'resolved' && t.reasoning_trace && (
        <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Reasoning Trace</h2>
          <ReasoningTrace trace={t.reasoning_trace} />
        </div>
      )}

      {t.status === 'escalated' && t.escalation_question && (
        <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-900">
          <p className="font-medium mb-1">Agent Question</p>
          <p>{t.escalation_question}</p>
        </div>
      )}
    </div>
  )
}
