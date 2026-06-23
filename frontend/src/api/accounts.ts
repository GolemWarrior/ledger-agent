import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export interface Account {
  id: number
  plaid_account_id: string
  name: string
  type: string
  last_synced_at: string | null
}

async function fetchAccounts(): Promise<{ data: Account[]; total: number }> {
  const res = await fetch('/api/v1/accounts')
  if (!res.ok) throw new Error('Failed to fetch accounts')
  return res.json()
}

async function fetchLinkToken(): Promise<string> {
  const res = await fetch('/api/v1/plaid/link-token')
  if (!res.ok) throw new Error('Failed to create link token')
  const json = await res.json()
  return json.data.link_token
}

async function exchangePublicToken(publicToken: string): Promise<void> {
  const res = await fetch('/api/v1/plaid/exchange-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ public_token: publicToken }),
  })
  if (!res.ok) throw new Error('Token exchange failed')
}

export function useAccounts() {
  return useQuery({ queryKey: ['accounts'], queryFn: fetchAccounts })
}

export function useLinkToken(enabled: boolean) {
  return useQuery({
    queryKey: ['plaid-link-token'],
    queryFn: fetchLinkToken,
    enabled,
    staleTime: 25 * 60 * 1000,
  })
}

export function useExchangeToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: exchangePublicToken,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })
}
