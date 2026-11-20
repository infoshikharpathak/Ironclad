import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useBank } from '../context/BankContext';
import AccountCard from '../components/AccountCard';
import TransactionList from '../components/TransactionList';
import ResetButton from '../components/ResetButton';

export default function Dashboard() {
  const { accounts, loading } = useBank();
  // Show transactions for the first account by default; allow toggling.
  const [selectedIdx, setSelectedIdx] = useState(0);
  const selectedAccount = accounts[selectedIdx];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="text-gray-500 text-sm">Loading accounts…</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Accounts</h1>
        <div className="flex items-center gap-3">
          <ResetButton />
          <Link
            to="/transfer"
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 transition-colors"
          >
            New Transfer
          </Link>
        </div>
      </div>

      {/* Account cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {accounts.map((account, idx) => (
          <button
            key={account.id}
            onClick={() => setSelectedIdx(idx)}
            className={`text-left rounded-xl transition-all ${
              idx === selectedIdx
                ? 'ring-2 ring-emerald-500/50'
                : 'ring-0 hover:ring-1 hover:ring-gray-700'
            }`}
          >
            <AccountCard account={account} />
          </button>
        ))}
      </div>

      {/* Transactions */}
      {selectedAccount && (
        <div>
          <h2 className="text-sm font-medium text-gray-400 mb-3">
            Recent transactions — {selectedAccount.name}
          </h2>
          <TransactionList
            key={selectedAccount.id}
            accountId={selectedAccount.id}
          />
        </div>
      )}
    </div>
  );
}
