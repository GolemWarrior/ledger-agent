import { Routes, Route, NavLink } from 'react-router-dom'
import Transactions from './views/Transactions'
import PendingQueue from './views/PendingQueue'
import Categories from './views/Categories'
import VendorMemory from './views/VendorMemory'
import SyncStatus from './components/SyncStatus'

export default function App() {
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
