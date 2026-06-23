import { usePlaidLink } from 'react-plaid-link'
import { useExchangeToken } from '../api/accounts'

interface PlaidLinkProps {
  linkToken: string
}

export default function PlaidLink({ linkToken }: PlaidLinkProps) {
  const exchangeToken = useExchangeToken()

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: (public_token) => {
      exchangeToken.mutate(public_token)
    },
  })

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={() => open()}
        disabled={!ready || exchangeToken.isPending}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {exchangeToken.isPending ? 'Linking...' : 'Connect Your Bank Account'}
      </button>
      {exchangeToken.isError && (
        <span className="text-red-500 text-sm">Linking failed. Please try again.</span>
      )}
    </div>
  )
}
