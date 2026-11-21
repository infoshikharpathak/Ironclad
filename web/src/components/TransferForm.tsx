import { useEffect, useState } from 'react';
import { initiateTransfer, getDirectory, ApiException } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';
import type { PublicAccount } from '../types';

type ToMode = 'own' | 'external';

export default function TransferForm() {
  const { accounts, addToast } = useBank();

  const [fromId, setFromId] = useState('');
  const [toMode, setToMode] = useState<ToMode>('own');
  const [toId, setToId] = useState('');
  const [externalId, setExternalId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Public directory for external transfers
  const [directory, setDirectory] = useState<PublicAccount[]>([]);
  useEffect(() => {
    getDirectory()
      .then((d) => setDirectory(d.accounts))
      .catch(() => {});
  }, []);

  // Default selection when accounts load
  if (accounts.length >= 2 && !fromId && !toId) {
    setFromId(accounts[0].id);
    setToId(accounts[1].id);
  }

  const resolvedTo = toMode === 'own' ? toId : externalId;
  const selectedFrom = accounts.find((a) => a.id === fromId);
  const selectedExternal = directory.find((d) => d.account_number === externalId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Enter a valid positive amount');
      return;
    }
    if (!resolvedTo) {
      setError('Select a destination account');
      return;
    }
    if (fromId === resolvedTo) {
      setError('Source and destination must be different');
      return;
    }

    setSubmitting(true);
    try {
      await initiateTransfer({
        from_account: fromId,
        to_account: resolvedTo,
        amount: parsedAmount,
        description,
        idempotency_key: `idem_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      });
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

      {/* To — mode toggle */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">
          To Account
        </label>
        <div className="flex gap-2 mb-3">
          <button
            type="button"
            onClick={() => setToMode('own')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              toMode === 'own'
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            My Accounts
          </button>
          <button
            type="button"
            onClick={() => setToMode('external')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              toMode === 'external'
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            External Account
          </button>
        </div>

        {toMode === 'own' ? (
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
        ) : (
          <div className="space-y-2">
            {/* Quick-pick from directory */}
            {directory.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {directory.map((p) => (
                  <button
                    key={p.account_number}
                    type="button"
                    onClick={() => setExternalId(p.account_number)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      externalId === p.account_number
                        ? 'border-emerald-500 bg-emerald-900/40 text-emerald-300'
                        : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600 hover:text-gray-200'
                    }`}
                  >
                    {p.owner_name}
                    <span className="ml-1.5 text-gray-500 font-mono text-[10px]">
                      {p.account_number}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {/* Manual entry */}
            <input
              type="text"
              value={externalId}
              onChange={(e) => setExternalId(e.target.value.toUpperCase())}
              placeholder="ACC-XXXXX-XXX"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
            />
            {selectedExternal && (
              <p className="text-xs text-gray-400">
                → {selectedExternal.owner_name} · {selectedExternal.account_type}
              </p>
            )}
          </div>
        )}
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
        disabled={submitting || !fromId || !resolvedTo || !amount}
        className="w-full px-4 py-3 rounded-lg bg-emerald-600 text-white font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {submitting ? 'Initiating…' : 'Initiate Transfer'}
      </button>
    </form>
  );
}
