import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

export interface Transaction {
  id: number
  description: string
  merchant_name: string | null
  amount: string
  date: string
  status: 'pending' | 'posted' | 'resolved' | 'escalated' | 'transfer'
  account_name: string
  category_name: string | null
  confidence_score: number | null
}

async function fetchTransactions(): Promise<{ data: Transaction[]; total: number }> {
  const res = await fetch('/api/v1/transactions')
  if (!res.ok) throw new Error('Failed to fetch transactions')
  return res.json()
}

export function useTransactions() {
  return useQuery({ queryKey: ['transactions'], queryFn: fetchTransactions })
}

export interface PendingTransaction {
  id: number
  description: string
  merchant_name: string | null
  amount: string
  date: string
  account_name: string
  category_name: string | null
  escalation_question: string | null
}

async function fetchPendingTransactions(): Promise<{ data: PendingTransaction[]; total: number }> {
  const res = await fetch('/api/v1/transactions/pending')
  if (!res.ok) throw new Error('Failed to fetch pending transactions')
  return res.json()
}

export function usePendingTransactions() {
  return useQuery({ queryKey: ['transactions', 'pending'], queryFn: fetchPendingTransactions })
}

async function resolveTransaction(id: number, answer: string): Promise<void> {
  const res = await fetch(`/api/v1/transactions/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
  if (!res.ok) throw new Error('Failed to resolve transaction')
}

export function useResolveTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, answer }: { id: number; answer: string }) =>
      resolveTransaction(id, answer),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions', 'pending'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}
