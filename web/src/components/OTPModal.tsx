import { useState } from 'react';
import { confirmTransfer } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';
import type { ApiError } from '../types';

export default function OTPModal() {
  const { otpEvent, clearOtp, refreshAccounts, addToast } = useBank();
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!otpEvent) return null;

  const handleConfirm = async () => {
    if (!input.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await confirmTransfer(otpEvent.transfer_id, input.trim());
      addToast('Transfer confirmed ✓', 'success');
      await refreshAccounts();
      clearOtp();
      setInput('');
    } catch (err: any) {
      const body: ApiError | undefined = err.body;
      setError(body?.message ?? 'Confirmation failed');
      if (body?.error === 'OTP_MAX_ATTEMPTS' || body?.error === 'OTP_EXPIRED') {
        setTimeout(() => {
          clearOtp();
          setInput('');
          setError(null);
        }, 2500);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-semibold text-white mb-1">Confirm Transfer</h2>
        <p className="text-sm text-gray-400 mb-4">
          Transfer{' '}
          <span className="text-white font-mono font-medium">
            {formatCurrency(otpEvent.amount)}
          </span>{' '}
          from <span className="text-white">{otpEvent.from_name}</span> to{' '}
          <span className="text-white">{otpEvent.to_name}</span>
        </p>

        {/* OTP display */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 text-center mb-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Your OTP Code</p>
          <p className="text-3xl font-mono font-bold tracking-[0.3em] text-emerald-400">
            {otpEvent.otp_code}
          </p>
        </div>

        {/* Input */}
        <label className="block text-xs text-gray-500 mb-1">Enter OTP to confirm</label>
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          value={input}
          onChange={(e) => setInput(e.target.value.replace(/\D/g, ''))}
          onKeyDown={(e) => e.key === 'Enter' && handleConfirm()}
          autoFocus
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-center text-xl font-mono tracking-[0.3em] text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
          placeholder="000000"
        />

        {error && (
          <p className="text-sm text-red-400 mt-2">{error}</p>
        )}

        <div className="flex gap-3 mt-5">
          <button
            onClick={() => {
              clearOtp();
              setInput('');
              setError(null);
            }}
            className="flex-1 px-4 py-2.5 rounded-lg border border-gray-700 text-gray-300 text-sm font-medium hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting || input.length < 6}
            className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'Confirming…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}
