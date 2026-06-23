import { Routes, Route, NavLink } from 'react-router-dom'
import Transactions from './views/Transactions'
import PendingQueue from './views/PendingQueue'
import Categories from './views/Categories'
import VendorMemory from './views/VendorMemory'
import SyncStatus from './components/SyncStatus'
import PlaidLink from './components/PlaidLink'
import { useAccounts, useLinkToken } from './api/accounts'

export default function App() {
  const accounts = useAccounts()
  const noAccounts = accounts.data?.total === 0
  const linkToken = useLinkToken(!!accounts.data && noAccounts)

  if (accounts.isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <span className="text-gray-500">Loading...</span>
      </div>
    )
  }

  if (accounts.isError) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <span className="text-red-500">Failed to load accounts. Please refresh.</span>
      </div>
    )
  }

  if (noAccounts) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <h1 className="text-2xl font-semibold text-gray-900">Welcome to Ledger Agent</h1>
        <p className="text-gray-500">Connect your bank account to get started.</p>
        {linkToken.data && <PlaidLink linkToken={linkToken.data} />}
        {linkToken.isLoading && <span className="text-gray-400 text-sm">Preparing link...</span>}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex gap-6 items-center">
        <span className="font-semibold text-gray-800 mr-4">Ledger Agent</span>
        <NavLink to="/" end className={({ isActive }) => isActive ? 'text-blue-600 font-medium' : 'text-gray-600 hover:text-gray-900'}>Transactions</NavLink>
        <NavLink to="/pending" className={({ isActive }) => isActive ? 'text-blue-600 font-medium' : 'text-gray-600 hover:text-gray-900'}>Pending</NavLink>
        <NavLink to="/categories" className={({ isActive }) => isActive ? 'text-blue-600 font-medium' : 'text-gray-600 hover:text-gray-900'}>Categories</NavLink>
        <NavLink to="/vendor-memory" className={({ isActive }) => isActive ? 'text-blue-600 font-medium' : 'text-gray-600 hover:text-gray-900'}>Vendor Memory</NavLink>
        <div className="ml-auto">
          <SyncStatus />
        </div>
      </nav>
      <main className="px-6 py-6">
        <Routes>
          <Route path="/" element={<Transactions />} />
          <Route path="/pending" element={<PendingQueue />} />
          <Route path="/categories" element={<Categories />} />
          <Route path="/vendor-memory" element={<VendorMemory />} />
        </Routes>
      </main>
    </div>
  )
}
