import { useState } from 'react';
import { initiateTransfer, ApiException } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';

export default function TransferForm() {
  const { accounts, addToast } = useBank();

  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Default selection when accounts load
  if (accounts.length >= 2 && !fromId && !toId) {
    setFromId(accounts[0].id);
    setToId(accounts[1].id);
  }

  const selectedFrom = accounts.find((a) => a.id === fromId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Enter a valid positive amount');
      return;
    }
    if (fromId === toId) {
      setError('Source and destination must be different');
      return;
    }

    setSubmitting(true);
    try {
      await initiateTransfer({
        from_account: fromId,
        to_account: toId,
        amount: parsedAmount,
        description,
        idempotency_key: `idem_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      });
      // The OTP modal will pop up via the WebSocket event (or the initiate response
      // already triggers it via context). Clear the form.
      setAmount('');
      setDescription('');
    } catch (err: any) {
      if (err instanceof ApiException) {
        setError(err.body.message);
      } else {
        setError('Something went wrong');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-lg">
      {/* From */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
          From Account
        </label>
        <select
          value={fromId}
          onChange={(e) => setFromId(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.account_type}) — {formatCurrency(a.balance)}
            </option>
          ))}
        </select>
      </div>

      {/* To */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
          To Account
        </label>
        <select
          value={toId}
          onChange={(e) => setToId(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.account_type}) — {formatCurrency(a.balance)}
            </option>
          ))}
        </select>
      </div>

      {/* Amount */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
          Amount (USD)
        </label>
        <input
          type="number"
          step="0.01"
          min="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
        />
        {selectedFrom && (
          <p className="text-xs text-gray-500 mt-1">
            Available: {formatCurrency(selectedFrom.balance)}
          </p>
        )}
      </div>

      {/* Description */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
          Description <span className="text-gray-600">(optional)</span>
        </label>
        <input
          type="text"
          maxLength={200}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Monthly savings, rent, etc."
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
        />
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting || !fromId || !toId || !amount}
        className="w-full px-4 py-3 rounded-lg bg-emerald-600 text-white font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {submitting ? 'Initiating…' : 'Initiate Transfer'}
      </button>
    </form>
  );
}
