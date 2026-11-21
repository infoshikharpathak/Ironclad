import { useState } from 'react';
import { useBank } from '../context/BankContext';
import AccountCard from '../components/AccountCard';
import TransactionList from '../components/TransactionList';
import DepositModal from '../components/DepositModal';
import ResetButton from '../components/ResetButton';
import PendingTransfers from '../components/PendingTransfers';
import TransferForm from '../components/TransferForm';

export default function Dashboard() {
  const { accounts, loading } = useBank();
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [depositIdx, setDepositIdx] = useState<number | null>(null);
  const [showTransfer, setShowTransfer] = useState(false);
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
          <button
            onClick={() => setShowTransfer(!showTransfer)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              showTransfer
                ? 'bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700'
                : 'bg-emerald-600 text-white hover:bg-emerald-500'
            }`}
          >
            {showTransfer ? 'Hide Transfer' : 'New Transfer'}
          </button>
        </div>
      </div>

      {/* Account cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {accounts.map((account, idx) => (
          <div key={account.id} className="relative group">
            <button
              onClick={() => setSelectedIdx(idx)}
              className={`w-full text-left rounded-xl transition-all ${
                idx === selectedIdx
                  ? 'ring-2 ring-emerald-500/50'
                  : 'ring-0 hover:ring-1 hover:ring-gray-700'
              }`}
            >
              <AccountCard account={account} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setDepositIdx(idx);
              }}
              className="absolute top-3 right-14 opacity-0 group-hover:opacity-100 transition-opacity text-xs text-emerald-400 hover:text-emerald-300 bg-gray-800 border border-gray-700 rounded-md px-2 py-1"
            >
              + Add Funds
            </button>
          </div>
        ))}
      </div>

      {/* Transfer form — inline collapsible */}
      {showTransfer && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-sm font-medium text-white mb-4">New Transfer</h2>
          <TransferForm />
        </div>
      )}

      {/* Pending transfers */}
      <PendingTransfers />

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

      {/* Deposit modal */}
      {depositIdx !== null && accounts[depositIdx] && (
        <DepositModal
          account={accounts[depositIdx]}
          onClose={() => setDepositIdx(null)}
        />
      )}
    </div>
  );
}
