import { useState } from 'react';
import { deposit, ApiException } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';
import type { Account } from '../types';

export default function DepositModal({
  account,
  onClose,
}: {
  account: Account;
  onClose: () => void;
}) {
  const { refreshAccounts, addToast } = useBank();
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDeposit = async () => {
    setError(null);
    const parsed = parseFloat(amount);
    if (isNaN(parsed) || parsed <= 0) {
      setError('Enter a valid positive amount');
      return;
    }
    setSubmitting(true);
    try {
      await deposit(account.id, parsed);
      await refreshAccounts();
      addToast(`Deposited ${formatCurrency(parsed)} into ${account.name} ✓`, 'success');
      onClose();
    } catch (err: any) {
      if (err instanceof ApiException) {
        setError(err.body.message);
      } else {
        setError('Deposit failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-6">
        <h2 className="text-lg font-semibold text-white mb-1">Add Funds</h2>
        <p className="text-sm text-gray-400 mb-4">
          Deposit into <span className="text-white">{account.name}</span>
          <span className="text-gray-500 ml-1">
            (current: {formatCurrency(account.balance)})
          </span>
        </p>

        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
          Amount (USD)
        </label>
        <input
          type="number"
          step="0.01"
          min="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleDeposit()}
          autoFocus
          placeholder="0.00"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
        />

        {error && <p className="text-sm text-red-400 mt-2">{error}</p>}

        <div className="flex gap-3 mt-5">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-lg border border-gray-700 text-gray-300 text-sm font-medium hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleDeposit}
            disabled={submitting || !amount}
            className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'Depositing…' : 'Deposit'}
          </button>
        </div>
      </div>
    </div>
  );
}
