import { useState } from 'react';
import { resetAccounts } from '../lib/api';
import { useBank } from '../context/BankContext';

export default function ResetButton() {
  const { refreshAccounts, addToast } = useBank();
  const [busy, setBusy] = useState(false);

  const handleReset = async () => {
    setBusy(true);
    try {
      await resetAccounts();
      await refreshAccounts();
      addToast('Demo accounts reset ✓', 'success');
    } catch {
      addToast('Reset failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleReset}
      disabled={busy}
      className="text-xs text-gray-500 hover:text-gray-300 border border-gray-800 hover:border-gray-600 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
    >
      {busy ? 'Resetting…' : 'Reset Demo'}
    </button>
  );
}
